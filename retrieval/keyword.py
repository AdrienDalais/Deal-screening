"""Finding things in a CIM by heading and by pattern. No embeddings.

Deliberately the simplest thing that could work, because it is the
baseline. An embedding index is only worth its complexity if it finds
evidence this misses, and that cannot be known without measuring this
first.

Two ways of looking:

**By section.** A deck's slide titles are the only structure it has, so
a section is found by matching its heading. Returns the pages, in order,
with the heading kept.

**By pattern.** A KPI stated in prose — "Net revenue retention of 118%
in FY24" — is found by looking for the metric's vocabulary near a number
with the right shape. Returns the sentence and the page, because a
figure without its source is not evidence.

Nothing here decides whether a claim is true. It finds candidate
statements; verifying them against the financials is reconciliation's
job, and the cohort module's later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingestion.pdf import Document, Page

# Section name -> words that identify its heading. First match wins, so
# more specific sections are listed before more general ones.
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "executive_summary": ("executive summary",),
    "investment_highlights": ("investment highlights", "key highlights"),
    "business_overview": ("business overview", "why the business exists",
                          "company overview"),
    "product": ("product", "platform", "technology overview"),
    "customers": ("customers", "customer", "retention"),
    "market": ("market", "competition", "competitive landscape"),
    "financials": ("financial summary", "financial review", "financials"),
    "management": ("management", "organisation", "team"),
    "process": ("process", "timetable", "transaction"),
    "ownership": ("ownership", "shareholder", "cap table"),
}

# metric -> (vocabulary that must appear, pattern the value must match)
KPI_PATTERNS: dict[str, tuple[tuple[str, ...], str]] = {
    "gross_retention": (("gross revenue retention", "gross retention"),
                        r"(\d{1,3}(?:\.\d+)?)\s*%"),
    "net_retention": (("net revenue retention", "net retention", "nrr"),
                      r"(\d{1,3}(?:\.\d+)?)\s*%"),
    "logo_retention": (("logo retention",), r"(\d{1,3}(?:\.\d+)?)\s*%"),
    "customer_count": (("customers", "customer organisations",
                        "provider organisations", "enterprise customers"),
                       r"(\d[\d,]{1,6})\s+(?:enterprise\s+)?"
                       r"(?:customers|provider organisations|customer)"),
    "top_10_concentration": (("top ten customers", "top 10 customers",
                              "customer concentration"),
                             r"(\d{1,3}(?:\.\d+)?)\s*%"),
    "average_contract_value": (("average contract value", "acv"),
                               r"[£€$]\s?(\d[\d,.]*)\s*([kKmM])?"),
    "employees": (("employees", "full-time employees", "headcount"),
                  r"(\d[\d,]{1,6})\s+(?:full-time\s+)?employees"),
    "market_size": (("addressable market", "market at", "market size",
                     "tam"),
                    r"[£€$]\s?(\d[\d,.]*)\s*([bBmM])"),
    "rule_of_40": (("rule of 40",), r"(\d{1,3}(?:\.\d+)?)\s*%"),
}


@dataclass(frozen=True)
class Section:
    name: str
    heading: str
    pages: tuple[int, ...]
    text: str


@dataclass(frozen=True)
class Finding:
    """A candidate statement, with where it was found.

    `sentence` is kept verbatim. A figure without the words around it
    cannot be checked by a human, and every one of these is going to be
    checked by a human.
    """

    key: str
    sentence: str
    page: int
    raw_value: str
    unit_hint: str | None = None

    @property
    def value(self) -> float | None:
        """The figure, with its suffix applied.

        A CIM writes "£66k" and means 66,000. Doing this here rather
        than in each caller means the scale is interpreted once, in the
        place that also holds the sentence it came from — so a wrong
        reading can be checked against the words.
        """
        try:
            number = float(self.raw_value.replace(",", ""))
        except ValueError:
            return None
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
        return number * multiplier.get((self.unit_hint or "").lower(), 1)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def find_sections(document: Document) -> list[Section]:
    """Locate each section, delimited by the deck's divider slides.

    A deck is structured by dividers — a slide carrying a section title
    and almost nothing else — and every content slide after one belongs
    to that section until the next divider.

    Ending a section at the next *content* heading instead was the
    obvious reading and the wrong one: each section then resolved to the
    divider page alone, which by definition has no text on it, and
    summarising it produced "NOT STATED" for sections the document
    covers in full.

    Where a deck has no dividers, every matching heading starts a
    section and it runs to the next match.
    """
    dividers: list[tuple[int, str, str]] = []
    headings: list[tuple[int, str, str]] = []

    for page in document.pages:
        heading = page.heading
        if not heading:
            continue
        normalised = _normalise(heading)
        for name, keywords in SECTION_KEYWORDS.items():
            if any(word in normalised for word in keywords):
                headings.append((page.number, name, heading))
                if page.is_sparse:
                    dividers.append((page.number, name, heading))
                break

    # A numbered title — "4. Customers and Retention" — is a section
    # divider. An unnumbered sparse slide is a graphic: a logo wall, a
    # chart, a photograph. Treating those as dividers truncates the
    # section they sit inside to the page before them.
    numbered = [d for d in dividers if re.match(r"^\d+[.)]\s", d[2].strip())]
    if numbered:
        dividers = numbered

    markers = dividers or headings
    sections: list[Section] = []
    claimed: set[str] = set()

    for index, (number, name, heading) in enumerate(markers):
        if name in claimed:
            continue
        end = (markers[index + 1][0] - 1 if index + 1 < len(markers)
               else document.page_count)
        numbers = tuple(range(number, end + 1))
        text = "\n".join(document.page(n).text for n in numbers).strip()
        if not text:
            continue
        claimed.add(name)
        sections.append(Section(name=name, heading=heading,
                                pages=numbers, text=text))
    return sections


def _sentences(page: Page) -> list[str]:
    """Split a slide into statements.

    Slides are bullets rather than prose, so a line is usually already a
    statement. Lines are split further on full stops so that one bullet
    carrying two figures yields two candidates.
    """
    out: list[str] = []
    for line in page.lines:
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if part:
                out.append(part)
    return out


def find_kpis(document: Document,
              patterns: dict | None = None) -> list[Finding]:
    """Find candidate KPI statements across the whole document.

    Scans every page rather than only the highlights section: a figure
    quoted in passing on page 60 is as real as one on the summary slide,
    and a retrieval step that only looks where it expects to find things
    will confirm whatever it assumed.
    """
    patterns = patterns or KPI_PATTERNS
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    for page in document.pages:
        for sentence in _sentences(page):
            lowered = _normalise(sentence)
            for key, (vocabulary, expression) in patterns.items():
                if not any(word in lowered for word in vocabulary):
                    continue
                match = re.search(expression, sentence)
                if not match:
                    continue
                groups = match.groups()
                signature = (key, match.group(0))
                if signature in seen:
                    continue
                seen.add(signature)
                findings.append(Finding(
                    key=key, sentence=sentence, page=page.number,
                    raw_value=groups[0],
                    unit_hint=(groups[1] if len(groups) > 1 else None),
                ))
    return findings
