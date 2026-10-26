"""Read a CIM. Text and layout only — no model involved.

A CIM is a PowerPoint export: landscape slides whose text comes back as
positioned fragments with no guaranteed reading order. Roughly 18% of
runs in a real deck move *up* the page, so reading `extract_text()`
top-to-bottom gives a scrambled narrative.

So fragments are collected with their coordinates and re-ordered: top to
bottom, then left to right, with a tolerance that treats fragments on
roughly the same line as one line. That recovers the reading order the
slide was designed to have.

What this module does **not** do is interpret. It returns pages, lines
and headings. Deciding that a line states a retention figure is the job
of `retrieval/`, and extracting a table into observations is the job of
the LLM. Keeping those separate means the deterministic part can be
measured on its own — and it is the baseline a model has to beat to
justify its cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

# Fragments whose baselines are within this many points are one line.
LINE_TOLERANCE = 4.0

# A horizontal gap wider than this share of the page splits one visual
# line into two. Slides are laid out in columns, and two bullets sitting
# at the same height in different columns are unrelated sentences. Join
# them and a retrieval step reads "retention of 94%" immediately
# followed by "top 10 customer concentration", and attributes the figure
# to the wrong metric.
COLUMN_GAP_RATIO = 0.08

# Two lines starting within this many points of each other are in the
# same column, so one may be a continuation of the other.
SAME_COLUMN_TOLERANCE = 6.0

# A page holding less text than this is a divider or a graphic-led
# slide. Reported rather than skipped: a page the system could not read
# is not an empty page, and treating it as one produces a confident
# answer with a hole in it.
SPARSE_PAGE_CHARS = 200


@dataclass
class Fragment:
    text: str
    x: float
    y: float
    size: float


@dataclass
class Page:
    """One slide, read two ways.

    `lines` splits at column boundaries, which is what prose needs: two
    bullets at the same height in different columns are unrelated
    sentences, and joining them makes a retrieval step attribute a
    figure to the wrong metric.

    `rows` keeps everything at the same height together, which is what a
    table needs: a row label and its six values are one row, and the gap
    between the label column and the first figure is exactly the gap
    that splits a bullet.

    Both come from the same fragments. Neither is the "right" reading —
    a slide is a layout, and what counts as one line depends on what you
    are looking for.
    """

    number: int
    lines: list[str] = field(default_factory=list)
    rows: list[str] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    image_sizes: list[tuple[int, int]] = field(default_factory=list)
    image_count: int = 0
    # Images on this page that are not the deck's repeated background.
    content_image_count: int = 0

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def table_text(self) -> str:
        return "\n".join(self.rows)

    @property
    def character_count(self) -> int:
        return sum(len(line) for line in self.lines)

    @property
    def is_sparse(self) -> bool:
        return self.character_count < SPARSE_PAGE_CHARS

    @property
    def heading(self) -> str | None:
        """The largest text near the top — a slide's title.

        Headings matter more in a deck than in a document: they are the
        only structure there is, and section-based retrieval depends on
        them entirely.
        """
        # A content slide puts its title at the top. A divider puts it
        # in the middle of the page, so looking only at the top band
        # finds no heading on exactly the slides that name the sections.
        band = (self.fragments if self.is_sparse else
                [f for f in self.fragments if f.y > self.height * 0.80])
        candidates = [f for f in band if f.text.strip()]
        if not candidates:
            return None
        largest = max(candidates, key=lambda f: f.size)
        same_line = [f for f in candidates
                     if abs(f.y - largest.y) <= LINE_TOLERANCE]
        same_line.sort(key=lambda f: f.x)
        return " ".join(f.text.strip() for f in same_line).strip() or None


@dataclass
class Document:
    path: Path
    pages: list[Page]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def sparse_pages(self) -> list[int]:
        """Pages the text layer could not meaningfully read."""
        return [p.number for p in self.pages if p.is_sparse]

    @property
    def unreadable_pages(self) -> list[int]:
        """Sparse pages carrying a *content* image.

        A deck puts a background template on nearly every page, so
        "sparse and has an image" describes every section divider in the
        document. Counting those as unreadable would bury the two pages
        that genuinely hold figures the text layer cannot recover, and a
        warning raised fifteen times is a warning nobody reads.
        """
        return [p.number for p in self.pages
                if p.is_sparse and p.content_image_count > 0]

    def page(self, number: int) -> Page:
        return self.pages[number - 1]


def _emit(group: list[Fragment], page_width: float,
          out: list[tuple[float, str]]) -> None:
    """Turn one horizontal band of fragments into one or more lines.

    Split where the horizontal gap is wide enough to be a column
    boundary rather than a word space.
    """
    group.sort(key=lambda f: f.x)
    gap_limit = page_width * COLUMN_GAP_RATIO
    run: list[Fragment] = []

    for fragment in group:
        if run:
            previous = run[-1]
            # Approximate the right-hand edge: PDF fragments do not
            # carry a width, and character count times half the font
            # size is close enough to tell a word space from a column.
            edge = previous.x + len(previous.text) * previous.size * 0.5
            if fragment.x - edge > gap_limit:
                text = " ".join(f.text.strip() for f in run if f.text.strip())
                if text:
                    out.append((run[0].x, text))
                run = []
        run.append(fragment)

    text = " ".join(f.text.strip() for f in run if f.text.strip())
    if text:
        out.append((run[0].x, text))


def _bands(fragments: list[Fragment]) -> list[list[Fragment]]:
    """Group fragments into horizontal bands, top to bottom."""
    if not fragments:
        return []
    remaining = sorted(fragments, key=lambda f: (-f.y, f.x))
    bands: list[list[Fragment]] = [[remaining[0]]]
    for fragment in remaining[1:]:
        if abs(fragment.y - bands[-1][0].y) <= LINE_TOLERANCE:
            bands[-1].append(fragment)
        else:
            bands.append([fragment])
    return bands


def _order(fragments: list[Fragment], page_width: float
           ) -> tuple[list[str], list[str]]:
    """Return (lines, rows): split at columns, and not split."""
    placed: list[tuple[float, str]] = []
    rows: list[str] = []
    for band in _bands(fragments):
        _emit(list(band), page_width, placed)
        band.sort(key=lambda f: f.x)
        row = " ".join(f.text.strip() for f in band if f.text.strip())
        if row:
            rows.append(row)
    return _rejoin_wrapped(placed), rows


def _rejoin_wrapped(placed: list[tuple[float, str]]) -> list[str]:
    """Rejoin a bullet that wrapped onto a second line.

    A bullet running past the column width is two lines on the page and
    one statement in meaning. Separated, a label loses its figure — "The
    top ten customers represent" on one line, "31% of ARR" on the next —
    and the metric is never found.

    Columns are tracked separately, because lines arrive interleaved:
    reading top to bottom across a two-column slide gives left, right,
    left, right, so a bullet's continuation is two entries later rather
    than the next one. Joining to the previous *entry* chains unrelated
    bullets from opposite sides of the slide together; joining to the
    previous entry *in the same column* is what was meant.
    """
    lines: list[str] = []
    last_in_column: dict[int, int] = {}
    absorbed: set[int] = set()

    for x, text in placed:
        column = round(x / SAME_COLUMN_TOLERANCE)
        index = last_in_column.get(column)
        wraps = (
            index is not None
            and index not in absorbed
            and not re.search(r"[.!?:]$", lines[index])
        )
        if wraps:
            # At most one continuation. A line that keeps absorbing
            # whatever follows it swallows the next bullet too, and then
            # a figure from one statement attaches to the label of
            # another — which is worse than the truncation it fixes.
            lines[index] = f"{lines[index]} {text}"
            absorbed.add(index)
            continue
        lines.append(text)
        last_in_column[column] = len(lines) - 1

    return lines
def read(path: Path | str) -> Document:
    path = Path(path)
    reader = PdfReader(str(path))
    pages: list[Page] = []

    for index, raw in enumerate(reader.pages, start=1):
        box = raw.mediabox
        page = Page(number=index, width=float(box.width),
                    height=float(box.height))

        def visitor(text, cm, tm, font_dict, font_size, _page=page):
            if not (text and text.strip()):
                return
            # The text matrix holds a position relative to the current
            # transformation matrix, not a page coordinate. Composing
            # them is what makes the ordering below mean anything.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            _page.fragments.append(
                Fragment(text=text, x=float(x), y=float(y),
                         size=float(font_size or 0)))

        try:
            raw.extract_text(visitor_text=visitor)
        except Exception:
            pass

        try:
            page.image_sizes = [im.image.size for im in raw.images]
        except Exception:
            page.image_sizes = []
        page.image_count = len(page.image_sizes)

        page.lines, page.rows = _order(page.fragments, page.width)
        pages.append(page)

    _mark_content_images(pages)
    return Document(path=path, pages=pages)


def _mark_content_images(pages: list[Page]) -> None:
    """Separate a deck's furniture from its content.

    An image repeated across a quarter of the pages is a background or a
    logo, not data. One appearing on a page or two is a chart or a
    photograph, and if it sits on a page with no text then it holds
    figures nothing can read.
    """
    from collections import Counter

    frequency: Counter = Counter()
    for page in pages:
        for size in set(page.image_sizes):
            frequency[size] += 1

    furniture = {size for size, count in frequency.items()
                 if count > len(pages) // 4}
    for page in pages:
        page.content_image_count = sum(
            1 for size in page.image_sizes if size not in furniture)

