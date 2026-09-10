"""Generate a financials workbook from a CompanyTruth.

Layout follows docs/PAPER_SPEC.md Part B: a header block stating currency
and units, a merged header separating historicals from forecasts, one
column per period, one row per line item, and a checks block.

Costs are written negative, matching the convention real working models
use, so that gross profit is revenue *plus* cost of sales.

Defects are applied here, explicitly and by key, so that every distortion
in the output can be traced to one line of code.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from storage import enums as E
from tests.fixtures.truth import CompanyTruth

FIRST_PERIOD_COL = 4          # column D
PERIOD_HEADER_ROW = 8
LABEL_COL = 2                 # column B
BOLD = Font(bold=True)
UNDERLINE = Border(bottom=Side(style="thin"))


def _scaled(value: float, unit: E.Unit) -> float:
    """Whole units -> the workbook's scale."""
    return round(value / unit.multiplier, 4)


def build(truth: CompanyTruth, out_dir: Path) -> tuple[Path, dict[str, int]]:
    """Returns the path and a metric -> row-number map.

    The row map lets the answer key cite the exact cell each figure was
    written to. Hardcoding cell references in the key would break the
    moment a line item was added above them.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Scorecard"

    # --- header block ------------------------------------------------
    # Units are stated. The real template omitted them; PAPER_SPEC B1
    # makes them mandatory, and the generator cannot write a sheet
    # without one.
    header = [
        ("Company", truth.name),
        ("Currency", truth.currency),
        ("Units", truth.workbook_unit.value),
        ("Year end (EoP)", ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                            "Jul", "Aug", "Sep", "Oct", "Nov",
                            "Dec"][truth.fiscal_year_end_month]),
    ]
    for offset, (label, value) in enumerate(header):
        ws.cell(row=2 + offset, column=LABEL_COL, value=label).font = BOLD
        ws.cell(row=2 + offset, column=LABEL_COL + 1, value=value)

    # --- period headers ----------------------------------------------
    # A merged cell spanning the actual columns, and another spanning the
    # forecasts. This is how real models signal basis: not with a suffix
    # on every column, but with a heading several rows above.
    header_row, period_row = 7, 8
    actual_cols, forecast_cols = [], []
    for index, period in enumerate(truth.periods):
        col = FIRST_PERIOD_COL + index
        suffix = "A" if period.basis == E.Basis.ACTUAL else "E"
        cell = ws.cell(row=period_row, column=col, value=f"{period.label}{suffix}")
        cell.font = BOLD
        cell.alignment = Alignment(horizontal="right")
        cell.border = UNDERLINE
        (actual_cols if period.basis == E.Basis.ACTUAL else forecast_cols).append(col)

    def _span(cols: list[int], text: str) -> None:
        if not cols:
            return
        first, last = min(cols), max(cols)
        ws.merge_cells(start_row=header_row, start_column=first,
                       end_row=header_row, end_column=last)
        cell = ws.cell(row=header_row, column=first, value=text)
        cell.font = BOLD
        cell.alignment = Alignment(horizontal="center")

    _span(actual_cols, "Historicals")
    _span(forecast_cols, "Management forecast")

    # --- line items ---------------------------------------------------
    row = period_row + 2
    row_of_metric: dict[str, int] = {}

    for item in truth.line_items:
        ws.cell(row=row, column=LABEL_COL, value=item.workbook_label)
        for index, period in enumerate(truth.periods):
            raw = item.values.get(period.label)
            if raw is None:
                continue
            value = _scaled(raw, truth.workbook_unit)
            if item.is_cost:
                value = -value

            # ---- DEFECT: thornbury_rekeying_scale_slip --------------
            # FY23 cost of sales re-keyed at the CIM's scale (millions)
            # into a sheet denominated in thousands.
            if (any(d.key == "thornbury_rekeying_scale_slip" for d in truth.defects)
                    and item.metric == "cogs" and period.label == "FY23"):
                value = value / 1000.0

            ws.cell(row=row, column=FIRST_PERIOD_COL + index, value=value)
        row_of_metric[item.metric] = row
        row += 1

    # --- checks -------------------------------------------------------
    # Every check is a live formula with a stated expectation. A check
    # that cannot be evaluated must say so in words, never render blank
    # or as an error code (PAPER_SPEC B6).
    row += 1
    ws.cell(row=row, column=LABEL_COL, value="Checks").font = BOLD
    row += 1

    checks = [
        ("Revenue less components (expect 0)", "revenue",
         ["recurring_revenue", "non_recurring_revenue"]),
        ("Gross profit less revenue and COGS (expect 0)", "gross_profit",
         ["revenue", "cogs"]),
        ("Total OPEX less components (expect 0)", "total_opex",
         ["personnel_expenses", "sales_and_marketing", "general_and_admin"]),
    ]
    for label, total_metric, parts in checks:
        if total_metric not in row_of_metric:
            continue
        if any(p not in row_of_metric for p in parts):
            ws.cell(row=row, column=LABEL_COL, value=label)
            ws.cell(row=row, column=FIRST_PERIOD_COL,
                    value="not evaluable: component row missing")
            row += 1
            continue
        ws.cell(row=row, column=LABEL_COL, value=label)
        for index in range(len(truth.periods)):
            col = get_column_letter(FIRST_PERIOD_COL + index)
            total_ref = f"{col}{row_of_metric[total_metric]}"
            part_refs = "+".join(f"{col}{row_of_metric[p]}" for p in parts)
            ws.cell(row=row, column=FIRST_PERIOD_COL + index,
                    value=f"={total_ref}-({part_refs})")
        row += 1

    ws.column_dimensions["B"].width = 34
    for index in range(len(truth.periods)):
        ws.column_dimensions[get_column_letter(FIRST_PERIOD_COL + index)].width = 13

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{truth.slug}_financials.xlsx"
    wb.save(path)
    return path, row_of_metric
