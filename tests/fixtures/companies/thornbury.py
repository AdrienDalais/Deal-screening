"""Thornbury Analytics — synthetic fixture company 1 of 3.

INVENTED. Any resemblance to a real company is coincidental; nothing in
this file derives from a real deal.

UK B2B SaaS, GBP, December year end. The straightforward one: clean
growth, clean margins, no structural oddities. Its job is to test the
three failure modes below without any other noise.

Planted defects
---------------
1. re-keying scale slip   — one workbook cell entered at the CIM's scale
2. intra-document restatement — the exec summary and the financial
   section quote different revenue for the same year, for a legitimate
   reason. NOT an error. Tests that the analyst's explanation persists.
3. adjusted EBITDA mislabelled — the CIM row says "EBITDA"; the figure
   is after add-backs.
"""

from __future__ import annotations

from datetime import date

from storage import enums as E
from tests.fixtures.truth import (
    BridgeRow, CompanyTruth, Competitor, Defect, Kpi, LineItem, Period,
    RetentionRow, Shareholder, TeamMember,
)

M = 1_000_000.0  # values below are written in millions for readability


def _periods() -> list[Period]:
    spec = [
        ("FY22", 2022, E.Basis.ACTUAL),
        ("FY23", 2023, E.Basis.ACTUAL),
        ("FY24", 2024, E.Basis.ACTUAL),
        ("FY25", 2025, E.Basis.MANAGEMENT_FORECAST),
        ("FY26", 2026, E.Basis.MANAGEMENT_FORECAST),
        ("FY27", 2027, E.Basis.MANAGEMENT_FORECAST),
    ]
    return [
        Period(label=lbl, start=date(y, 1, 1), end=date(y, 12, 31), basis=b)
        for lbl, y, b in spec
    ]


def _v(*millions: float) -> dict[str, float]:
    """Map six values, FY22..FY27, onto period labels, in whole units."""
    labels = ["FY22", "FY23", "FY24", "FY25", "FY26", "FY27"]
    return {lbl: round(m * M) for lbl, m in zip(labels, millions)}


def _line_items() -> list[LineItem]:
    return [
        LineItem("arr", "ARR (year end)", "ARR",
                 _v(7.0, 10.2, 14.1, 18.7, 24.3, 30.2)),
        LineItem("recurring_revenue", "Recurring revenue", "Recurring Revenue",
                 _v(6.1, 9.0, 12.3, 16.5, 21.8, 27.9)),
        LineItem("non_recurring_revenue", "Services and other",
                 "Non-Recurring Revenue",
                 _v(2.1, 2.6, 3.1, 3.6, 4.2, 4.6)),
        LineItem("revenue", "Turnover", "Revenue",
                 _v(8.2, 11.6, 15.4, 20.1, 26.0, 32.5)),
        LineItem("cogs", "Cost of sales", "COGS",
                 _v(2.6, 3.5, 4.5, 5.7, 7.2, 8.8), is_cost=True),
        LineItem("gross_profit", "Gross profit", "Gross profit",
                 _v(5.6, 8.1, 10.9, 14.4, 18.8, 23.7)),
        LineItem("personnel_expenses", "Staff costs", "Personnel",
                 _v(3.4, 4.6, 5.8, 7.2, 8.9, 10.6), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("sales_and_marketing", "Sales and marketing", "S&M",
                 _v(1.2, 1.9, 2.6, 3.3, 4.1, 4.9), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("general_and_admin", "Administrative expenses", "G&A",
                 _v(0.9, 1.2, 1.5, 1.8, 2.2, 2.5), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.BY_FUNCTION),
        LineItem("total_opex", "Total overheads", "Total OPEX",
                 _v(5.5, 7.7, 9.9, 12.3, 15.2, 18.0), is_cost=True,
                 breakdown_axis=E.BreakdownAxis.TOTAL),
        LineItem("ebitda_adjustments", "Exceptional items", "Adjustments",
                 _v(0.3, 0.4, 0.5, 0.0, 0.0, 0.0)),
        # The CIM prints this row as plain "EBITDA". It is not.
        LineItem("adjusted_ebitda", "EBITDA", "Adj. EBITDA",
                 _v(0.4, 0.8, 1.5, 2.1, 3.6, 5.7),
                 is_adjusted=True,
                 adjustment_note="Pre-exceptional items and share-based payments."),
    ]


def _kpis() -> list[Kpi]:
    return [
        Kpi("gross_retention", "Gross revenue retention",
            "Gross revenue retention of 94% in FY24", 94.0, E.Unit.PERCENT, "FY24"),
        Kpi("net_retention", "Net revenue retention",
            "Net revenue retention of 118% in FY24", 118.0, E.Unit.PERCENT, "FY24"),
        Kpi("customer_count", "Customers",
            "214 enterprise customers as at 31 December 2024",
            214, E.Unit.COUNT, "FY24"),
        Kpi("top_10_concentration", "Top 10 customer concentration",
            "The top ten customers represent 31% of ARR",
            31.0, E.Unit.PERCENT, "FY24"),
        Kpi("average_contract_value", "Average contract value",
            "Average contract value of £66k", 66_000.0, E.Unit.UNITS, "FY24"),
        Kpi("employees", "Employees",
            "126 full-time employees across two offices", 126, E.Unit.COUNT, "FY24"),
    ]



def _bridge() -> list[BridgeRow]:
    """ARR bridges. FY23 ties; FY24 does not.

    FY24 closing is printed as 14.4 while the financial summary shows
    ARR of 14.1 — a bridge built before a late adjustment to the
    accounts, which is how this happens in practice.
    """
    return [
        BridgeRow("FY23", opening=7.0 * M, new_business=2.4 * M,
                  expansion=1.5 * M, churn=0.7 * M, closing=10.2 * M),
        BridgeRow("FY24", opening=10.2 * M, new_business=3.1 * M,
                  expansion=2.2 * M, churn=1.1 * M, closing=14.4 * M),
    ]


def _retention() -> list[RetentionRow]:
    return [
        RetentionRow("FY22", 91.0, 109.0, 88.0),
        RetentionRow("FY23", 93.0, 114.0, 90.0),
        RetentionRow("FY24", 94.0, 118.0, 92.0),
    ]


def _cap_table() -> list[Shareholder]:
    """Holdings total 100%. PAPER_SPEC B6 requires that check to have
    something to run against."""
    return [
        Shareholder("A. Whitfield (CEO, co-founder)", 24.5, "founder"),
        Shareholder("R. Nakamura (CTO, co-founder)", 21.0, "founder"),
        Shareholder("Peregrine Ventures LP", 19.5, "institutional"),
        Shareholder("Halstead Growth Partners II", 16.0, "institutional"),
        Shareholder("Early angel investors (x4)", 8.5, "other"),
        Shareholder("EMI option pool", 7.0, "employee"),
        Shareholder("Employee growth shares", 3.5, "employee"),
    ]


def _team() -> list[TeamMember]:
    return [
        TeamMember("A. Whitfield", "Chief Executive Officer", "2016",
                   "Co-founder. Previously underwriting systems lead at a "
                   "composite insurer."),
        TeamMember("R. Nakamura", "Chief Technology Officer", "2016",
                   "Co-founder. Background in actuarial modelling and "
                   "distributed systems."),
        TeamMember("S. Oyelaran", "Chief Financial Officer", "2022",
                   "Joined from a listed insurance services group where she "
                   "was group financial controller."),
        TeamMember("M. Brennan", "VP Sales", "2021",
                   "Previously enterprise sales at two broking technology "
                   "vendors."),
        TeamMember("K. Lindqvist", "VP Customer Success", "2019",
                   "Joined from consulting; leads onboarding and renewals."),
    ]


def _competitors() -> list[Competitor]:
    return [
        Competitor("Established policy administration vendors",
                   "Incumbent, extending into analytics",
                   "Broad footprint, slower release cycles, analytics bolted on."),
        Competitor("Vantell Risk Systems", "Direct specialist",
                   "Similar positioning; stronger in the Nordics."),
        Competitor("Corveth Analytics", "Direct specialist",
                   "Enterprise-only; longer deployments."),
        Competitor("In-house spreadsheets", "Status quo",
                   "Still the most common alternative; free but ungoverned."),
    ]


def _narrative() -> dict[str, str]:
    return {
        "business_description": (
            "Thornbury Analytics provides subscription software that helps "
            "mid-market insurance brokers price and monitor commercial risk. "
            "The platform ingests policy and claims data, applies the "
            "company's proprietary scoring models, and returns pricing "
            "guidance and portfolio exposure reporting."
        ),
        "problem": (
            "Commercial broking remains substantially manual. Pricing "
            "decisions rely on individual underwriter judgement, with "
            "limited portfolio-level visibility of accumulating exposure."
        ),
        "solution": (
            "A hosted platform replacing spreadsheet-based rating with "
            "governed, auditable models, deployed alongside existing policy "
            "administration systems rather than replacing them."
        ),
        "differentiation": (
            "Deployment measured in weeks rather than quarters; no "
            "replacement of the incumbent policy system; model governance "
            "reporting aligned to FCA expectations."
        ),
        "growth_plans": (
            "Expansion within existing broker groups, entry into the Irish "
            "and Benelux markets, and a claims analytics module scheduled "
            "for release in the second half of FY25."
        ),
        "management": (
            "Founder-led. The chief executive and chief technology officer "
            "co-founded the business in 2016. A chief financial officer "
            "joined in 2022 from a listed insurance services group."
        ),
        # Exec summary quotes revenue excluding a line the financial
        # section includes. Both figures are correct. See defect 2.
        "exec_summary_revenue_note": (
            "FY24 revenue from continuing operations of £15.1m, representing "
            "growth of 31% over the prior year."
        ),
    }


def _filler_sections() -> list[tuple[str, str]]:
    """Plausible but irrelevant sections, so the CIM reaches a realistic
    length and retrieval has to discriminate rather than return the only
    thing it found."""
    return [
        ("Process and Timetable",
         "Indicative offers are requested by 14 March. Management "
         "presentations will be scheduled during the following three weeks, "
         "with access to a virtual data room granted on receipt of a "
         "non-binding offer. The vendors reserve the right to amend the "
         "process at their discretion."),
        ("Technology Infrastructure",
         "The platform is hosted on a single cloud provider across two "
         "regions, with infrastructure defined as code and deployed "
         "through an automated pipeline. Recovery objectives are four "
         "hours for recovery time and fifteen minutes for recovery point."),
        ("Information Security",
         "The company holds ISO 27001 certification, renewed most recently "
         "in the prior financial year. Penetration testing is performed "
         "annually by an external provider. No material incidents have "
         "been reported in the last three years."),
        ("Intellectual Property",
         "All software is owned outright. Contributor agreements are in "
         "place for every employee and contractor. The company holds two "
         "registered trademarks and has made no patent applications."),
        ("Litigation and Contingencies",
         "The company is not party to any litigation, and management is "
         "not aware of any threatened claims. There are no contingent "
         "liabilities requiring disclosure."),
        ("Property and Leases",
         "Two leasehold offices are held on tenant-break terms expiring "
         "within three years. Neither lease carries a dilapidations "
         "provision considered material."),
        ("Environmental, Social and Governance",
         "The business reports scope 1 and scope 2 emissions annually. A "
         "board-level diversity policy was adopted in the prior year. No "
         "environmental liabilities have been identified."),
        ("Insurance",
         "Professional indemnity, cyber and directors' and officers' cover "
         "are maintained at levels reviewed annually by the board."),
    ]


def _defects() -> list[Defect]:
    return [
        Defect(
            key="thornbury_rekeying_scale_slip",
            kind="unit_inconsistency",
            where="workbook, COGS FY23",
            description=(
                "The workbook is denominated in thousands. FY23 cost of "
                "sales was re-keyed from the CIM as 3.5 rather than 3,500 "
                "— the CIM's scale, entered into a sheet using a different "
                "one. The figure is understated by a factor of 1,000."
            ),
            expected_detection=(
                "Gross profit does not equal revenue less cost of sales for "
                "FY23, and the same figure in the CIM is 1,000x larger once "
                "both are standardised."
            ),
        ),
        Defect(
            key="thornbury_exec_summary_restatement",
            kind="intra_document_restatement",
            where="CIM, executive summary vs financial summary, FY24 revenue",
            description=(
                "The executive summary quotes FY24 revenue of £15.1m "
                "(continuing operations); the financial summary shows "
                "£15.4m (including a professional services line exited "
                "during the year). Both are correct."
            ),
            expected_detection=(
                "Two figures for FY24 revenue within one document. Must be "
                "raised once, and must stop being raised after the analyst "
                "records why they differ."
            ),
            is_genuine_error=False,
        ),
        Defect(
            key="thornbury_arr_bridge_does_not_tie",
            kind="bridge_does_not_tie",
            where="CIM, ARR bridge slide, FY24",
            description=(
                "The FY24 ARR bridge sums to and prints a closing ARR of "
                "14.4, while the financial summary shows ARR of 14.1 for "
                "the same year. The bridge is internally consistent; it "
                "disagrees with the accounts."
            ),
            expected_detection=(
                "Closing ARR on the bridge does not equal the ARR line for "
                "the same period in the financial summary. A difference of "
                "0.3 that appears in no other year."
            ),
        ),
        Defect(
            key="thornbury_adjusted_ebitda_mislabelled",
            kind="label_inconsistent_with_inputs",
            where="CIM, financial summary, EBITDA row",
            description=(
                "The CIM prints the row as 'EBITDA'. The figure is after "
                "exceptional items and share-based payments, and is £0.5m "
                "higher than statutory EBITDA in FY24."
            ),
            expected_detection=(
                "The row labelled EBITDA does not equal gross profit less "
                "total overheads; the difference equals the exceptional "
                "items line disclosed elsewhere in the same table."
            ),
        ),
    ]


THORNBURY = CompanyTruth(
    name="Thornbury Analytics",
    sector="B2B Software",
    subsector="Insurance Technology / Pricing and Risk Analytics",
    country="United Kingdom",
    currency="GBP",
    fiscal_year_end_month=12,
    cim_unit=E.Unit.MILLIONS,
    workbook_unit=E.Unit.THOUSANDS,
    rule_of_40_variant=E.RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
    periods=_periods(),
    line_items=_line_items(),
    kpis=_kpis(),
    bridge=_bridge(),
    retention=_retention(),
    cap_table=_cap_table(),
    team=_team(),
    competitors=_competitors(),
    narrative=_narrative(),
    filler_sections=_filler_sections(),
    defects=_defects(),
)
