"""Larkspur Systems — synthetic fixture company 2 of 3.

INVENTED. Nothing here derives from a real deal.

Irish B2B SaaS, EUR, **June year end**. The year end is the point: FY24
runs 1 July 2023 to 30 June 2024. Anything in our code that assumes FY24
means calendar 2024 breaks on this company, and that is a failure worth
catching in a fixture rather than on a live deal.

Planted defects
---------------
1. forecast inside the historical block — the workbook's "Historicals"
   header spans one column too far, so FY25 sits under it while its own
   column label says FY25E. Two signals inside one document disagree.
2. Rule of 40 labelled "(CARR + EBITDA)" and computed from ARR growth.
   No CARR line exists anywhere in the company's reporting.
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
    """June year end. FY24 covers Jul-23 to Jun-24.

    The `basis` recorded here is the truth. The workbook presents FY25 as
    though it were historical; that disagreement is defect 1.
    """
    out = []
    for index, label in enumerate(LABELS):
        end_year = 2022 + index
        out.append(Period(
            label=label,
            start=date(end_year - 1, 7, 1),
            end=date(end_year, 6, 30),
            basis=E.Basis.ACTUAL if index < 3 else E.Basis.MANAGEMENT_FORECAST,
        ))
    return out


def _v(*millions: float) -> dict[str, float]:
    return {lbl: round(m * M) for lbl, m in zip(LABELS, millions)}


def _line_items() -> list[LineItem]:
    return [
        LineItem("arr", "ARR (year end)", "ARR",
                 _v(11.0, 16.1, 22.3, 29.5, 38.2, 48.0)),
        LineItem("recurring_revenue", "Subscription revenue", "Recurring Revenue",
                 _v(10.6, 15.4, 21.2, 28.0, 36.2, 45.5)),
        LineItem("non_recurring_revenue", "Implementation and services",
                 "Non-Recurring Revenue",
                 _v(3.6, 4.4, 5.2, 6.0, 7.3, 8.5)),
        LineItem("revenue", "Revenue", "Revenue",
                 _v(14.2, 19.8, 26.4, 34.0, 43.5, 54.0)),
        LineItem("cogs", "Cost of revenue", "COGS",
                 _v(3.7, 5.0, 6.6, 8.2, 10.2, 12.4), is_cost=True),
        LineItem("gross_profit", "Gross profit", "Gross profit",
                 _v(10.5, 14.8, 19.8, 25.8, 33.3, 41.6)),
        LineItem("personnel_expenses", "Employee costs", "Personnel",
                 _v(6.8, 9.0, 11.4, 14.0, 17.0, 20.2), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("sales_and_marketing", "Sales and marketing", "S&M",
                 _v(2.6, 3.6, 4.8, 6.0, 7.4, 8.8), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("general_and_admin", "General and administrative", "G&A",
                 _v(1.7, 2.2, 2.8, 3.4, 4.1, 4.8), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("total_opex", "Total operating expenses", "Total OPEX",
                 _v(11.1, 14.8, 19.0, 23.4, 28.5, 33.8), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.TOTAL),
        LineItem("ebitda_adjustments", "Non-recurring items", "Adjustments",
                 _v(0.4, 0.5, 0.6, 0.0, 0.0, 0.0)),
        LineItem("adjusted_ebitda", "Adjusted EBITDA", "Adj. EBITDA",
                 _v(-0.2, 0.5, 1.4, 2.4, 4.8, 7.8),
                 is_adjusted=True,
                 adjustment_note="Pre non-recurring items."),
    ]


def _kpis() -> list[Kpi]:
    return [
        Kpi("gross_retention", "Gross revenue retention",
            "Gross revenue retention of 96% in FY24", 96.0, E.Unit.PERCENT, "FY24"),
        Kpi("net_retention", "Net revenue retention",
            "Net revenue retention of 127% in FY24", 127.0, E.Unit.PERCENT, "FY24"),
        Kpi("customer_count", "Customers",
            "168 customers as at 30 June 2024", 168, E.Unit.COUNT, "FY24"),
        Kpi("top_10_concentration", "Top 10 customer concentration",
            "The top ten customers represent 38% of ARR",
            38.0, E.Unit.PERCENT, "FY24"),
        # Stated in the narrative, computed from ARR growth despite the
        # label. This is defect 2, asserted rather than tabulated.
        Kpi("rule_of_40", "Rule of 40",
            "Rule of 40 of 44% (CARR growth plus EBITDA margin) in FY24",
            44.0, E.Unit.PERCENT, "FY24"),
        Kpi("employees", "Employees",
            "191 full-time employees", 191, E.Unit.COUNT, "FY24"),
    ]


def _bridge() -> list[BridgeRow]:
    return [
        BridgeRow("FY23", opening=11.0 * M, new_business=3.9 * M,
                  expansion=2.1 * M, churn=0.9 * M, closing=16.1 * M),
        BridgeRow("FY24", opening=16.1 * M, new_business=4.8 * M,
                  expansion=2.6 * M, churn=1.2 * M, closing=22.3 * M),
    ]


def _retention() -> list[RetentionRow]:
    return [RetentionRow("FY22", 94.0, 118.0, 91.0),
            RetentionRow("FY23", 95.0, 122.0, 92.0),
            RetentionRow("FY24", 96.0, 127.0, 94.0)]


def _cap_table() -> list[Shareholder]:
    return [
        Shareholder("D. Moloney (CEO, founder)", 28.0, "founder"),
        Shareholder("Kilbride Capital Fund III", 24.5, "institutional"),
        Shareholder("Northbrace Partners", 18.0, "institutional"),
        Shareholder("Enterprise development agency", 9.0, "institutional"),
        Shareholder("Early investors (x6)", 11.5, "other"),
        Shareholder("Employee option pool", 9.0, "employee"),
    ]


def _team() -> list[TeamMember]:
    return [
        TeamMember("D. Moloney", "Chief Executive Officer", "2015",
                   "Founder. Previously product lead at a payments processor."),
        TeamMember("E. Farrugia", "Chief Financial Officer", "2021",
                   "Joined from a private equity backed software group."),
        TeamMember("T. Bergqvist", "Chief Technology Officer", "2018",
                   "Previously principal engineer at a logistics platform."),
        TeamMember("N. Haugen", "Chief Revenue Officer", "2022",
                   "Built the enterprise sales function at two SaaS vendors."),
        TeamMember("P. Duarte", "VP Engineering", "2019",
                   "Leads platform and reliability."),
    ]


def _competitors() -> list[Competitor]:
    return [
        Competitor("Incumbent ERP modules", "Status quo",
                   "Bundled, weakly maintained, hard to displace commercially."),
        Competitor("Brannock Logistics Cloud", "Direct",
                   "Stronger in North America; thinner European coverage."),
        Competitor("Tessaly Systems", "Direct",
                   "Comparable product; historically price-led."),
        Competitor("Internal build", "Status quo",
                   "Common among the largest operators."),
    ]


def _narrative() -> dict[str, str]:
    return {
        "business_description": (
            "Larkspur Systems provides subscription software for freight "
            "forwarders and third-party logistics operators, covering "
            "quotation, booking and settlement across multi-modal shipments."
        ),
        "problem": (
            "Freight operations remain coordinated largely by email and "
            "spreadsheet. Margin leakage between quoted and settled rates is "
            "substantial and poorly measured."
        ),
        "solution": (
            "A hosted platform connecting rate management, booking and "
            "invoice reconciliation, deployed alongside existing transport "
            "management systems."
        ),
        "differentiation": (
            "Multi-modal from the outset, native settlement reconciliation, "
            "and deployment measured in weeks."
        ),
        "growth_plans": (
            "Expansion within existing operator groups, entry into the "
            "Iberian and Nordic markets, and a customs module planned for "
            "FY26."
        ),
        "management": (
            "Founder-led, with a chief financial officer and chief revenue "
            "officer recruited in the last three years."
        ),
        "exec_summary_revenue_note": (
            "FY24 revenue of EUR 26.4m, representing growth of 33% over the "
            "prior year, with 80% of revenue recurring."
        ),
    }


def _defects() -> list[Defect]:
    return [
        Defect(
            key="larkspur_forecast_inside_historicals",
            kind="forecast_presented_as_actual",
            where="workbook, Historicals header spans FY22 to FY25",
            description=(
                "The merged 'Historicals' header covers four columns rather "
                "than three, placing FY25 — a management forecast — inside "
                "the historical block. The column's own label still reads "
                "FY25E, so two signals within one sheet disagree."
            ),
            expected_detection=(
                "A column sitting under the historical header whose own "
                "label carries the forecast suffix. Any growth rate or "
                "margin computed across FY24 and FY25 spans a change of "
                "basis and must be refused or flagged, not reported."
            ),
        ),
        Defect(
            key="larkspur_rule_of_40_label_mismatch",
            kind="label_inconsistent_with_inputs",
            where="CIM, investment highlights, Rule of 40",
            description=(
                "Rule of 40 is stated as 'CARR growth plus EBITDA margin'. "
                "The company reports no CARR anywhere; the figure is ARR "
                "growth plus EBITDA margin."
            ),
            expected_detection=(
                "The named variant references an input the company does not "
                "report. Recomputing from ARR growth reproduces the stated "
                "figure; recomputing from CARR is impossible. A hard error, "
                "not a warning — see docs/DECISIONS.md #008."
            ),
        ),
    ]


LARKSPUR = CompanyTruth(
    name="Larkspur Systems",
    sector="B2B Software",
    subsector="Logistics and Freight Technology",
    country="Ireland",
    currency="EUR",
    fiscal_year_end_month=6,
    cim_unit=E.Unit.MILLIONS,
    workbook_unit=E.Unit.THOUSANDS,
    # Declared as the CARR variant, which the company cannot support.
    rule_of_40_variant=E.RuleOf40Variant.CARR_GROWTH_PLUS_EBITDA_MARGIN,
    periods=_periods(),
    line_items=_line_items(),
    kpis=_kpis(),
    bridge=_bridge(),
    retention=_retention(),
    cap_table=_cap_table(),
    team=_team(),
    competitors=_competitors(),
    narrative=_narrative(),
    filler_sections=[],
    defects=_defects(),
)
