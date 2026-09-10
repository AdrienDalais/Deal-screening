"""Generate the answer key for a company's fixtures.

The key has two independent halves, and conflating them would make both
meaningless.

**What each document says.** Extraction is scored on faithful
transcription — including of the documents' mistakes. An extractor that
"helpfully" corrects the mis-keyed cost of sales cell is failing, not
helping: silently repairing a document is precisely the behaviour this
system exists to prevent.

**What reconciliation should find.** The planted defects, one of which is
not an error at all and must stop being raised once the analyst has
explained it.

Because the key is generated from the same CompanyTruth as the documents,
it cannot drift when a fixture is regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl.utils import get_column_letter

from storage import enums as E
from tests.fixtures.build_workbook import FIRST_PERIOD_COL
from tests.fixtures.truth import CompanyTruth

# Rows the CIM prints, in order. The workbook prints every line item; the
# CIM prints a summary, as real ones do.
CIM_ROWS = ["arr", "revenue", "recurring_revenue", "non_recurring_revenue",
            "cogs", "gross_profit", "total_opex", "ebitda_adjustments",
            "adjusted_ebitda"]

# What a faithful extractor should call a row, given only its printed
# label. The CIM prints adjusted EBITDA as "EBITDA", so the correct
# extraction is `ebitda`, not `adjusted_ebitda` — discovering that the
# figure is actually adjusted is reconciliation's job, not extraction's.
CIM_METRIC_AS_LABELLED = {"adjusted_ebitda": "ebitda"}


def _round(value: float) -> float:
    return round(value, 4)


def build(truth: CompanyTruth, out_dir: Path, cim_pages: dict[str, int],
          workbook_rows: dict[str, int], cim_filename: str,
          workbook_filename: str,
          unreadable_pages: list[int] | None = None) -> Path:
    table_page = cim_pages["financial_table"]

    # --- what the CIM says --------------------------------------------
    cim_observations = []
    for metric in CIM_ROWS:
        try:
            item = truth.item(metric)
        except KeyError:
            continue
        for period in truth.periods:
            raw = item.values.get(period.label)
            if raw is None:
                continue
            printed = raw / truth.cim_unit.multiplier
            cim_observations.append({
                "metric": CIM_METRIC_AS_LABELLED.get(metric, metric),
                "original_label": item.cim_label,
                "value_original": _round(printed),
                "unit_original": truth.cim_unit.value,
                "currency_original": truth.currency,
                "value_standardised": _round(raw),
                "period_label": period.label,
                "period_start": period.start.isoformat(),
                "period_end": period.end.isoformat(),
                "period_type": E.PeriodType.FISCAL_YEAR.value,
                "basis": period.basis.value,
                # As *presented*. The CIM does not say this row is adjusted.
                "is_adjusted_as_presented": False,
                "source_page": table_page,
                "extraction_method": E.ExtractionMethod.LLM_STRUCTURED.value,
            })

    cim_claims = [
        {
            "claim_type": ("retention" if "retention" in k.key
                           else "customer_concentration" if "concentration" in k.key
                           else "other"),
            "subject_metric": k.key,
            "stated_value": k.value,
            "stated_unit": k.unit.value,
            "period_label": k.period_label,
            "claim_text": k.stated_text,
            "source_page": cim_pages["investment_highlights"],
        }
        for k in truth.kpis
    ]

    # --- what the workbook says ----------------------------------------
    workbook_observations = []
    for item in truth.line_items:
        row = workbook_rows.get(item.metric)
        if row is None:
            continue
        for index, period in enumerate(truth.periods):
            raw = item.values.get(period.label)
            if raw is None:
                continue
            printed = raw / truth.workbook_unit.multiplier
            if item.is_cost:
                printed = -printed
            standardised = -raw if item.is_cost else raw

            # The re-keying slip: the cell holds the CIM's scale.
            if (any(d.key == "thornbury_rekeying_scale_slip" for d in truth.defects)
                    and item.metric == "cogs" and period.label == "FY23"):
                printed = printed / 1000.0
                standardised = standardised / 1000.0

            workbook_observations.append({
                "metric": item.metric,
                "original_label": item.workbook_label,
                "value_original": _round(printed),
                "unit_original": truth.workbook_unit.value,
                "currency_original": truth.currency,
                "value_standardised": _round(standardised),
                "period_label": period.label,
                "period_start": period.start.isoformat(),
                "period_end": period.end.isoformat(),
                "period_type": E.PeriodType.FISCAL_YEAR.value,
                "basis": period.basis.value,
                "is_adjusted_as_presented": item.is_adjusted,
                "breakdown_axis": item.breakdown_axis.value,
                "source_sheet": "Scorecard",
                "source_cell": f"{get_column_letter(FIRST_PERIOD_COL + index)}{row}",
                "extraction_method": E.ExtractionMethod.OPENPYXL_DIRECT.value,
            })

    key = {
        "company": {
            "name": truth.name,
            "sector": truth.sector,
            "subsector": truth.subsector,
            "country": truth.country,
            "reporting_currency": truth.currency,
            "fiscal_year_end_month": truth.fiscal_year_end_month,
            "rule_of_40_variant": truth.rule_of_40_variant.value,
            "confidentiality": E.Confidentiality.SYNTHETIC.value,
        },
        "documents": [
            {
                "filename": cim_filename,
                "document_type": E.DocumentType.CIM.value,
                "printed_unit": truth.cim_unit.value,
                "section_pages": cim_pages,
                "observations": cim_observations,
                "claims": cim_claims,
            },
            {
                "filename": workbook_filename,
                "document_type": E.DocumentType.FINANCIALS_WORKBOOK.value,
                "printed_unit": truth.workbook_unit.value,
                "observations": workbook_observations,
                "claims": [],
            },
        ],
        "structured_sections": {
            # The cap table must total 100%. PAPER_SPEC B6 requires that
            # check; this is what it runs against.
            "cap_table": [
                {"name": h.name, "holding_pct": h.holding_pct,
                 "category": h.category}
                for h in truth.cap_table
            ],
            "cap_table_total_pct": round(
                sum(h.holding_pct for h in truth.cap_table), 2),
            # Opening + new + expansion - churn = closing, and closing
            # must also equal the ARR line in the financial summary.
            "arr_bridge": [
                {"period_label": b.period_label,
                 "opening": b.opening, "new_business": b.new_business,
                 "expansion": b.expansion, "churn": b.churn,
                 "closing_as_printed": b.closing,
                 "closing_implied_by_components": b.implied_closing,
                 "arr_in_financial_summary":
                     truth.item("arr").values.get(b.period_label)}
                for b in truth.bridge
            ],
            "retention": [
                {"period_label": r.period_label,
                 "gross_retention_pct": r.gross_retention_pct,
                 "net_retention_pct": r.net_retention_pct,
                 "logo_retention_pct": r.logo_retention_pct}
                for r in truth.retention
            ],
            "team": [{"name": m.name, "role": m.role, "joined": m.joined}
                     for m in truth.team],
            "competitors": [{"name": c.name, "positioning": c.positioning}
                            for c in truth.competitors],
        },
        # Pages whose content exists only as pixels. The system must
        # report these as unread. Treating them as empty is a failure:
        # a screening tool that silently omits what it could not parse
        # produces a confident answer with a hole in it.
        "pages_requiring_ocr_or_flagging": unreadable_pages or [],
        "expected_reconciliation_findings": [
            {
                "key": d.key,
                "kind": d.kind,
                "where": d.where,
                "description": d.description,
                "expected_detection": d.expected_detection,
                "is_genuine_error": d.is_genuine_error,
            }
            for d in truth.defects
        ],
        "notes": [
            "Extraction is scored against what each document literally "
            "says, defects included. Correcting a figure during extraction "
            "is a failure, not a help.",
            "Reconciliation is scored against expected_reconciliation_"
            "findings. One finding is not a genuine error and must stop "
            "being raised once explained (see docs/DECISIONS.md #011).",
            "Pages listed in pages_requiring_ocr_or_flagging hold figures "
            "that text extraction cannot recover. Reporting them as unread "
            "is correct; reporting them as empty is not.",
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "expected.json"
    path.write_text(json.dumps(key, indent=2) + "\n")
    return path
