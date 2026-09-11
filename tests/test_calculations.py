"""The specification for core/calculations.py, written as tests.

Adrien writes the function bodies; these say what they must do. Every
expected value below was computed by hand from the fixture companies and
is shown with its arithmetic, so a failure tells you which number is
wrong rather than only that one is.

Run just this file while working:

    pytest tests/test_calculations.py -v

They all fail at first. That is the point — each one turning green is a
piece of the specification met.
"""

from __future__ import annotations

import pytest

from core.calculations import (
    BasisMismatch, CurrencyMismatch, Figure, PeriodMismatch, UnitMismatch,
    VariantInputMissing, cagr, margin, revenue_growth, rule_of_40,
    share_of_total, variant_growth_metric,
)
from storage.enums import Basis, RuleOf40Variant, Unit


def gbp(value: float | None, metric: str, period: str,
        basis: Basis = Basis.ACTUAL, **kwargs) -> Figure:
    return Figure(value=value, metric=metric, period_label=period,
                  basis=basis, currency="GBP", **kwargs)


# =====================================================================
# revenue_growth
# =====================================================================

def test_revenue_growth_thornbury_fy23_to_fy24():
    """15,400,000 / 11,600,000 - 1 = 0.3275862068965518"""
    result = revenue_growth(gbp(11_600_000, "revenue", "FY23"),
                            gbp(15_400_000, "revenue", "FY24"))
    assert result == pytest.approx(0.3275862068965518)


def test_revenue_growth_can_be_negative():
    """A business that shrank. 9,000,000 / 12,000,000 - 1 = -0.25"""
    result = revenue_growth(gbp(12_000_000, "revenue", "FY23"),
                            gbp(9_000_000, "revenue", "FY24"))
    assert result == pytest.approx(-0.25)


def test_revenue_growth_is_none_when_a_figure_is_missing():
    """Missing is missing. Not zero, not an error — there is simply no
    growth rate to report."""
    assert revenue_growth(gbp(None, "revenue", "FY23"),
                          gbp(15_400_000, "revenue", "FY24")) is None
    assert revenue_growth(gbp(11_600_000, "revenue", "FY23"),
                          gbp(None, "revenue", "FY24")) is None


def test_revenue_growth_is_none_when_growing_from_zero():
    """Growth from nothing is undefined. Not infinity, not 100%."""
    assert revenue_growth(gbp(0, "revenue", "FY23"),
                          gbp(15_400_000, "revenue", "FY24")) is None


def test_revenue_growth_refuses_a_change_of_basis():
    """THE LARKSPUR DEFECT.

    FY24 actual to FY25 management forecast is not a growth rate, it is
    a plan. This must raise, not return a number with a caveat attached
    somewhere else.
    """
    with pytest.raises(BasisMismatch):
        revenue_growth(
            gbp(26_400_000, "revenue", "FY24", basis=Basis.ACTUAL),
            gbp(34_000_000, "revenue", "FY25",
                basis=Basis.MANAGEMENT_FORECAST))


def test_revenue_growth_allows_two_forecasts_to_be_compared():
    """Forecast-to-forecast is a legitimate question: it is the growth
    management is projecting. Only *mixing* the two is forbidden."""
    result = revenue_growth(
        gbp(20_100_000, "revenue", "FY25", basis=Basis.MANAGEMENT_FORECAST),
        gbp(26_000_000, "revenue", "FY26", basis=Basis.MANAGEMENT_FORECAST))
    assert result == pytest.approx(0.29353233830845765)


def test_revenue_growth_refuses_different_currencies():
    """Never silently converted. An FX rate inside a result is an
    assumption with no date on it."""
    with pytest.raises(CurrencyMismatch):
        revenue_growth(
            Figure(11_600_000, "revenue", "FY23", Basis.ACTUAL,
                   currency="GBP"),
            Figure(19_800_000, "revenue", "FY24", Basis.ACTUAL,
                   currency="EUR"))


def test_revenue_growth_refuses_different_units():
    with pytest.raises(UnitMismatch):
        revenue_growth(
            Figure(11.6, "revenue", "FY23", Basis.ACTUAL,
                   unit=Unit.MILLIONS, currency="GBP"),
            Figure(15_400_000, "revenue", "FY24", Basis.ACTUAL,
                   unit=Unit.UNITS, currency="GBP"))


def test_revenue_growth_refuses_the_same_period_twice():
    """Comparing a period with itself is a caller bug, not a 0% result."""
    with pytest.raises(PeriodMismatch):
        revenue_growth(gbp(15_400_000, "revenue", "FY24"),
                       gbp(15_400_000, "revenue", "FY24"))


# =====================================================================
# share_of_total
# =====================================================================

def test_recurring_share_thornbury_fy24():
    """12,300,000 / 15,400,000 = 0.7987012987012987"""
    result = share_of_total(gbp(12_300_000, "recurring_revenue", "FY24"),
                            gbp(15_400_000, "revenue", "FY24"))
    assert result == pytest.approx(0.7987012987012987)


def test_recurring_share_calderwood_fy24():
    """23,200,000 / 31,800,000 = 0.7295597484276729"""
    result = share_of_total(
        Figure(23_200_000, "recurring_revenue", "FY24", Basis.ACTUAL,
               currency="USD"),
        Figure(31_800_000, "revenue", "FY24", Basis.ACTUAL, currency="USD"))
    assert result == pytest.approx(0.7295597484276729)


def test_share_of_total_is_none_when_the_total_is_zero():
    assert share_of_total(gbp(12_300_000, "recurring_revenue", "FY24"),
                          gbp(0, "revenue", "FY24")) is None


def test_share_of_total_refuses_figures_from_different_periods():
    """Recurring revenue for one year over total revenue for another is
    a number, and it means nothing."""
    with pytest.raises(PeriodMismatch):
        share_of_total(gbp(12_300_000, "recurring_revenue", "FY24"),
                       gbp(11_600_000, "revenue", "FY23"))


# =====================================================================
# margin
# =====================================================================

def test_gross_margin_thornbury_fy24():
    """10,900,000 / 15,400,000 = 0.7077922077922078"""
    result = margin(gbp(10_900_000, "gross_profit", "FY24"),
                    gbp(15_400_000, "revenue", "FY24"))
    assert result == pytest.approx(0.7077922077922078)


def test_ebitda_margin_thornbury_fy24():
    """1,500,000 / 15,400,000 = 0.09740259740259741"""
    result = margin(gbp(1_500_000, "adjusted_ebitda", "FY24",
                        is_adjusted=True),
                    gbp(15_400_000, "revenue", "FY24"))
    assert result == pytest.approx(0.09740259740259741)


def test_gross_margin_larkspur_fy24_is_exactly_three_quarters():
    """19,800,000 / 26,400,000 = 0.75"""
    result = margin(
        Figure(19_800_000, "gross_profit", "FY24", Basis.ACTUAL,
               currency="EUR"),
        Figure(26_400_000, "revenue", "FY24", Basis.ACTUAL, currency="EUR"))
    assert result == pytest.approx(0.75)


def test_a_negative_margin_is_returned_not_suppressed():
    """Larkspur FY22: -200,000 / 14,200,000 = -0.014084507042253521

    Loss-making is a fact about the business, not an error to be
    cleaned up.
    """
    result = margin(
        Figure(-200_000, "adjusted_ebitda", "FY22", Basis.ACTUAL,
               currency="EUR", is_adjusted=True),
        Figure(14_200_000, "revenue", "FY22", Basis.ACTUAL, currency="EUR"))
    assert result == pytest.approx(-0.014084507042253521)


def test_margin_is_none_when_revenue_is_missing():
    assert margin(gbp(1_500_000, "adjusted_ebitda", "FY24"),
                  gbp(None, "revenue", "FY24")) is None


def test_margin_refuses_a_change_of_basis():
    with pytest.raises(BasisMismatch):
        margin(gbp(2_100_000, "adjusted_ebitda", "FY25",
                   basis=Basis.MANAGEMENT_FORECAST),
               gbp(15_400_000, "revenue", "FY24", basis=Basis.ACTUAL))


# =====================================================================
# cagr
# =====================================================================

def test_cagr_thornbury_revenue_over_two_years():
    """(15,400,000 / 8,200,000) ** (1/2) - 1 = 0.3704191988175751"""
    result = cagr(gbp(8_200_000, "revenue", "FY22"),
                  gbp(15_400_000, "revenue", "FY24"), years=2)
    assert result == pytest.approx(0.3704191988175751)


def test_cagr_over_one_year_equals_simple_growth():
    """A sanity check worth having: with years=1 the two functions must
    agree exactly, or one of them is wrong."""
    earlier = gbp(11_600_000, "revenue", "FY23")
    later = gbp(15_400_000, "revenue", "FY24")
    assert cagr(earlier, later, years=1) == pytest.approx(
        revenue_growth(earlier, later))


def test_cagr_is_none_across_a_sign_change():
    """A compound rate from a negative base is not a real number."""
    assert cagr(gbp(-200_000, "adjusted_ebitda", "FY22"),
                gbp(1_500_000, "adjusted_ebitda", "FY24"), years=2) is None


def test_cagr_is_none_when_years_is_zero():
    assert cagr(gbp(8_200_000, "revenue", "FY22"),
                gbp(15_400_000, "revenue", "FY24"), years=0) is None


# =====================================================================
# Rule of 40 — the variant machinery
# =====================================================================

def test_variant_growth_metric_maps_each_variant_to_its_input():
    assert variant_growth_metric(
        RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN) == "arr"
    assert variant_growth_metric(
        RuleOf40Variant.CARR_GROWTH_PLUS_EBITDA_MARGIN) == "carr"
    assert variant_growth_metric(
        RuleOf40Variant.SALES_GROWTH_PLUS_EBITDA_MARGIN) == "revenue"


def test_rule_of_40_thornbury_fy24_arr_variant():
    """ARR growth   14,100,000 / 10,200,000 - 1 = 0.38235294117647056
       EBITDA margin 1,500,000 / 15,400,000     = 0.09740259740259741
       total                                    = 0.47975553857906794
    """
    result = rule_of_40(
        RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
        current={"arr": gbp(14_100_000, "arr", "FY24"),
                 "revenue": gbp(15_400_000, "revenue", "FY24"),
                 "adjusted_ebitda": gbp(1_500_000, "adjusted_ebitda", "FY24",
                                        is_adjusted=True)},
        prior={"arr": gbp(10_200_000, "arr", "FY23")})
    assert result == pytest.approx(0.47975553857906794)


def test_rule_of_40_calderwood_fy24_sales_variant():
    """Revenue growth 31,800,000 / 27,000,000 - 1 = 0.1777777777777778
       EBITDA margin   2,800,000 / 31,800,000     = 0.0880503144654088
       total                                      = 0.2658280922431866
    """
    usd = lambda v, m, p: Figure(v, m, p, Basis.ACTUAL, currency="USD")
    result = rule_of_40(
        RuleOf40Variant.SALES_GROWTH_PLUS_EBITDA_MARGIN,
        current={"revenue": usd(31_800_000, "revenue", "FY24"),
                 "adjusted_ebitda": usd(2_800_000, "adjusted_ebitda", "FY24")},
        prior={"revenue": usd(27_000_000, "revenue", "FY23")})
    assert result == pytest.approx(0.2658280922431866)


def test_rule_of_40_the_same_inputs_give_different_answers_per_variant():
    """Thornbury FY24 on the ARR variant is 0.4798; on the sales variant
    it is 0.4250. Five points apart, from the same company in the same
    year. This is why the variant is stored on the deal and printed in
    every label — see docs/DECISIONS.md #008.
    """
    figures = {
        "arr": gbp(14_100_000, "arr", "FY24"),
        "revenue": gbp(15_400_000, "revenue", "FY24"),
        "adjusted_ebitda": gbp(1_500_000, "adjusted_ebitda", "FY24"),
    }
    prior = {"arr": gbp(10_200_000, "arr", "FY23"),
             "revenue": gbp(11_600_000, "revenue", "FY23")}

    by_arr = rule_of_40(RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
                        current=figures, prior=prior)
    by_sales = rule_of_40(RuleOf40Variant.SALES_GROWTH_PLUS_EBITDA_MARGIN,
                          current=figures, prior=prior)
    assert by_arr == pytest.approx(0.47975553857906794)
    assert by_sales == pytest.approx(0.4249888042991492)
    assert abs(by_arr - by_sales) > 0.05


def test_rule_of_40_raises_when_the_variant_names_a_missing_input():
    """THE LARKSPUR DEFECT.

    A scorecard labelled "CARR + EBITDA" for a company that reports no
    CARR anywhere. Substituting ARR here would produce a number that
    looks right, matches the label, and is not what the label says.
    Decision 008 makes this a hard error.
    """
    eur = lambda v, m, p: Figure(v, m, p, Basis.ACTUAL, currency="EUR")
    with pytest.raises(VariantInputMissing):
        rule_of_40(
            RuleOf40Variant.CARR_GROWTH_PLUS_EBITDA_MARGIN,
            current={"arr": eur(22_300_000, "arr", "FY24"),
                     "revenue": eur(26_400_000, "revenue", "FY24"),
                     "adjusted_ebitda": eur(1_400_000, "adjusted_ebitda",
                                            "FY24")},
            prior={"arr": eur(16_100_000, "arr", "FY23")})


def test_rule_of_40_raises_when_revenue_is_absent():
    """No revenue means no margin, and a Rule of 40 without its margin
    half is not a Rule of 40."""
    with pytest.raises(VariantInputMissing):
        rule_of_40(
            RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
            current={"arr": gbp(14_100_000, "arr", "FY24"),
                     "adjusted_ebitda": gbp(1_500_000, "adjusted_ebitda",
                                            "FY24")},
            prior={"arr": gbp(10_200_000, "arr", "FY23")})


def test_rule_of_40_is_none_when_an_input_value_is_missing():
    """Present but empty is different from absent. A figure we know we
    are missing gives no answer; a figure the variant never asked for
    is an error."""
    result = rule_of_40(
        RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
        current={"arr": gbp(14_100_000, "arr", "FY24"),
                 "revenue": gbp(15_400_000, "revenue", "FY24"),
                 "adjusted_ebitda": gbp(None, "adjusted_ebitda", "FY24")},
        prior={"arr": gbp(10_200_000, "arr", "FY23")})
    assert result is None


def test_rule_of_40_refuses_a_change_of_basis_in_its_growth_input():
    with pytest.raises(BasisMismatch):
        rule_of_40(
            RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
            current={"arr": gbp(18_700_000, "arr", "FY25",
                                basis=Basis.MANAGEMENT_FORECAST),
                     "revenue": gbp(20_100_000, "revenue", "FY25",
                                    basis=Basis.MANAGEMENT_FORECAST),
                     "adjusted_ebitda": gbp(2_100_000, "adjusted_ebitda",
                                            "FY25",
                                            basis=Basis.MANAGEMENT_FORECAST)},
            prior={"arr": gbp(14_100_000, "arr", "FY24",
                              basis=Basis.ACTUAL)})
