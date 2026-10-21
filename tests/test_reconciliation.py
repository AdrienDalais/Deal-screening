"""The specification for core/reconciliation.py.

Every test is tied to a planted defect in the fixtures or to a rule in
docs/DECISIONS.md. Values are in whole currency units, as standardised
observations always are.
"""

from __future__ import annotations

import pytest

from core.reconciliation import (
    Issue, Observation, Severity, check_arr_bridge, check_basis_consistency,
    check_extraction_flags,
    check_currency_and_units, check_ebitda, check_expense_axes,
    check_gross_profit, check_metric_variant_inputs, check_revenue_components,
    check_sources_agree, reconcile,
)
from storage.enums import Basis, BreakdownAxis, RuleOf40Variant

M = 1_000_000.0


def obs(metric: str, period: str, value: float | None, *,
        basis: Basis = Basis.ACTUAL, currency: str = "GBP",
        axis: BreakdownAxis = BreakdownAxis.NOT_APPLICABLE,
        document: str = "workbook.xlsx", ref: str = "D10",
        label: str | None = None) -> Observation:
    return Observation(
        metric=metric, period_label=period, value_standardised=value,
        basis=basis, currency=currency, breakdown_axis=axis,
        document=document, source_ref=ref, original_label=label)


def keys(issues: list[Issue]) -> set[tuple[str, str]]:
    return {(i.check, i.period_label or "") for i in issues}


# =====================================================================
# check_gross_profit  —  THE WORKED EXAMPLE
# =====================================================================

def test_gross_profit_that_ties_raises_nothing():
    assert check_gross_profit([
        obs("revenue", "FY24", 15.4 * M),
        obs("cogs", "FY24", 4.5 * M),
        obs("gross_profit", "FY24", 10.9 * M),
    ]) == []


def test_gross_profit_catches_the_thornbury_rekeying_slip():
    """FY23 cost of sales entered at the CIM's scale into a sheet
    denominated in thousands: 3,500 rather than 3,500,000."""
    issues = check_gross_profit([
        obs("revenue", "FY23", 11.6 * M),
        obs("cogs", "FY23", 3_500.0),          # understated 1,000x
        obs("gross_profit", "FY23", 8.1 * M),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert issues[0].period_label == "FY23"
    assert len(issues[0].observations) == 3


def test_gross_profit_tolerates_rounding():
    """A document printing 10.9 for 10,873,000 is rounding, not erring."""
    assert check_gross_profit([
        obs("revenue", "FY24", 15_400_000),
        obs("cogs", "FY24", 4_527_000),
        obs("gross_profit", "FY24", 10_900_000),
    ]) == []


def test_gross_profit_is_silent_when_a_figure_is_absent():
    """Missing data is not a finding. Reporting it as one would bury the
    real findings in noise."""
    assert check_gross_profit([
        obs("revenue", "FY24", 15.4 * M),
        obs("gross_profit", "FY24", 10.9 * M),
    ]) == []


def test_gross_profit_checks_every_period_independently():
    issues = check_gross_profit([
        obs("revenue", "FY23", 11.6 * M), obs("cogs", "FY23", 3_500.0),
        obs("gross_profit", "FY23", 8.1 * M),
        obs("revenue", "FY24", 15.4 * M), obs("cogs", "FY24", 4.5 * M),
        obs("gross_profit", "FY24", 10.9 * M),
    ])
    assert {i.period_label for i in issues} == {"FY23"}


def test_gross_profit_message_cites_its_sources():
    issues = check_gross_profit([
        obs("revenue", "FY23", 11.6 * M, document="cim.pdf", ref="p.42"),
        obs("cogs", "FY23", 3_500.0, document="workbook.xlsx", ref="E14"),
        obs("gross_profit", "FY23", 8.1 * M, document="cim.pdf", ref="p.42"),
    ])
    assert "E14" in issues[0].message


# =====================================================================
# check_ebitda
# =====================================================================

def test_ebitda_that_ties_raises_nothing():
    assert check_ebitda([
        obs("gross_profit", "FY24", 10.9 * M),
        obs("total_opex", "FY24", 9.9 * M),
        obs("ebitda_adjustments", "FY24", 0.5 * M),
        obs("adjusted_ebitda", "FY24", 1.5 * M),
    ]) == []


def test_ebitda_catches_the_thornbury_mislabelled_row():
    """The CIM prints "EBITDA" for a figure that is after exceptional
    items, so it exceeds gross profit less overheads by exactly the
    adjustments line. The message must say so — that is the diagnosis."""
    issues = check_ebitda([
        obs("gross_profit", "FY24", 10.9 * M),
        obs("total_opex", "FY24", 9.9 * M),
        obs("ebitda_adjustments", "FY24", 0.5 * M),
        obs("ebitda", "FY24", 1.5 * M, label="EBITDA"),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "adjust" in issues[0].message.lower()


def test_ebitda_works_without_an_adjustments_line():
    """Treat a missing adjustments figure as zero, not as a reason to
    skip the check."""
    assert check_ebitda([
        obs("gross_profit", "FY24", 18.8 * M),
        obs("total_opex", "FY24", 15.2 * M),
        obs("adjusted_ebitda", "FY24", 3.6 * M),
    ]) == []


# =====================================================================
# check_revenue_components
# =====================================================================

def test_revenue_components_that_tie_raise_nothing():
    assert check_revenue_components([
        obs("recurring_revenue", "FY24", 12.3 * M),
        obs("non_recurring_revenue", "FY24", 3.1 * M),
        obs("revenue", "FY24", 15.4 * M),
    ]) == []


def test_revenue_components_catches_a_mismatch():
    issues = check_revenue_components([
        obs("recurring_revenue", "FY24", 12.3 * M),
        obs("non_recurring_revenue", "FY24", 3.1 * M),
        obs("revenue", "FY24", 16.9 * M),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR


# =====================================================================
# check_expense_axes  —  Calderwood
# =====================================================================

def test_one_axis_that_reconciles_raises_nothing():
    assert check_expense_axes([
        obs("personnel_expenses", "FY24", 5.8 * M,
            axis=BreakdownAxis.BY_FUNCTION),
        obs("sales_and_marketing", "FY24", 2.6 * M,
            axis=BreakdownAxis.BY_FUNCTION),
        obs("general_and_admin", "FY24", 1.5 * M,
            axis=BreakdownAxis.BY_FUNCTION),
        obs("total_opex", "FY24", 9.9 * M, axis=BreakdownAxis.TOTAL),
    ]) == []


def test_two_axes_that_both_reconcile_raise_a_warning():
    """Calderwood. Each axis sums to total opex on its own, so nothing is
    wrong — but summing every expense row gives twice the cost base, and
    only one axis may be used in any calculation."""
    issues = check_expense_axes([
        obs("personnel_expenses", "FY24", 12.0 * M,
            axis=BreakdownAxis.BY_NATURE),
        obs("non_personnel_expenses", "FY24", 7.1 * M,
            axis=BreakdownAxis.BY_NATURE),
        obs("product_and_engineering", "FY24", 6.9 * M,
            axis=BreakdownAxis.BY_FUNCTION),
        obs("sales_and_marketing", "FY24", 7.4 * M,
            axis=BreakdownAxis.BY_FUNCTION),
        obs("general_and_admin", "FY24", 4.8 * M,
            axis=BreakdownAxis.BY_FUNCTION),
        obs("total_opex", "FY24", 19.1 * M, axis=BreakdownAxis.TOTAL),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert "one" in issues[0].message.lower()


def test_an_axis_that_does_not_reconcile_is_an_error():
    issues = check_expense_axes([
        obs("personnel_expenses", "FY24", 12.0 * M,
            axis=BreakdownAxis.BY_NATURE),
        obs("non_personnel_expenses", "FY24", 5.0 * M,
            axis=BreakdownAxis.BY_NATURE),
        obs("total_opex", "FY24", 19.1 * M, axis=BreakdownAxis.TOTAL),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR


# =====================================================================
# check_sources_agree
# =====================================================================

def test_agreeing_sources_raise_nothing():
    assert check_sources_agree([
        obs("revenue", "FY24", 31.8 * M, document="cim.pdf", ref="p.42"),
        obs("revenue", "FY24", 31.8 * M, document="workbook.xlsx", ref="F13"),
    ]) == []


def test_disagreeing_sources_are_reported_as_a_disagreement_not_an_error():
    """Calderwood. The CIM says 31.8; management accounts say 30.9,
    restated to exclude a divested line. Neither is wrong."""
    issues = check_sources_agree([
        obs("revenue", "FY24", 31.8 * M, currency="USD",
            document="cim.pdf", ref="p.42"),
        obs("revenue", "FY24", 30.9 * M, currency="USD",
            document="management_accounts.xlsx", ref="F10"),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.DISAGREE
    assert len(issues[0].observations) == 2


def test_a_disagreement_names_both_documents_and_picks_neither():
    issues = check_sources_agree([
        obs("revenue", "FY24", 15.4 * M, document="cim.pdf", ref="p.42"),
        obs("revenue", "FY24", 15.1 * M, document="cim.pdf", ref="p.2"),
    ])
    assert "p.42" in issues[0].message and "p.2" in issues[0].message


def test_figures_on_different_bases_are_not_a_disagreement():
    """An actual and a forecast for the same period are different
    questions, not conflicting answers."""
    assert check_sources_agree([
        obs("revenue", "FY25", 20.1 * M, basis=Basis.ACTUAL),
        obs("revenue", "FY25", 21.0 * M, basis=Basis.MANAGEMENT_FORECAST),
    ]) == []


# =====================================================================
# check_basis_consistency  —  Larkspur
# =====================================================================

def test_consistent_basis_raises_nothing():
    assert check_basis_consistency([
        obs("revenue", "FY24", 26.4 * M, basis=Basis.ACTUAL),
        obs("arr", "FY24", 22.3 * M, basis=Basis.ACTUAL),
    ]) == []


def test_one_period_presented_as_both_actual_and_forecast_is_an_error():
    """Larkspur's FY25: labelled as a forecast, sitting under
    "Historicals"."""
    issues = check_basis_consistency([
        obs("revenue", "FY25", 34.0 * M, basis=Basis.ACTUAL, ref="G13"),
        obs("arr", "FY25", 29.5 * M, basis=Basis.MANAGEMENT_FORECAST,
            ref="G8"),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert issues[0].period_label == "FY25"


# =====================================================================
# check_currency_and_units
# =====================================================================

def test_a_single_currency_raises_nothing():
    assert check_currency_and_units([
        obs("revenue", "FY24", 15.4 * M, currency="GBP"),
        obs("cogs", "FY24", 4.5 * M, currency="GBP"),
    ]) == []


def test_mixed_currencies_within_one_deal_are_an_error():
    issues = check_currency_and_units([
        obs("revenue", "FY24", 15.4 * M, currency="GBP"),
        obs("cogs", "FY24", 4.5 * M, currency="EUR"),
    ])
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR


# =====================================================================
# check_metric_variant_inputs  —  Larkspur
# =====================================================================

def test_a_variant_whose_input_is_reported_raises_nothing():
    assert check_metric_variant_inputs(
        [obs("arr", "FY24", 14.1 * M)],
        RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN) == []


def test_a_variant_naming_an_unreported_input_is_an_error():
    """Larkspur declares the CARR variant and reports no CARR anywhere.
    Decision 008: a hard error, not a warning."""
    issues = check_metric_variant_inputs(
        [obs("arr", "FY24", 22.3 * M, currency="EUR")],
        RuleOf40Variant.CARR_GROWTH_PLUS_EBITDA_MARGIN)
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "carr" in issues[0].message.lower()


# =====================================================================
# check_arr_bridge  —  Thornbury
# =====================================================================

def test_a_bridge_that_ties_to_the_accounts_raises_nothing():
    assert check_arr_bridge(
        [{"period_label": "FY23", "opening": 7.0 * M,
          "new_business": 2.4 * M, "expansion": 1.5 * M,
          "churn": 0.7 * M, "closing": 10.2 * M}],
        [obs("arr", "FY23", 10.2 * M)]) == []


def test_a_bridge_disagreeing_with_the_arr_line_is_reported():
    """Thornbury FY24: components sum to 14.4 and print 14.4, while the
    financial summary shows 14.1."""
    issues = check_arr_bridge(
        [{"period_label": "FY24", "opening": 10.2 * M,
          "new_business": 3.1 * M, "expansion": 2.2 * M,
          "churn": 1.1 * M, "closing": 14.4 * M}],
        [obs("arr", "FY24", 14.1 * M)])
    assert len(issues) == 1
    assert issues[0].period_label == "FY24"


def test_a_bridge_whose_own_components_do_not_sum_is_a_separate_finding():
    """Arithmetic inside the bridge, as distinct from the bridge
    disagreeing with the accounts. Two different problems."""
    issues = check_arr_bridge(
        [{"period_label": "FY24", "opening": 10.2 * M,
          "new_business": 3.1 * M, "expansion": 2.2 * M,
          "churn": 1.1 * M, "closing": 15.0 * M}],
        [obs("arr", "FY24", 15.0 * M)])
    assert len(issues) == 1
    assert "component" in issues[0].message.lower()


# =====================================================================
# reconcile
# =====================================================================

def test_reconcile_runs_every_check_and_orders_by_severity():
    issues = reconcile(
        [obs("revenue", "FY23", 11.6 * M),
         obs("cogs", "FY23", 3_500.0),
         obs("gross_profit", "FY23", 8.1 * M),
         obs("revenue", "FY23", 11.3 * M, document="cim.pdf", ref="p.2")],
        declared_variant=RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN)
    severities = [i.severity for i in issues]
    assert Severity.ERROR in severities
    assert severities == sorted(
        severities, key=lambda s: ["error", "disagree", "warning"].index(s.value))


def test_every_issue_has_a_stable_fingerprint():
    """Decision 011: a resolution attaches to the fingerprint, so the
    same finding on the same data must always fingerprint identically."""
    args = ([obs("revenue", "FY23", 11.6 * M), obs("cogs", "FY23", 3_500.0),
             obs("gross_profit", "FY23", 8.1 * M)],)
    first = {i.fingerprint for i in check_gross_profit(*args)}
    second = {i.fingerprint for i in check_gross_profit(*args)}
    assert first == second and len(first) == 1


def test_changing_a_figure_changes_the_fingerprint():
    """So a resolution cannot outlive the figures it explained."""
    a = check_gross_profit([obs("revenue", "FY23", 11.6 * M),
                            obs("cogs", "FY23", 3_500.0),
                            obs("gross_profit", "FY23", 8.1 * M)])
    b = check_gross_profit([obs("revenue", "FY23", 11.6 * M),
                            obs("cogs", "FY23", 4_000.0),
                            obs("gross_profit", "FY23", 8.1 * M)])
    assert a[0].fingerprint != b[0].fingerprint


# =====================================================================
# check_extraction_flags  —  Larkspur, end to end
# =====================================================================

def test_unflagged_observations_raise_nothing():
    assert check_extraction_flags([obs("revenue", "FY24", 26.4 * M)]) == []


def test_a_contradiction_found_during_extraction_is_reported():
    """The extractor records both signals and declines to choose, which
    is correct — but a defect detected and not reported is a defect
    missed."""
    reason = ("Column G is labelled FY25E (reads as management_forecast) "
              "but sits under a merged header reading 'Historicals'.")
    flagged = [
        Observation("revenue", "FY25", 34.0 * M, Basis.ACTUAL, "EUR",
                    document="wb.xlsx", source_ref="G13",
                    needs_review=True, ambiguity_reason=reason),
        Observation("arr", "FY25", 29.5 * M, Basis.ACTUAL, "EUR",
                    document="wb.xlsx", source_ref="G8",
                    needs_review=True, ambiguity_reason=reason),
    ]
    issues = check_extraction_flags(flagged)
    assert len(issues) == 1
    assert issues[0].severity == Severity.ERROR
    assert "Historicals" in issues[0].message
    assert len(issues[0].observations) == 2


def test_one_contradiction_affecting_many_figures_is_one_finding():
    """Twelve flagged cells from one over-spanning header is one
    problem, not twelve. Reporting it twelve times would train the reader
    to skim the issues list."""
    reason = "one reason"
    flagged = [
        Observation("m" + str(n), "FY25", 1.0, Basis.ACTUAL, "EUR",
                    needs_review=True, ambiguity_reason=reason)
        for n in range(12)
    ]
    assert len(check_extraction_flags(flagged)) == 1
