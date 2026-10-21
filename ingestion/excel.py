"""Read a financials workbook directly, preserving cell references.

No model involved. A fixed-layout spreadsheet is a solved problem, and
sending it to an LLM would add cost, latency and a failure mode in
exchange for nothing. Extraction accuracy here should be 100%, which also
makes this the control against which LLM extraction from PDFs is judged.

What this does NOT do is correct anything. If a cell holds 3.5 in a sheet
denominated in thousands, this reports 3.5. Noticing that it should have
been 3,500 is reconciliation's job. An extractor that quietly repairs
figures destroys the evidence that the document was wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

FIRST_PERIOD_COLUMN = 4   # column D, matching the fixture layout

from ingestion.labels import is_cost_metric, map_label
from storage.enums import (
    Basis, BreakdownAxis, ExtractionMethod, PeriodType, Unit,
)

UNIT_WORDS = {
    "units": Unit.UNITS, "thousands": Unit.THOUSANDS,
    "millions": Unit.MILLIONS, "billions": Unit.BILLIONS,
    "k": Unit.THOUSANDS, "m": Unit.MILLIONS, "000s": Unit.THOUSANDS,
}
# Metrics that identify each cut of the cost base when a sheet presents
# both. Used only to decide which axis a row belongs to on a sheet that
# has been shown to carry two.
_NATURE_MARKERS = {"personnel_expenses", "non_personnel_expenses"}
_FUNCTION_MARKERS = {"product_and_engineering", "sales_and_marketing",
                     "general_and_admin", "implementation", "other_opex"}


def _axis_assignment(metrics: set[str]) -> dict[str, BreakdownAxis]:
    """Decide which breakdown axis each expense row belongs to.

    The axis is a property of the sheet, not of the metric name. One
    company's "Personnel" row sits inside a functional breakdown
    alongside S&M and G&A; another's is one half of a breakdown by
    nature presented beside a functional one. A static map would
    double count the first and miss the second.

    So: a sheet carrying markers of *both* cuts is treated as dual-axis
    and each row assigned accordingly. A sheet carrying one cut has all
    its expense rows on a single axis, whatever they are called.
    """
    has_nature = bool(metrics & {"non_personnel_expenses"})
    has_function = bool(metrics & (_FUNCTION_MARKERS - {"other_opex"}))

    assignment: dict[str, BreakdownAxis] = {"total_opex": BreakdownAxis.TOTAL}
    if has_nature and has_function:
        for metric in metrics & _NATURE_MARKERS:
            assignment[metric] = BreakdownAxis.BY_NATURE
        for metric in metrics & _FUNCTION_MARKERS:
            assignment[metric] = BreakdownAxis.BY_FUNCTION
    else:
        for metric in (metrics & (_NATURE_MARKERS | _FUNCTION_MARKERS)):
            assignment[metric] = BreakdownAxis.BY_FUNCTION
    return assignment


MONTH_NUMBER = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
     "Nov", "Dec"], start=1)}


@dataclass
class ExtractedObservation:
    metric: str
    original_label: str
    value_original: float | None
    unit_original: Unit
    currency_original: str | None
    value_standardised: float | None
    period_label: str
    period_start: date | None
    period_end: date | None
    period_type: PeriodType
    basis: Basis
    source_sheet: str
    source_cell: str
    breakdown_axis: BreakdownAxis = BreakdownAxis.NOT_APPLICABLE
    extraction_method: ExtractionMethod = ExtractionMethod.OPENPYXL_DIRECT
    needs_review: bool = False
    ambiguity_reason: str | None = None
    is_adjusted_as_presented: bool = False


@dataclass
class ExtractedWorkbook:
    path: Path
    sheet_name: str
    currency: str | None
    unit: Unit | None
    fiscal_year_end_month: int | None
    observations: list[ExtractedObservation] = field(default_factory=list)
    unmapped_labels: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _header_block(sheet: Worksheet) -> dict[str, str]:
    """Read the labelled header block at the top-left of the sheet."""
    found: dict[str, str] = {}
    for row in range(1, 12):
        label = sheet.cell(row=row, column=2).value
        value = sheet.cell(row=row, column=3).value
        if isinstance(label, str) and value is not None:
            found[label.strip().lower()] = str(value).strip()
    return found


def _period_header_row(sheet: Worksheet) -> int | None:
    """The row holding the period labels: FY22A, FY23A and so on."""
    for row in range(1, 20):
        hits = 0
        for col in range(3, 20):
            value = sheet.cell(row=row, column=col).value
            if isinstance(value, str) and value.strip().upper().startswith("FY"):
                hits += 1
        if hits >= 2:
            return row
    return None


def _basis_spans(sheet: Worksheet, header_row: int) -> dict[int, str]:
    """Which columns each merged basis header covers.

    Basis in a real model is signalled by a merged cell sitting a row or
    two above the numbers, not by a suffix on every column. This reads
    that merge.
    """
    spans: dict[int, str] = {}
    for merged in sheet.merged_cells.ranges:
        if merged.min_row >= header_row:
            continue
        text = sheet.cell(row=merged.min_row, column=merged.min_col).value
        if not isinstance(text, str):
            continue
        for col in range(merged.min_col, merged.max_col + 1):
            spans[col] = text.strip()
    return spans


def _basis_from_suffix(label: str) -> Basis | None:
    stripped = label.strip().upper()
    if stripped.endswith("A"):
        return Basis.ACTUAL
    if stripped.endswith(("E", "F", "P")):
        return Basis.MANAGEMENT_FORECAST
    return None


def _basis_from_span(text: str | None) -> Basis | None:
    if not text:
        return None
    lowered = text.lower()
    if "historic" in lowered or "actual" in lowered:
        return Basis.ACTUAL
    if "forecast" in lowered or "budget" in lowered or "plan" in lowered:
        return Basis.MANAGEMENT_FORECAST
    return None


def _period_dates(label: str, year_end_month: int | None
                  ) -> tuple[date | None, date | None]:
    """Turn FY24 into real dates, using the company's year end.

    A June year end means FY24 runs 1 Jul 2023 to 30 Jun 2024. Without
    this, comparing two companies on "FY24" silently compares different
    twelve-month windows.
    """
    digits = "".join(c for c in label if c.isdigit())
    if not digits or year_end_month is None:
        return None, None
    year = 2000 + int(digits[:2]) if len(digits) <= 2 else int(digits[:4])
    end_day = 31 if year_end_month in (1, 3, 5, 7, 8, 10, 12) else 30
    if year_end_month == 2:
        end_day = 28
    end = date(year, year_end_month, end_day)
    start_year = year if year_end_month == 12 else year - 1
    start_month = 1 if year_end_month == 12 else year_end_month + 1
    if start_month > 12:
        start_month, start_year = 1, year
    return date(start_year, start_month, 1), end


def extract(path: Path | str, sheet_name: str | None = None
            ) -> ExtractedWorkbook:
    path = Path(path)
    workbook = load_workbook(path, data_only=False)
    sheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]

    header = _header_block(sheet)
    currency = header.get("currency")
    unit = UNIT_WORDS.get((header.get("units") or "").lower())
    year_end = MONTH_NUMBER.get((header.get("year end (eop)") or "")[:3].title())

    result = ExtractedWorkbook(path=path, sheet_name=sheet.title,
                               currency=currency, unit=unit,
                               fiscal_year_end_month=year_end)
    if year_end is None:
        # Without a year end, FY24 cannot be turned into real dates, and
        # two companies compared on "FY24" may be covering different
        # twelve-month windows. Say so rather than leaving the dates
        # quietly empty.
        result.warnings.append(
            "The sheet does not state a fiscal year end, so period labels "
            "cannot be resolved to dates.")
    if unit is None:
        # A sheet whose scale is only implied is not safely readable.
        result.warnings.append(
            "The sheet does not state its units. Every figure on it is "
            "ambiguous by a factor of 1,000 or more.")

    header_row = _period_header_row(sheet)
    if header_row is None:
        result.warnings.append("No period header row found.")
        return result

    spans = _basis_spans(sheet, header_row)
    columns: list[tuple[int, str, Basis, str | None]] = []
    for col in range(3, 25):
        label = sheet.cell(row=header_row, column=col).value
        if not isinstance(label, str) or not label.strip().upper().startswith("FY"):
            continue
        from_suffix = _basis_from_suffix(label)
        from_span = _basis_from_span(spans.get(col))

        ambiguity = None
        if from_suffix and from_span and from_suffix != from_span:
            # THE LARKSPUR DEFECT. Two signals in one sheet disagree.
            # Record both and flag; do not pick a winner. Which one is
            # right is a judgement, and judgements belong to the analyst.
            ambiguity = (
                f"Column {get_column_letter(col)} is labelled "
                f"{label.strip()} (reads as {from_suffix.value}) but sits "
                f"under a merged header reading {spans.get(col)!r} "
                f"(reads as {from_span.value})."
            )
        basis = from_span or from_suffix or Basis.ACTUAL
        columns.append((col, label.strip().rstrip("AEFPaefp") or label.strip(),
                        basis, ambiguity))

    present: set[str] = set()
    for row in range(header_row + 1, sheet.max_row + 1):
        label = sheet.cell(row=row, column=2).value
        if not isinstance(label, str) or not label.strip():
            continue
        if label.strip().lower() == "checks":
            break
        mapped = map_label(label)
        if mapped:
            present.add(mapped)
    axes = _axis_assignment(present)

    for row in range(header_row + 1, sheet.max_row + 1):
        label = sheet.cell(row=row, column=2).value
        if not isinstance(label, str) or not label.strip():
            continue
        if label.strip().lower() == "checks":
            # Everything below is controls, not figures. Their results
            # are read separately by read_checks(); transcribing them as
            # observations would put a validation result into the ledger
            # as though it were something the document reported.
            break
        metric = map_label(label)
        if metric is None:
            result.unmapped_labels.append(label.strip())
            continue

        for col, period_label, basis, ambiguity in columns:
            cell = sheet.cell(row=row, column=col)
            value = cell.value
            if value is None or isinstance(value, str):
                continue  # formulas and text are not figures to transcribe

            standardised = None
            if unit is not None and unit.multiplier is not None:
                standardised = value * unit.multiplier
            if is_cost_metric(metric) and standardised is not None:
                standardised = -standardised   # stored as positive magnitude

            start, end = _period_dates(period_label, year_end)
            result.observations.append(ExtractedObservation(
                metric=metric,
                original_label=label.strip(),
                value_original=float(value),
                unit_original=unit or Unit.UNITS,
                currency_original=currency,
                value_standardised=standardised,
                period_label=period_label,
                period_start=start, period_end=end,
                period_type=PeriodType.FISCAL_YEAR,
                basis=basis,
                source_sheet=sheet.title,
                source_cell=f"{get_column_letter(col)}{row}",
                breakdown_axis=axes.get(metric, BreakdownAxis.NOT_APPLICABLE),
                needs_review=ambiguity is not None,
                ambiguity_reason=ambiguity,
                is_adjusted_as_presented="adj" in label.strip().lower(),
            ))

    return result


@dataclass
class CheckRow:
    """One control from the workbook's checks block.

    `evaluable` is the field that matters. A check whose formula cannot
    be resolved must be reported in words as not evaluable — never
    rendered blank, as a dash, or as an error code, because all three
    read as "fine" to a tired reader.
    """

    label: str
    source_cell: str
    formula: str | None
    evaluable: bool
    reason: str | None = None


# Functions and references openpyxl can hand us that indicate a formula
# cannot resolve: a defined name that does not exist resolves to nothing.
def read_checks(path: Path | str, sheet_name: str | None = None
                ) -> list[CheckRow]:
    """Read the checks block, reporting which controls actually work."""
    path = Path(path)
    workbook = load_workbook(path, data_only=False)
    sheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]

    defined_names = set(workbook.defined_names.keys())
    rows: list[CheckRow] = []
    in_checks = False

    for row in range(1, sheet.max_row + 1):
        label = sheet.cell(row=row, column=2).value
        if isinstance(label, str) and label.strip().lower() == "checks":
            in_checks = True
            continue
        if not in_checks or not isinstance(label, str) or not label.strip():
            continue

        cell = sheet.cell(row=row, column=FIRST_PERIOD_COLUMN)
        formula = cell.value if isinstance(cell.value, str) else None
        evaluable, reason = True, None

        if formula is None:
            evaluable = False
            reason = "The check has no formula in its first period column."
        else:
            # A bare word in a formula that is not a defined name and not
            # a cell reference cannot resolve — the sheet displays an
            # error while presenting the row as a working control.
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", formula):
                if re.fullmatch(r"[A-Z]{1,3}\d+", token):
                    continue
                if token in defined_names:
                    continue
                evaluable = False
                reason = (
                    f"The formula references {token!r}, which is neither a "
                    f"cell nor a defined name in this workbook. The check "
                    f"cannot be evaluated.")
                break

        rows.append(CheckRow(label=label.strip(),
                             source_cell=f"{get_column_letter(FIRST_PERIOD_COLUMN)}{row}",
                             formula=formula, evaluable=evaluable,
                             reason=reason))
    return rows
