"""The pipeline: extraction through calculation and reconciliation."""

from __future__ import annotations

import pytest

from tests.fixtures.build_all import COMPANIES
from tools.run_deal import report_for


@pytest.fixture(params=COMPANIES, ids=[c.slug for c in COMPANIES])
def report(request):
    return report_for(request.param)


def test_a_report_is_produced_for_every_company(report):
    assert report.observations
    assert report.metrics["revenue"]


def test_corroborating_sources_do_not_blank_a_figure():
    """Calderwood's management accounts restate FY22 and FY23
    identically. Two documents agreeing is corroboration, so the figure
    must still be shown — adding a source should never make the
    scorecard worse."""
    report = report_for(COMPANIES[2])
    assert report.metrics["revenue"]["FY22"] == pytest.approx(22_500_000)
    assert report.metrics["revenue"]["FY23"] == pytest.approx(27_000_000)


def test_a_genuine_disagreement_blanks_the_figure():
    """FY24 is restated 31.8 -> 30.9. Neither is preferred, so nothing
    is shown and the disagreement is reported instead."""
    report = report_for(COMPANIES[2])
    assert report.metrics["revenue"]["FY24"] is None
    assert any(i.check == "sources_disagree" and i.metric == "revenue"
               for i in report.issues)


def test_growth_across_a_change_of_basis_is_refused_not_reported():
    """FY24 is an actual and FY25 a forecast. The calculation raises;
    the report shows a dash rather than a growth rate spanning the
    boundary."""
    report = report_for(COMPANIES[0])
    assert report.metrics["revenue_growth"]["FY25"] is None
    assert report.metrics["revenue_growth"]["FY24"] == pytest.approx(
        0.3275862068965518)


def test_forecast_to_forecast_growth_is_still_reported():
    """Only mixing bases is refused. Growth between two forecasts is a
    legitimate question — it is the growth management is projecting."""
    report = report_for(COMPANIES[0])
    assert report.metrics["revenue_growth"]["FY26"] == pytest.approx(
        0.29353233830845765)


def test_margins_match_hand_checked_values():
    report = report_for(COMPANIES[0])
    assert report.metrics["gross_margin"]["FY24"] == pytest.approx(
        0.7077922077922078)
    assert report.metrics["ebitda_margin"]["FY24"] == pytest.approx(
        0.09740259740259741)
    assert report.metrics["recurring_share"]["FY24"] == pytest.approx(
        0.7987012987012987)


def test_larkspur_rule_of_40_is_never_produced():
    """It declares the CARR variant and reports no CARR. The metric
    cannot be computed as labelled, so no number is shown for any
    period."""
    report = report_for(COMPANIES[1])
    assert all(v is None for v in report.metrics["rule_of_40"].values())
    assert any(i.check == "metric_variant_inputs" for i in report.issues)


def test_every_report_surfaces_its_findings(report):
    assert report.issues, f"{report.name}: no findings"
    for issue in report.issues:
        assert issue.message and len(issue.fingerprint) == 16
