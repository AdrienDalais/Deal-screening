"""Excel extraction, scored against the answer key.

No model is involved, so accuracy here should be 100% — which is what
makes this the control. When LLM extraction from PDFs scores 94%, the
question is whether the missing 6% is the model or the pipeline, and
having a deterministic path that scores 100% on the same fixtures
answers it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.excel import extract, read_checks
from storage.enums import Basis
from tests.fixtures.build_all import COMPANIES

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(params=COMPANIES, ids=[c.slug for c in COMPANIES])
def company(request):
    return request.param


def _key(slug: str) -> dict:
    path = FIXTURES / slug / "expected.json"
    if not path.exists():
        pytest.skip("fixtures not built")
    return json.loads(path.read_text())


def _expected(slug: str) -> dict[tuple[str, str], dict]:
    doc = next(d for d in _key(slug)["documents"]
               if d["document_type"] == "financials_workbook")
    return {(o["metric"], o["period_label"]): o for o in doc["observations"]}


# ---------------------------------------------------------------------

def test_extraction_finds_every_figure_the_key_expects(company):
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    found = {(o.metric, o.period_label) for o in result.observations}
    missing = set(_expected(company.slug)) - found
    assert not missing, f"{company.slug}: not extracted: {sorted(missing)}"


def test_extraction_invents_nothing(company):
    """Every figure extracted must be one the key knows about."""
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    expected = _expected(company.slug)
    extra = {(o.metric, o.period_label) for o in result.observations} - set(expected)
    assert not extra, f"{company.slug}: invented: {sorted(extra)}"


def test_every_extracted_value_matches_the_key_exactly(company):
    """Including the mis-keyed cell. Extraction transcribes; it does not
    correct. An extractor that repaired Thornbury's FY23 cost of sales
    would be destroying the evidence that the document was wrong."""
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    expected = _expected(company.slug)
    for obs in result.observations:
        want = expected[(obs.metric, obs.period_label)]
        assert obs.value_original == pytest.approx(want["value_original"]), (
            f"{company.slug} {obs.metric} {obs.period_label} "
            f"at {obs.source_cell}")


def test_every_cell_reference_matches_the_key(company):
    """Source references are the whole point. A figure whose citation is
    wrong is worse than one that was never extracted."""
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    expected = _expected(company.slug)
    for obs in result.observations:
        assert obs.source_cell == \
            expected[(obs.metric, obs.period_label)]["source_cell"]


def test_units_and_currency_are_read_from_the_header(company):
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    assert result.currency == company.currency
    assert result.unit == company.workbook_unit
    assert result.fiscal_year_end_month == company.fiscal_year_end_month
    assert not result.warnings


def test_periods_become_real_dates_using_the_year_end(company):
    """Larkspur's FY24 runs Jul-23 to Jun-24. A fixture-wide check that
    nothing assumes a fiscal year is a calendar year."""
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    for obs in result.observations:
        assert obs.period_end is not None
        assert obs.period_end.month == company.fiscal_year_end_month
        expected = company.period(obs.period_label)
        assert obs.period_end == expected.end
        assert obs.period_start == expected.start


def test_no_label_goes_unmapped(company):
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    assert result.unmapped_labels == []


# ---------------------------------------------------------------------
# The planted defects
# ---------------------------------------------------------------------

def test_larkspur_contradictory_basis_signals_are_flagged_not_resolved():
    """THE LARKSPUR DEFECT.

    The column label says forecast; the merged header above it says
    historical. The extractor records both and flags the row. It does not
    pick a winner — which one is right is a judgement, and judgements
    belong to the analyst.
    """
    result = extract(FIXTURES / "larkspur" / "larkspur_financials.xlsx")
    flagged = [o for o in result.observations if o.needs_review]
    assert flagged, "the contradiction was not detected"
    assert {o.period_label for o in flagged} == {"FY25"}

    reason = flagged[0].ambiguity_reason
    assert "FY25E" in reason and "Historicals" in reason
    assert "management_forecast" in reason and "actual" in reason


def test_thornbury_rekeying_slip_is_transcribed_not_corrected():
    """The cell holds 3.5 in a sheet denominated in thousands. Extraction
    must report 3.5."""
    result = extract(FIXTURES / "thornbury" / "thornbury_financials.xlsx")
    cogs = next(o for o in result.observations
                if o.metric == "cogs" and o.period_label == "FY23")
    assert cogs.value_original == pytest.approx(-3.5)
    assert cogs.value_standardised == pytest.approx(3_500.0)


def test_calderwood_inert_check_is_reported_as_not_evaluable():
    """A check that cannot run must say so in words. Rendered blank, as a
    dash, or as an error code, it reads as 'fine'."""
    checks = read_checks(FIXTURES / "calderwood" /
                         "calderwood_financials.xlsx")
    broken = [c for c in checks if not c.evaluable]
    assert len(broken) == 1
    assert "Adj_EBITDA_PL" in broken[0].reason
    assert "cannot be evaluated" in broken[0].reason


def test_working_checks_are_reported_as_evaluable():
    for slug in ("thornbury", "larkspur"):
        checks = read_checks(FIXTURES / slug / f"{slug}_financials.xlsx")
        assert checks and all(c.evaluable for c in checks)


def test_calderwood_management_accounts_restate_fy24_revenue():
    """A second document covering the same period on a different basis.
    Both figures survive extraction; neither is preferred."""
    cim_side = extract(FIXTURES / "calderwood" /
                       "calderwood_financials.xlsx")
    accounts = extract(FIXTURES / "calderwood" /
                       "calderwood_management_accounts.xlsx",
                       sheet_name="Management Accounts")

    def revenue(result):
        return next(o.value_standardised for o in result.observations
                    if o.metric == "revenue" and o.period_label == "FY24")

    assert revenue(cim_side) == pytest.approx(31_800_000)
    assert revenue(accounts) == pytest.approx(30_900_000)


def test_forecast_columns_are_read_as_forecasts(company):
    """Basis comes from the merged header, not from a suffix someone
    remembered to type."""
    result = extract(FIXTURES / company.slug /
                     f"{company.slug}_financials.xlsx")
    fy27 = [o for o in result.observations if o.period_label == "FY27"]
    assert fy27
    assert all(o.basis == Basis.MANAGEMENT_FORECAST for o in fy27)
