"""Calderwood Health — synthetic fixture company 3 of 3.

INVENTED. Nothing here derives from a real deal.

US healthcare software, USD, **March year end**. FY24 runs 1 April 2023
to 31 March 2024.

Planted defects
---------------
1. two documents disagree on the same year's revenue. The CIM shows FY24
   revenue of 31.8; management accounts issued later show 30.9, restated
   to exclude a divested clinic services line. Both are correct on their
   own terms, and the difference is material.
2. overlapping expense breakdowns. Operating costs are presented twice —
   by nature and by function — for the same cost base. Summing across
   both axes double counts the entire opex line.
3. a check formula that cannot be evaluated, displayed as though it were
   a working control.
"""

from __future__ import annotations

from datetime import date

from storage import enums as E
from tests.fixtures.truth import (
    BridgeRow, CompanyTruth, Competitor, Defect, Kpi, LineItem, Period,
    RetentionRow, Shareholder, TeamMember,
)

M = 1_000_000.0
LABELS = ["FY22", "FY23", "FY24", "FY25", "FY26", "FY27"]


def _periods() -> list[Period]:
    out = []
    for index, label in enumerate(LABELS):
        end_year = 2022 + index
        out.append(Period(
            label=label,
            start=date(end_year - 1, 4, 1),
            end=date(end_year, 3, 31),
            basis=E.Basis.ACTUAL if index < 3 else E.Basis.MANAGEMENT_FORECAST,
        ))
    return out


def _v(*millions: float) -> dict[str, float]:
    return {lbl: round(m * M) for lbl, m in zip(LABELS, millions)}


def _line_items() -> list[LineItem]:
    return [
        LineItem("arr", "ARR", "ARR",
                 _v(17.0, 21.0, 25.4, 30.5, 36.2, 42.5)),
        LineItem("recurring_revenue", "Subscription and support",
                 "Recurring Revenue",
                 _v(15.8, 19.4, 23.2, 28.1, 33.4, 39.3)),
        LineItem("non_recurring_revenue", "Professional services",
                 "Non-Recurring Revenue",
                 _v(6.7, 7.6, 8.6, 9.4, 10.6, 11.7)),
        LineItem("revenue", "Total revenue", "Revenue",
                 _v(22.5, 27.0, 31.8, 37.5, 44.0, 51.0)),
        LineItem("cogs", "Cost of revenue", "COGS",
                 _v(7.9, 9.2, 10.6, 12.3, 14.1, 16.0), is_cost=True),
        LineItem("gross_profit", "Gross profit", "Gross profit",
                 _v(14.6, 17.8, 21.2, 25.2, 29.9, 35.0)),

        # --- axis 1: by nature ------------------------------------------
        LineItem("personnel_expenses", "Personnel", "Personnel",
                 _v(9.0, 10.5, 12.0, 13.8, 15.6, 17.5), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_NATURE),
        LineItem("non_personnel_expenses", "Non-personnel", "Non-Personnel",
                 _v(5.4, 6.3, 7.1, 8.0, 9.0, 10.0), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_NATURE),

        # --- axis 2: by function, the SAME cost base --------------------
        # Summing these alongside the two rows above double counts every
        # dollar of operating cost. This is why breakdown_axis exists.
        LineItem("product_and_engineering", "Product and engineering",
                 "Product", _v(5.2, 6.1, 6.9, 7.9, 8.9, 10.0), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("sales_and_marketing", "Sales and marketing", "S&M",
                 _v(5.6, 6.5, 7.4, 8.4, 9.5, 10.6), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("general_and_admin", "General and administrative", "G&A",
                 _v(3.6, 4.2, 4.8, 5.5, 6.2, 6.9), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),

        LineItem("total_opex", "Total operating expenses", "Total OPEX",
                 _v(14.4, 16.8, 19.1, 21.8, 24.6, 27.5), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.TOTAL),
        LineItem("ebitda_adjustments", "Transaction and other items",
                 "Adjustments", _v(0.5, 0.6, 0.7, 0.0, 0.0, 0.0)),
        LineItem("adjusted_ebitda", "Adjusted EBITDA", "Adj. EBITDA",
                 _v(0.7, 1.6, 2.8, 3.4, 5.3, 7.5),
                 is_adjusted=True,
                 adjustment_note="Pre transaction costs and other items."),
    ]


def _management_accounts() -> dict[str, dict[str, float]]:
    """Figures as restated in management accounts issued after the CIM.

    FY24 revenue is 30.9 rather than 31.8: a clinic services line was
    divested during the year and has been taken out of continuing
    operations. Gross profit and EBITDA move with it.

    Neither document is wrong. The system's job is to show both and let
    the analyst record which basis the paper is written on.
    """
    return {
        "revenue": {"FY24": round(30.9 * M)},
        "non_recurring_revenue": {"FY24": round(7.7 * M)},
        "gross_profit": {"FY24": round(20.6 * M)},
        "adjusted_ebitda": {"FY24": round(2.5 * M)},
    }


def _kpis() -> list[Kpi]:
    return [
        Kpi("gross_retention", "Gross revenue retention",
            "Gross revenue retention of 92% in FY24", 92.0, E.Unit.PERCENT, "FY24"),
        Kpi("net_retention", "Net revenue retention",
            "Net revenue retention of 111% in FY24", 111.0, E.Unit.PERCENT, "FY24"),
        Kpi("customer_count", "Customers",
            "342 provider organisations as at 31 March 2024",
            342, E.Unit.COUNT, "FY24"),
        Kpi("top_10_concentration", "Top 10 customer concentration",
            "The top ten customers represent 26% of ARR",
            26.0, E.Unit.PERCENT, "FY24"),
        Kpi("employees", "Employees", "284 employees across three sites",
            284, E.Unit.COUNT, "FY24"),
    ]


def _bridge() -> list[BridgeRow]:
    return [
        BridgeRow("FY23", opening=17.0 * M, new_business=4.1 * M,
                  expansion=1.8 * M, churn=1.9 * M, closing=21.0 * M),
        BridgeRow("FY24", opening=21.0 * M, new_business=4.4 * M,
                  expansion=2.2 * M, churn=2.2 * M, closing=25.4 * M),
    ]


def _retention() -> list[RetentionRow]:
    return [RetentionRow("FY22", 90.0, 106.0, 87.0),
            RetentionRow("FY23", 91.0, 109.0, 88.0),
            RetentionRow("FY24", 92.0, 111.0, 89.0)]


def _cap_table() -> list[Shareholder]:
    return [
        Shareholder("Marchmont Health Partners LP", 41.0, "institutional"),
        Shareholder("J. Okonkwo (CEO)", 12.0, "founder"),
        Shareholder("L. Petrosyan (co-founder)", 10.5, "founder"),
        Shareholder("Ridgeline Capital", 16.0, "institutional"),
        Shareholder("Former owners of acquired businesses", 8.5, "other"),
        Shareholder("Employee equity plan", 12.0, "employee"),
    ]


def _team() -> list[TeamMember]:
    return [
        TeamMember("J. Okonkwo", "Chief Executive Officer", "2017",
                   "Joined at the Series A; previously a healthcare operator."),
        TeamMember("L. Petrosyan", "Chief Product Officer", "2014",
                   "Co-founder. Clinical informatics background."),
        TeamMember("R. Castellanos", "Chief Financial Officer", "2020",
                   "Previously CFO of a healthcare services roll-up."),
        TeamMember("A. Dunleavy", "Chief Technology Officer", "2019",
                   "Previously engineering director at a claims processor."),
        TeamMember("H. Iwasaki", "Chief Commercial Officer", "2021",
                   "Enterprise sales leadership across provider networks."),
    ]


def _competitors() -> list[Competitor]:
    return [
        Competitor("Integrated EHR vendors", "Incumbent",
                   "Bundled modules; deep entrenchment, slow to change."),
        Competitor("Whitlock Care Systems", "Direct",
                   "Similar segment; stronger in the Midwest."),
        Competitor("Pentworth Analytics", "Adjacent",
                   "Analytics only; frequently deployed alongside."),
        Competitor("Manual processes", "Status quo",
                   "Still prevalent among smaller provider groups."),
    ]


def _narrative() -> dict[str, str]:
    return {
        "business_description": (
            "Calderwood Health provides workflow and revenue-cycle software "
            "to mid-sized provider organisations in the United States, "
            "covering scheduling, coding support and claims submission."
        ),
        "problem": (
            "Provider organisations lose materially to denied and "
            "under-coded claims. Existing systems are configured once and "
            "rarely revisited."
        ),
        "solution": (
            "A platform that monitors coding and claim outcomes "
            "continuously and surfaces corrective actions before "
            "submission."
        ),
        "differentiation": (
            "Integrates with the major electronic health record systems "
            "rather than replacing them; priced on realised recovery."
        ),
        "growth_plans": (
            "Expansion into larger provider networks, a denials analytics "
            "module, and selective acquisition of regional competitors."
        ),
        "management": (
            "Institutionally backed since 2017, with a majority holder and "
            "a management team recruited largely from healthcare services."
        ),
        "exec_summary_revenue_note": (
            "FY24 total revenue of USD 31.8m, representing growth of 18% "
            "over the prior year."
        ),
    }


def _defects() -> list[Defect]:
    return [
        Defect(
            key="calderwood_documents_disagree_on_revenue",
            kind="cross_document_disagreement",
            where="CIM FY24 revenue 31.8 vs management accounts 30.9",
            description=(
                "The CIM reports FY24 revenue of 31.8. Management accounts "
                "issued afterwards report 30.9, restated to exclude a "
                "divested clinic services line. Gross profit and adjusted "
                "EBITDA move with it."
            ),
            expected_detection=(
                "Two live observations for revenue FY24 from different "
                "documents, differing by 0.9. Both must be retained and "
                "shown side by side; neither may be silently preferred."
            ),
        ),
        Defect(
            key="calderwood_overlapping_opex_breakdowns",
            kind="overlapping_expense_breakdown",
            where="workbook, operating expenses presented on two axes",
            description=(
                "Operating costs are presented both by nature (personnel, "
                "non-personnel) and by function (product, S&M, G&A) for the "
                "same cost base. Each axis sums to total opex on its own."
            ),
            expected_detection=(
                "Summing every expense row gives twice total operating "
                "expenses. Each axis must reconcile to the total "
                "independently, and only one may be used in any "
                "calculation."
            ),
        ),
        Defect(
            key="calderwood_inert_check_formula",
            kind="check_cannot_be_evaluated",
            where="workbook, checks block",
            description=(
                "A check row references a named range that does not exist, "
                "so it reports an error permanently while being displayed "
                "as though it were a working control."
            ),
            expected_detection=(
                "A check that cannot be evaluated must be reported in "
                "words as not evaluable. Rendering it blank, as a dash, or "
                "as an error code lets it read as decoration."
            ),
        ),
    ]


CALDERWOOD = CompanyTruth(
    name="Calderwood Health",
    sector="B2B Software",
    subsector="Healthcare Revenue Cycle Management",
    country="United States",
    currency="USD",
    fiscal_year_end_month=3,
    cim_unit=E.Unit.MILLIONS,
    workbook_unit=E.Unit.THOUSANDS,
    rule_of_40_variant=E.RuleOf40Variant.SALES_GROWTH_PLUS_EBITDA_MARGIN,
    periods=_periods(),
    line_items=_line_items(),
    kpis=_kpis(),
    bridge=_bridge(),
    retention=_retention(),
    cap_table=_cap_table(),
    team=_team(),
    competitors=_competitors(),
    narrative=_narrative(),
    management_accounts=_management_accounts(),
    filler_sections=[],
    defects=_defects(),
)
