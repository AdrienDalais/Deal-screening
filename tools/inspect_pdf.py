"""Report the STRUCTURE of a PDF. Never its contents.

    python -m tools.inspect_pdf "/path/to/document.pdf"

Written so that a confidential document can be characterised without any
part of it being disclosed. The output contains page dimensions, counts,
and statistical summaries — no words, no numbers from the document, no
file name unless you pass one that reveals something.

Read the code before running it on anything sensitive. The only things
that ever reach stdout are integers, floats derived from counts, and
fixed strings defined in this file.
"""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

PT_PER_INCH = 72.0


def _orientation(width: float, height: float) -> str:
    ratio = width / height if height else 0
    if ratio > 1.55:
        return "landscape 16:9-ish (slide deck)"
    if ratio > 1.05:
        return "landscape 4:3-ish (slide deck)"
    if ratio < 0.95:
        return "portrait (document)"
    return "square"


def inspect(path: Path) -> None:
    reader = PdfReader(str(path))
    pages = reader.pages

    sizes: Counter[tuple[int, int]] = Counter()
    orientations: Counter[str] = Counter()
    char_counts: list[int] = []
    run_counts: list[int] = []
    image_counts: list[int] = []
    largest_image: tuple[int, int] = (0, 0)
    image_sizes: Counter[tuple[int, int]] = Counter()
    pages_with_images = 0
    total_images = 0
    big_image_pages = 0          # an image covering >25% of the page
    sparse_pages = 0             # under 200 characters: a graphic-led slide
    y_disorder: list[float] = [] # how far text departs from top-to-bottom order

    for page in pages:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        sizes[(round(width), round(height))] += 1
        orientations[_orientation(width, height)] += 1

        runs: list[tuple[float, float, int]] = []

        def visitor(text, cm, tm, font_dict, font_size, _runs=runs):
            if not (text and text.strip()):
                return
            # The text matrix holds a position relative to the current
            # transformation matrix, not a page coordinate. Compose the
            # two, or every position reads as near-zero and the
            # reading-order measure below becomes meaningless.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            _runs.append((float(x), float(y), len(text.strip())))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            pass

        char_counts.append(sum(r[2] for r in runs))
        run_counts.append(len(runs))
        if sum(r[2] for r in runs) < 200:
            sparse_pages += 1

        # Reading-order disorder: what share of consecutive text runs move
        # UP the page. Flowing prose is near zero; slide layouts are high.
        if len(runs) > 3:
            backwards = sum(1 for a, b in zip(runs, runs[1:]) if b[1] > a[1] + 2)
            y_disorder.append(backwards / (len(runs) - 1))

        try:
            images = list(page.images)
        except Exception:
            images = []
        image_counts.append(len(images))
        total_images += len(images)
        if images:
            pages_with_images += 1
        for image in images:
            try:
                w, h = image.image.size
            except Exception:
                continue
            image_sizes[(w, h)] += 1
            if w * h > largest_image[0] * largest_image[1]:
                largest_image = (w, h)

    n = len(pages)
    print(f"pages                     {n}")
    print()
    print("PAGE GEOMETRY")
    for (w, h), count in sizes.most_common(4):
        print(f"  {w} x {h} pt  ({w/PT_PER_INCH:.1f} x {h/PT_PER_INCH:.1f} in)"
              f"   {count} page(s)   {_orientation(w, h)}")
    print()
    print("TEXT DENSITY  (characters per page)")
    if char_counts:
        print(f"  median {statistics.median(char_counts):,.0f}   "
              f"mean {statistics.mean(char_counts):,.0f}   "
              f"min {min(char_counts):,}   max {max(char_counts):,}")
        print(f"  pages under 200 chars (graphic-led): {sparse_pages} "
              f"({sparse_pages / n:.0%})")
    print()
    print("TEXT FRAGMENTATION  (separate positioned runs per page)")
    if run_counts:
        print(f"  median {statistics.median(run_counts):,.0f}   "
              f"max {max(run_counts):,}")
    if y_disorder:
        share = statistics.median(y_disorder)
        print(f"  median share of runs that move UP the page: {share:.0%}")
        print("    flowing prose is typically under 10%; slide layouts are"
              " much higher,")
        print("    which means extracted text arrives out of reading order.")
    print()
    print("IMAGES")
    print(f"  total placements          {total_images}")
    print(f"  distinct dimensions       {len(image_sizes)}")
    icons = sum(c for (w, h), c in image_sizes.items() if w * h < 10_000)
    large = {d: c for d, c in image_sizes.items() if d[0] * d[1] >= 250_000}
    print(f"  of which tiny (<10k px)   {icons}  "
          f"— glyphs, bullets and logos, not data")
    print(f"  distinct LARGE images     {len(large)}  "
          f"({sum(large.values())} placements)")
    repeated = [(d, c) for d, c in large.items() if c > n // 4]
    for (w, h), count in repeated:
        print(f"    {w} x {h} px on {count} pages — a slide background, "
              f"not content")
    print(f"  pages containing an image {pages_with_images} "
          f"({pages_with_images / n:.0%})")
    if largest_image != (0, 0):
        print(f"  largest image             {largest_image[0]} x "
              f"{largest_image[1]} px")
    print()
    total_chars = sum(char_counts)
    print("TEXT VOLUME")
    print(f"  total characters          {total_chars:,}  "
          f"(roughly {total_chars // 4:,} tokens)")
    print(f"  pages with no text at all {sum(1 for c in char_counts if c == 0)}")
    print()
    print("READING")
    # Judge on distinct large images, not placements: a background
    # template repeated on every page is not data.
    data_images = sum(1 for d, c in image_sizes.items()
                      if d[0] * d[1] >= 250_000 and c <= n // 4)
    if sparse_pages / n > 0.5:
        print("  Graphic-led. Most pages carry little text, so figures shown")
        print("  only inside images are NOT in the file and cannot be read")
        print("  without OCR or a vision model.")
    elif data_images > 0:
        print("  Slide-shaped and mixed. Most pages carry real text, so")
        print("  charts are probably vector with extractable labels — but")
        print(f"  {sparse_pages} page(s) hold almost no text and are likely")
        print("  section dividers or full-page graphics. Anything shown only")
        print("  on those pages needs OCR, or must be reported as unread.")
    else:
        print("  Largely text. Extraction should recover most content,")
        print("  subject to reading order.")
    print()
    print("Nothing above is content from the document. Only counts,")
    print("dimensions, and the fixed sentences written in this file.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    inspect(args.path)


if __name__ == "__main__":
    main()
