"""Generate a CIM as a landscape slide deck, the way real ones arrive.

Measured against a real 84-page IM (structure only, via
tools/inspect_pdf.py):

    960 x 540 pt, 16:9              median 1,156 characters per page
    17% of pages under 200 chars    1 page with no text at all
    18% of text runs move UP        ~101k characters total
    546 tiny images, 20 large       one background repeated on 72 pages

Those are the targets. They matter because a slide deck is a different
extraction problem from a flowing document: text arrives as positioned
fragments with no guaranteed reading order, and some numbers live only
inside images.

Drawn on the canvas directly rather than through platypus, because slides
are positioned layouts, not flowing text.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from storage import enums as E
from tests.fixtures import prose, slide_art
from tests.fixtures.truth import CompanyTruth

W, H = 960.0, 540.0                      # 16:9, matching the real deck
# Tuned so the rendered deck matches the 18% reading-order
# disorder measured on a real IM. See tools/inspect_pdf.py.
DISORDER = 0.10

NAVY = HexColor("#3A527A")
INK = HexColor("#1A1A1A")
GREY = HexColor("#6A6A6A")
RULE = Color(0.80, 0.82, 0.86)


class Deck:
    def __init__(self, path: Path, title: str) -> None:
        self.c = pdfcanvas.Canvas(str(path), pagesize=(W, H))
        self.c.setTitle(title)
        self.page = 0
        self.marks: dict[str, int] = {}
        self._band = ImageReader(BytesIO(slide_art.background_band()))
        self._logos = [ImageReader(BytesIO(slide_art.logo_tile(i)))
                       for i in range(24)]
        self._marker = ImageReader(BytesIO(slide_art.bullet_marker()))

    # -- page furniture ------------------------------------------------
    def _start(self, footer: str | None = "Strictly private and confidential"):
        self.page += 1
        self.c.drawImage(self._band, 0, 0, width=W, height=H, mask=None)
        # Footer is drawn BEFORE the title, so extracted text runs move
        # from the bottom of the page back to the top. That is what
        # produces the reading-order disorder a real deck exhibits, and
        # it is deliberate rather than incidental.
        if footer:
            self.c.setFont("Helvetica", 7)
            self.c.setFillColor(GREY)
            self.c.drawString(40, 18, footer)
            self.c.drawRightString(W - 40, 18, str(self.page))

    def _end(self) -> None:
        self.c.showPage()

    def mark(self, key: str) -> None:
        self.marks[key] = self.page + 1

    # -- slide kinds ---------------------------------------------------
    def cover(self, truth: CompanyTruth) -> None:
        self._start(footer=None)
        self.c.setFillColor(NAVY)
        self.c.setFont("Helvetica-Bold", 40)
        self.c.drawString(70, 320, truth.name)
        self.c.setFont("Helvetica", 16)
        self.c.setFillColor(INK)
        self.c.drawString(70, 280, "Confidential Information Memorandum")
        self.c.setFont("Helvetica", 9)
        self.c.setFillColor(GREY)
        self.c.drawString(70, 120, "SYNTHETIC TEST FIXTURE — this company "
                                   "does not exist and every figure is invented.")
        self._end()

    def divider(self, title: str, blank: bool = False) -> None:
        """A section divider: a title and nothing else.

        17% of the real deck looks like this. `blank` produces the one
        page carrying no extractable text at all — a graphic-only slide
        that any honest pipeline must report as unread.
        """
        self._start(footer=None if blank else "Strictly private and confidential")
        if blank:
            self.c.drawImage(
                ImageReader(BytesIO(slide_art.logo_tile(9))),
                W / 2 - 120, H / 2 - 60, width=240, height=120, mask=None)
        else:
            self.c.setFillColor(NAVY)
            self.c.rect(0, H / 2 - 2, W, 2, stroke=0, fill=1)
            self.c.setFont("Helvetica-Bold", 28)
            self.c.drawString(70, H / 2 + 24, title)
        self._end()

    def _title(self, title: str, kicker: str | None = None) -> None:
        self.c.setFillColor(NAVY)
        self.c.setFont("Helvetica-Bold", 19)
        self.c.drawString(40, H - 58, title)
        if kicker:
            self.c.setFont("Helvetica", 10)
            self.c.setFillColor(GREY)
            self.c.drawString(40, H - 76, kicker)
        self.c.setStrokeColor(RULE)
        self.c.line(40, H - 86, W - 40, H - 86)

    def bullets(self, title: str, lines: list[str],
                kicker: str | None = None) -> None:
        """A dense two-column content slide, emitted in shuffled z-order.

        Two things here are deliberate and both matter for extraction.

        The slide is built from many small positioned text elements
        rather than a few long strings: a real deck averages ~44 separate
        runs per page, and that fragmentation is what makes reassembling
        a slide hard.

        And the elements are emitted in a seeded-shuffled order rather
        than top to bottom. A PowerPoint export writes text boxes in
        z-order, not reading order, which is why ~18% of runs in a real
        deck move UP the page. A fixture drawn tidily downwards would let
        us build an extractor that quietly relies on reading order and
        then fails on every real document.

        Seeded, so the shuffle is identical on every rebuild.
        """
        import random

        self._start()
        rng = random.Random(1000 + self.page)
        ops: list[tuple[float, float, str, float, str]] = []

        ops.append((40, H - 58, "Helvetica-Bold", 19, title))
        if kicker:
            ops.append((40, H - 76, "Helvetica", 10, kicker))
        ops.append((W - 300, H - 58, "Helvetica", 7,
                    title.split()[0][:18].upper()))

        columns = [(52.0, H - 118), (500.0, H - 118)]
        half = max(1, (len(lines) + 1) // 2)
        for (x, top), group in zip(columns, (lines[:half], lines[half:])):
            y = top
            for line in group:
                if y < 104:
                    break
                self.c.drawImage(self._marker, x - 14, y - 2,
                                 width=7, height=7, mask=None)
                for chunk in _wrap(line, 62):
                    if y < 104:
                        break
                    ops.append((x, y, "Helvetica", 8.5, chunk))
                    y -= 12
                y -= 7

        # A strip of small statistics, the kind that sits along the foot
        # of a real slide. More discrete runs, drawn out of order.
        for index, (label, value) in enumerate(
                (("Customers", "214"), ("NRR", "118%"),
                 ("Sites", "2 offices"), ("Founded", "2016"))):
            x = 60 + index * 205
            ops.append((x, 78, "Helvetica-Bold", 9, value))
            ops.append((x, 66, "Helvetica", 7, label))

        ops.append((60, 52, "Helvetica", 7, "Management information, unaudited."))
        ops.append((W - 240, 52, "Helvetica", 7, "Source: company information"))

        # A *partial* disturbance of reading order, not a full shuffle.
        # PowerPoint writes text boxes in creation order, which correlates
        # loosely with layout — so a real deck reads mostly top-down with
        # regular jumps, not at random. Full shuffling gave 48% disorder
        # against the 18% measured on a real deck, which would have made
        # the fixture harder than reality rather than equal to it.
        ops.sort(key=lambda op: (-op[1], op[0]))
        for _ in range(int(len(ops) * DISORDER)):
            i = rng.randrange(len(ops))
            j = rng.randrange(len(ops))
            ops[i], ops[j] = ops[j], ops[i]

        for x, y, font, size, text in ops:
            self.c.setFont(font, size)
            self.c.setFillColor(NAVY if font == "Helvetica-Bold" else INK)
            self.c.drawString(x, y, text)

        self.c.setStrokeColor(RULE)
        self.c.line(40, H - 86, W - 40, H - 86)
        self.c.line(46, 94, W - 46, 94)
        self._end()

    def table(self, title: str, header: list[str], rows: list[list[str]],
              kicker: str | None = None, col0: float = 190.0,
              colw: float = 88.0) -> None:
        self._start()
        self._title(title, kicker)
        y = H - 120
        self.c.setFont("Helvetica-Bold", 8.5)
        self.c.setFillColor(INK)
        for index, cell in enumerate(header):
            x = 46 if index == 0 else 46 + col0 + (index - 1) * colw
            (self.c.drawString if index == 0 else self.c.drawRightString)(
                x if index == 0 else x + colw - 8, y, cell)
        self.c.setStrokeColor(RULE)
        self.c.line(46, y - 6, W - 46, y - 6)
        y -= 22
        self.c.setFont("Helvetica", 8.5)
        for row in rows:
            for index, cell in enumerate(row):
                x = 46 if index == 0 else 46 + col0 + (index - 1) * colw
                (self.c.drawString if index == 0 else self.c.drawRightString)(
                    x if index == 0 else x + colw - 8, y, cell)
            y -= 16
        self._end()

    def bar_chart(self, title: str, values: list[tuple[str, float]],
                  note: str, unit: str = "") -> None:
        """A vector chart: bars are shapes, labels are real text.

        Extractable, but the labels arrive as fragments scattered across
        the page with no association to their axis. This is the common
        case in a real deck, and the harder one to parse correctly.
        """
        self._start()
        self._title(title)
        peak = max(v for _, v in values) or 1.0
        base, left, bw, gap = 140.0, 90.0, 74.0, 34.0
        self.c.setStrokeColor(RULE)
        self.c.line(left - 20, base, W - 60, base)
        for index, (label, value) in enumerate(values):
            x = left + index * (bw + gap)
            height = (value / peak) * 250.0
            self.c.setFillColor(NAVY if index % 2 == 0 else HexColor("#6E86AA"))
            self.c.rect(x, base, bw, height, stroke=0, fill=1)
            self.c.setFillColor(INK)
            self.c.setFont("Helvetica-Bold", 9)
            self.c.drawCentredString(x + bw / 2, base + height + 8,
                                     f"{value:,.1f}{unit}")
            self.c.setFont("Helvetica", 8.5)
            self.c.setFillColor(GREY)
            self.c.drawCentredString(x + bw / 2, base - 16, label)
        self.c.setFont("Helvetica", 8.5)
        self.c.setFillColor(GREY)
        for line in _wrap(note, 120)[:3]:
            self.c.drawString(46, 66, line)
        self._end()

    def image_slide(self, title: str, png: bytes, caption: str) -> None:
        """A slide whose figures exist only as pixels.

        Deliberately unreadable. The system must report the page as
        unread rather than treating it as empty.
        """
        self._start()
        self._title(title)
        self.c.drawImage(ImageReader(BytesIO(png)), 150, 80,
                         width=660, height=372, mask=None)
        self.c.setFont("Helvetica", 7.5)
        self.c.setFillColor(GREY)
        self.c.drawString(46, 62, caption)
        self._end()

    def logo_wall(self, title: str, count: int = 21) -> None:
        """Customer logos: many small images, almost no text.

        Real information that text extraction cannot see at all.
        """
        self._start()
        self._title(title)
        for index in range(count):
            col, row = index % 7, index // 7
            self.c.drawImage(self._logos[index % len(self._logos)],
                             52 + col * 128, 320 - row * 92,
                             width=96, height=48, mask=None)
        self.c.setFont("Helvetica", 8)
        self.c.setFillColor(GREY)
        self.c.drawString(46, 62, "Selected customers. Logos used with consent.")
        self._end()

    def save(self) -> dict[str, int]:
        self.c.save()
        return self.marks


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _money(value: float, unit: E.Unit) -> str:
    scaled = value / unit.multiplier
    return f"({abs(scaled):,.1f})" if scaled < 0 else f"{scaled:,.1f}"


CIM_ROWS = ["arr", "revenue", "recurring_revenue", "non_recurring_revenue",
            "cogs", "gross_profit", "total_opex", "ebitda_adjustments",
            "adjusted_ebitda"]


def build(truth: CompanyTruth, out_dir: Path, filler_slides: int = 26,
          suffix: str = "") -> tuple[Path, dict[str, int]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{truth.slug}_cim_slides{suffix}.pdf"
    deck = Deck(path, f"{truth.name} — Confidential Information Memorandum")
    filler = iter(prose.paragraphs(900))
    take = lambda n: [next(filler) for _ in range(n)]

    deck.cover(truth)
    deck.bullets("Important Notice", [
        "This document has been prepared solely for the purpose of assisting "
        "recipients in deciding whether to proceed with a further "
        "investigation of the company.",
        "No representation or warranty, express or implied, is given as to "
        "the accuracy or completeness of the information contained herein.",
        "Forecast information reflects management's current operating plan "
        "and has not been audited or independently reviewed.",
    ])
    deck.bullets("Contents", [
        "1. Executive Summary", "2. Business Overview", "3. Product",
        "4. Customers and Retention", "5. Market and Competition",
        "6. Financial Review", "7. Management and Organisation",
        "8. Ownership and Process", "9. Appendices",
    ])

    # --- 1. executive summary ------------------------------------------
    deck.divider("1. Executive Summary")
    deck.mark("executive_summary")
    deck.bullets("Executive Summary", [
        truth.narrative["business_description"],
        truth.narrative["exec_summary_revenue_note"],   # DEFECT: 15.1m
        truth.narrative["problem"],
    ], kicker="Overview")
    deck.mark("investment_highlights")
    deck.bullets("Investment Highlights",
                 [f"{k.label}. {k.stated_text}" for k in truth.kpis],
                 kicker="Key performance indicators")
    for para in take(3):
        deck.bullets("Executive Summary (continued)", [para] + take(5))

    # --- 2. business overview -------------------------------------------
    deck.divider("2. Business Overview")
    deck.bullets("Why the business exists", [truth.narrative["solution"]] + take(5))
    deck.bullets("Growth plans", [truth.narrative["growth_plans"]] + take(5))
    for _ in range(5):
        deck.bullets("Business Overview", take(6))

    # --- 3. product -------------------------------------------------------
    deck.divider("3. Product")
    deck.bullets("Differentiation", [truth.narrative["differentiation"]] + take(5))
    for _ in range(5):
        deck.bullets("Product", take(6))
    deck.mark("blank_divider")
    deck.divider("", blank=True)          # the one page with no text at all

    # --- 4. customers and retention ---------------------------------------
    deck.divider("4. Customers and Retention")
    deck.logo_wall("Selected Customers")
    if truth.retention:
        deck.mark("retention_table")
        deck.table(
            "Retention Analysis", ["%"] + [r.period_label for r in truth.retention],
            [["Gross revenue retention"] + [f"{r.gross_retention_pct:.0f}%"
                                            for r in truth.retention],
             ["Net revenue retention"] + [f"{r.net_retention_pct:.0f}%"
                                          for r in truth.retention],
             ["Logo retention"] + [f"{r.logo_retention_pct:.0f}%"
                                   for r in truth.retention]],
            kicker="Management analysis; not independently verified")
    for _ in range(4):
        deck.bullets("Customers", take(6))

    # --- 5. market and competition -----------------------------------------
    deck.divider("5. Market and Competition")
    if truth.competitors:
        deck.mark("competitive_landscape")
        deck.table("Competitive Landscape", ["Competitor", "Positioning", "Note"],
                   [[c.name[:34], c.positioning[:26], c.note[:48]]
                    for c in truth.competitors],
                   col0=250.0, colw=200.0)
    for _ in range(6):
        deck.bullets("Market", take(6))

    # --- 6. financial review -------------------------------------------------
    deck.divider("6. Financial Review")
    unit_word = {E.Unit.MILLIONS: "m", E.Unit.THOUSANDS: "k"}[truth.cim_unit]
    header = [f"{truth.currency}{unit_word}"] + [p.label for p in truth.periods]
    basis_row = [""] + ["Actual" if p.basis == E.Basis.ACTUAL else "Forecast"
                        for p in truth.periods]
    rows = [basis_row]
    for metric in CIM_ROWS:
        try:
            item = truth.item(metric)
        except KeyError:
            continue
        line = [item.cim_label]
        for period in truth.periods:
            raw = item.values.get(period.label)
            line.append("n.a." if raw is None
                        else _money(-raw if item.is_cost else raw, truth.cim_unit))
        rows.append(line)
    deck.mark("financial_table")
    deck.table("Financial Summary", header, rows,
               kicker="Historical results and management forecast")

    deck.mark("revenue_chart")
    revenue = truth.item("revenue")
    deck.bar_chart(
        "Revenue Growth",
        [(p.label, revenue.values[p.label] / truth.cim_unit.multiplier)
         for p in truth.periods if p.label in revenue.values],
        "Vector chart: labels are extractable text, though they arrive "
        "detached from their axis.", unit="m")

    if truth.bridge:
        deck.mark("arr_bridge")
        deck.table(
            "ARR Bridge", [f"{truth.currency}{unit_word}", "Opening", "New",
                           "Expansion", "Churn", "Closing"],
            [[b.period_label,
              _money(b.opening, truth.cim_unit),
              _money(b.new_business, truth.cim_unit),
              _money(b.expansion, truth.cim_unit),
              f"({b.churn / truth.cim_unit.multiplier:,.1f})",
              _money(b.closing, truth.cim_unit)] for b in truth.bridge],
            kicker="Movement in annual recurring revenue", col0=120.0, colw=110.0)

    # A chart whose numbers exist only as pixels.
    deck.mark("unreadable_chart")
    gross = truth.item("gross_profit")
    deck.image_slide(
        "Gross Profit by Year",
        slide_art.unreadable_chart(
            [(p.label, gross.values[p.label] / truth.cim_unit.multiplier)
             for p in truth.periods if p.label in gross.values],
            "Gross profit"),
        "Chart supplied by management. Figures shown in the chart above are "
        "not reproduced elsewhere in this document.")
    for _ in range(3):
        deck.bullets("Financial Review", take(6))

    # --- 7. management ---------------------------------------------------------
    deck.divider("7. Management and Organisation")
    if truth.team:
        deck.mark("team")
        deck.table("Management Team", ["Name", "Role", "Joined", "Background"],
                   [[m.name, m.role[:28], m.joined, m.background[:52]]
                    for m in truth.team], col0=150.0, colw=210.0)
    deck.bullets("Organisation", [truth.narrative["management"]] + take(5))
    for _ in range(3):
        deck.bullets("Management", take(6))

    # --- 8. ownership and process ------------------------------------------------
    deck.divider("8. Ownership and Process")
    if truth.cap_table:
        deck.mark("cap_table")
        deck.table("Shareholder Register", ["Shareholder", "Holding", "Category"],
                   [[s.name[:44], f"{s.holding_pct:.1f}%", s.category]
                    for s in truth.cap_table]
                   + [["Total", f"{sum(s.holding_pct for s in truth.cap_table):.1f}%", ""]],
                   col0=300.0, colw=130.0)
    for _ in range(4):
        deck.bullets("Process", take(6))

    # --- 9. appendices -------------------------------------------------------------
    deck.divider("9. Appendices")
    for index in range(filler_slides):
        title = prose.APPENDIX_TITLES[index % len(prose.APPENDIX_TITLES)]
        deck.bullets(title, take(6))

    return path, deck.save()


def build_to_page_count(truth: CompanyTruth, out_dir: Path, target_pages: int,
                        suffix: str = "", tolerance: int = 2,
                        max_attempts: int = 8) -> tuple[Path, dict[str, int], int]:
    """Calibrate against the rendered page count, as the prose builder does."""
    from pypdf import PdfReader

    filler = max(0, target_pages - 58)
    best: tuple[int, int] | None = None
    for _ in range(max_attempts):
        path, marks = build(truth, out_dir, filler_slides=filler, suffix=suffix)
        actual = len(PdfReader(str(path)).pages)
        miss = abs(actual - target_pages)
        if best is None or miss < best[0]:
            best = (miss, filler)
        if miss <= tolerance:
            return path, marks, actual
        filler = max(0, filler + (target_pages - actual))
    path, marks = build(truth, out_dir, filler_slides=best[1], suffix=suffix)
    return path, marks, len(PdfReader(str(path)).pages)
