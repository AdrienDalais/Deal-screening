"""Generate a CIM-style PDF from a CompanyTruth.

Text, not images: the financial summary is a real table of extractable
text, matching how CIMs actually present financials.

Length is a parameter. The full document runs to roughly the 80-100 pages
of a real CIM, which is what forces chunking and makes retrieval a real
problem; a short variant with identical figures, defects and decoys keeps
the fast test loop fast.

Page numbers of the sections that matter are captured during rendering
and returned, so the answer key cites the page the figure actually landed
on rather than a page we guessed.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from storage import enums as E
from tests.fixtures import prose
from tests.fixtures.truth import CompanyTruth

_styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontSize=10,
                      leading=14, spaceAfter=8)
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontSize=16, spaceBefore=6,
                    spaceAfter=12)
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=12, spaceBefore=10,
                    spaceAfter=6)
TITLE = ParagraphStyle("title", parent=_styles["Title"], fontSize=24, spaceAfter=18)
CENTRE = ParagraphStyle("centre", parent=BODY, alignment=TA_CENTER)


class PageMark(Flowable):
    """Zero-height flowable that records which page it landed on.

    The answer key must cite the page a figure is actually printed on. A
    guess would be wrong the moment any paragraph above it changes
    length, and would then quietly corrupt every source-reference test.
    """

    def __init__(self, key: str, sink: dict[str, int]) -> None:
        super().__init__()
        self.key, self.sink = key, sink
        self.width = self.height = 0

    def draw(self) -> None:
        self.sink[self.key] = self.canv.getPageNumber()


def _money(value: float, unit: E.Unit) -> str:
    scaled = value / unit.multiplier
    return f"({abs(scaled):,.1f})" if scaled < 0 else f"{scaled:,.1f}"


def _financial_table(truth: CompanyTruth) -> Table:
    """The financial summary. Live text, units stated in the header.

    Actual and forecast columns run continuously with a heading above
    marking where one becomes the other — the convention real CIMs use.
    """
    unit_word = {E.Unit.MILLIONS: "m", E.Unit.THOUSANDS: "k"}[truth.cim_unit]
    periods = truth.periods

    group_row = [""]
    for period in periods:
        group_row.append("Actual" if period.basis == E.Basis.ACTUAL
                         else "Forecast")
    header = [f"{truth.currency}{unit_word}"] + [p.label for p in periods]

    rows = [group_row, header]
    shown = ["arr", "revenue", "recurring_revenue", "non_recurring_revenue",
             "cogs", "gross_profit", "total_opex", "ebitda_adjustments",
             "adjusted_ebitda"]
    for metric in shown:
        try:
            item = truth.item(metric)
        except KeyError:
            continue
        # The CIM label is used verbatim, including where it is wrong.
        # The adjusted EBITDA row prints as "EBITDA": that is the planted
        # defect, and the extractor must transcribe it faithfully.
        line = [item.cim_label]
        for period in periods:
            raw = item.values.get(period.label)
            if raw is None:
                line.append("n.a.")
                continue
            line.append(_money(-raw if item.is_cost else raw, truth.cim_unit))
        rows.append(line)

    table = Table(rows, hAlign="LEFT", colWidths=[52 * mm] + [18 * mm] * len(periods))
    n = len(periods)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.75, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.25, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


# Section name -> share of the filler budget. Finance-adjacent prose is
# spread across all of them, so retrieval cannot succeed by finding the
# single place money is discussed.
BUDGET_SHARES = {
    "executive_summary": 0.03, "highlights": 0.04, "business": 0.12,
    "customers": 0.12, "market": 0.12, "management": 0.06,
    "process": 0.04, "appendices": 0.47,
}


def build(truth: CompanyTruth, out_dir: Path, paragraph_budget: int = 900,
          suffix: str = "") -> tuple[Path, dict[str, int]]:
    pages: dict[str, int] = {}
    share = lambda k: max(2, int(paragraph_budget * BUDGET_SHARES[k]))
    story: list = []

    def heading(text: str, key: str | None = None) -> None:
        if key:
            story.append(PageMark(key, pages))
        story.append(Paragraph(text, H1))

    def body(text: str) -> None:
        story.append(Paragraph(text, BODY))

    def filler(count: int) -> None:
        for para in prose.paragraphs(count):
            body(para)

    # --- cover ---------------------------------------------------------
    story += [
        Spacer(1, 55 * mm),
        Paragraph(truth.name, TITLE),
        Paragraph("Confidential Information Memorandum", CENTRE),
        Spacer(1, 8 * mm),
        Paragraph(f"{truth.sector} — {truth.subsector}", CENTRE),
        Paragraph(f"{truth.country}", CENTRE),
        Spacer(1, 20 * mm),
        Paragraph("SYNTHETIC TEST FIXTURE. This company does not exist and "
                  "every figure in this document is invented.", CENTRE),
        PageBreak(),
    ]

    # --- 1. executive summary -----------------------------------------
    heading("1. Executive Summary", "executive_summary")
    body(truth.narrative["business_description"])
    # DEFECT: exec summary restates revenue on a different basis from the
    # financial summary. Both figures are correct. See the defect list.
    body(truth.narrative["exec_summary_revenue_note"])
    body(truth.narrative["problem"])
    body(truth.narrative["solution"])
    filler(share("executive_summary"))
    story.append(PageBreak())

    # --- 2. investment highlights -------------------------------------
    heading("2. Investment Highlights", "investment_highlights")
    for kpi in truth.kpis:
        story.append(Paragraph(f"<b>{kpi.label}.</b> {kpi.stated_text}", BODY))
    body(truth.narrative["differentiation"])
    filler(share("highlights"))
    story.append(PageBreak())

    # --- 3. business overview ------------------------------------------
    heading("3. Business Overview", "business_overview")
    body(truth.narrative["solution"])
    body(truth.narrative["growth_plans"])
    filler(share("business"))
    story.append(PageBreak())

    # --- 4. customers ---------------------------------------------------
    heading("4. Customers and Commercial Model", "customers")
    filler(share("customers"))
    story.append(PageBreak())

    # --- 5. market -------------------------------------------------------
    heading("5. Market", "market")
    filler(share("market"))
    story.append(PageBreak())

    # --- 6. financial summary — the extractable table ---------------------
    heading("6. Financial Summary", "financial_summary")
    body(f"The table below presents historical and forecast results. All "
         f"figures are stated in {truth.currency} millions unless otherwise "
         f"indicated.")
    story.append(Spacer(1, 4 * mm))
    story.append(PageMark("financial_table", pages))
    story.append(_financial_table(truth))
    story.append(Spacer(1, 5 * mm))
    body("Forecast periods reflect management's current operating plan and "
         "have not been audited or independently reviewed.")
    story.append(PageBreak())

    # --- 7. management ----------------------------------------------------
    heading("7. Management", "management")
    body(truth.narrative["management"])
    filler(share("management"))
    story.append(PageBreak())

    # --- 8. process -------------------------------------------------------
    heading("8. Process and Timetable", "process")
    filler(share("process"))
    story.append(PageBreak())

    # --- appendices: the bulk --------------------------------------------
    # Filler is scattered across many appendices rather than piled into
    # one, so finance-adjacent prose appears throughout the document.
    per_appendix = max(2, share("appendices") // len(prose.APPENDIX_TITLES))
    for title in prose.APPENDIX_TITLES:
        heading(title)
        filler(per_appendix)
        story.append(PageBreak())

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{truth.slug}_cim{suffix}.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"{truth.name} — Confidential Information Memorandum",
    )
    doc.build(story)
    return path, pages


def build_to_page_count(truth: CompanyTruth, out_dir: Path, target_pages: int,
                        suffix: str = "", tolerance: int = 3,
                        max_attempts: int = 6) -> tuple[Path, dict[str, int], int]:
    """Render, measure, adjust, repeat until the page count lands.

    Calibrating against the real rendered output rather than a paragraphs
    -per-page constant means the fixture stays the right length even if
    the styles change later. Deterministic: the same target always
    converges to the same document.
    """
    from pypdf import PdfReader

    budget = target_pages * 12
    best: tuple[int, int] | None = None   # (miss, budget)
    for _ in range(max_attempts):
        path, marks = build(truth, out_dir, paragraph_budget=budget, suffix=suffix)
        actual = len(PdfReader(str(path)).pages)
        miss = abs(actual - target_pages)
        if best is None or miss < best[0]:
            best = (miss, budget)
        if miss <= tolerance:
            return path, marks, actual
        budget = max(20, int(budget * target_pages / max(actual, 1)))
    # No attempt hit the tolerance: re-render the closest one, so the
    # file on disk is the best fit rather than the last thing tried.
    path, marks = build(truth, out_dir, paragraph_budget=best[1], suffix=suffix)
    return path, marks, len(PdfReader(str(path)).pages)
