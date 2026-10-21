"""End to end: are the planted defects actually caught?

The other suites test the pieces. This one answers the question the whole
project exists to answer — run extraction and reconciliation over the
fixtures as they are on disk, and check each declared defect produces a
finding.

A defect declared in a fixture's answer key and not caught here is a hole
in the system, not a broken test.
"""

from __future__ import annotations

import pytest

from core.reconciliation import Observation, reconcile
from ingestion.excel import extract, read_checks
from tests.fixtures.build_all import COMPANIES, FIXTURE_ROOT


def _observations(truth) -> list[Observation]:
    def convert(result, document):
        return [Observation(
            metric=o.metric, period_label=o.period_label,
            value_standardised=o.value_standardised, basis=o.basis,
            currency=o.currency_original, original_label=o.original_label,
            breakdown_axis=o.breakdown_axis, document=document,
            source_ref=o.source_cell,
            is_adjusted_as_presented=o.is_adjusted_as_presented,
            needs_review=o.needs_review, ambiguity_reason=o.ambiguity_reason,
        ) for o in result.observations]

    directory = FIXTURE_ROOT / truth.slug
    out = convert(extract(directory / f"{truth.slug}_financials.xlsx"),
                  f"{truth.slug}_financials.xlsx")
    if truth.management_accounts:
        out += convert(
            extract(directory / f"{truth.slug}_management_accounts.xlsx",
                    sheet_name="Management Accounts"),
            f"{truth.slug}_management_accounts.xlsx")
    return out


def _findings(truth) -> list:
    bridge = [{"period_label": b.period_label, "opening": b.opening,
               "new_business": b.new_business, "expansion": b.expansion,
               "churn": b.churn, "closing": b.closing} for b in truth.bridge]
    return reconcile(_observations(truth),
                     declared_variant=truth.rule_of_40_variant,
                     bridge_rows=bridge)


@pytest.fixture(params=COMPANIES, ids=[c.slug for c in COMPANIES])
def company(request):
    return request.param


def test_reconciliation_finds_something_on_every_company(company):
    assert _findings(company), f"{company.slug}: no findings at all"


def test_thornbury_rekeying_slip_is_caught():
    checks = {i.check for i in _findings(COMPANIES[0])}
    assert "gross_profit" in checks


def test_thornbury_bridge_disagreement_is_caught():
    issues = [i for i in _findings(COMPANIES[0])
              if i.check == "arr_bridge_vs_accounts"]
    assert len(issues) == 1
    assert issues[0].period_label == "FY24"
    assert "300,000" in issues[0].message


def test_larkspur_forecast_inside_historicals_is_caught():
    """Detected during extraction, surfaced by reconciliation. A defect
    found and not reported is a defect missed."""
    issues = [i for i in _findings(COMPANIES[1])
              if i.check == "extraction_ambiguity"]
    assert len(issues) == 1
    assert "Historicals" in issues[0].message
    assert "FY25" in issues[0].message


def test_larkspur_rule_of_40_label_mismatch_is_caught():
    issues = [i for i in _findings(COMPANIES[1])
              if i.check == "metric_variant_inputs"]
    assert len(issues) == 1
    assert "carr" in issues[0].message.lower()


def test_calderwood_document_disagreement_is_caught_and_not_resolved():
    issues = [i for i in _findings(COMPANIES[2])
              if i.check == "sources_disagree" and i.metric == "revenue"]
    assert len(issues) == 1
    assert "31,800,000" in issues[0].message
    assert "30,900,000" in issues[0].message
    assert issues[0].severity.value == "disagree"


def test_calderwood_overlapping_opex_axes_are_caught():
    issues = [i for i in _findings(COMPANIES[2])
              if i.check == "expense_axis_overlap"]
    assert issues
    assert "by_nature" in issues[0].message
    assert "by_function" in issues[0].message


def test_calderwood_inert_check_formula_is_caught():
    broken = [c for c in read_checks(
        FIXTURE_ROOT / "calderwood" / "calderwood_financials.xlsx")
        if not c.evaluable]
    assert len(broken) == 1


def test_clean_companies_produce_no_false_positives_on_tying_figures():
    """Larkspur's figures all tie. Its only findings should be the two
    defects it was built with — not arithmetic noise."""
    checks = {i.check for i in _findings(COMPANIES[1])}
    for arithmetic in ("gross_profit", "revenue_components", "ebitda",
                       "expense_axis"):
        assert arithmetic not in checks, f"false positive: {arithmetic}"


def test_every_finding_carries_a_fingerprint_and_a_citation():
    for truth in COMPANIES:
        for issue in _findings(truth):
            assert len(issue.fingerprint) == 16
            assert issue.message
            if issue.observations:
                assert any(o.source_ref for o in issue.observations)
