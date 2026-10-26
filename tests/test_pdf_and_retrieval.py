"""Reading a CIM without a model.

This is the baseline. Whatever the LLM scores later is only meaningful
against what deterministic reading already achieves — a model that
matches this has earned nothing, and one that falls short of it is
costing money to do worse.
"""

from __future__ import annotations

import pytest

from ingestion.pdf import read
from retrieval.keyword import find_kpis, find_sections
from tests.fixtures.build_all import COMPANIES, FIXTURE_ROOT


@pytest.fixture(scope="module", params=COMPANIES,
                ids=[c.slug for c in COMPANIES])
def document(request):
    truth = request.param
    path = FIXTURE_ROOT / truth.slug / f"{truth.slug}_cim_slides.pdf"
    if not path.exists():
        pytest.skip("fixtures not built")
    return read(path), truth


# ---------------------------------------------------------------------
# Reading order
# ---------------------------------------------------------------------

def test_the_financial_table_reads_as_rows(document):
    """Raw pypdf returns a slide table as a flat column-wise stream with
    the grid gone. Fragments are re-ordered by position to recover it."""
    doc, truth = document
    page = next(p for p in doc.pages if "Financial Summary" in p.text)
    revenue_row = next(r for r in page.rows
                       if r.startswith(truth.item("revenue").cim_label))
    for period in ("FY22", "FY24"):
        printed = truth.item("revenue").values[period] / 1_000_000
        assert f"{printed:,.1f}" in revenue_row


def test_columns_are_split_in_prose_and_kept_in_tables(document):
    """Two bullets at the same height in different columns are unrelated
    sentences; a row label and its values are one row. Both readings come
    from the same fragments."""
    doc, _ = document
    table = next(p for p in doc.pages if "Financial Summary" in p.text)
    assert any(len(r.split()) > 6 for r in table.rows)

    bullets = doc.page(6)
    assert len(bullets.lines) >= len(bullets.rows)


def test_headings_are_recovered(document):
    doc, _ = document
    headings = [p.heading for p in doc.pages if p.heading]
    assert len(headings) > 20
    assert any("Financial Summary" in h for h in headings)


# ---------------------------------------------------------------------
# Pages that cannot be read
# ---------------------------------------------------------------------

def test_unreadable_pages_are_identified(document):
    """Figures existing only as pixels must be reported, never treated
    as an empty page."""
    doc, _ = document
    assert doc.unreadable_pages


def test_section_dividers_are_not_called_unreadable(document):
    """A deck puts a background on nearly every page, so "sparse and has
    an image" describes every divider. A warning raised fifteen times is
    a warning nobody reads."""
    doc, _ = document
    assert len(doc.unreadable_pages) < len(doc.sparse_pages)


# ---------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------

def test_the_sections_a_screening_paper_needs_are_found(document):
    doc, _ = document
    found = {s.name for s in find_sections(doc)}
    for required in ("executive_summary", "investment_highlights",
                     "financials", "management", "market"):
        assert required in found, f"{required} not located"


def test_stated_kpis_are_found_with_their_source_page(document):
    doc, truth = document
    findings = {f.key: f for f in find_kpis(doc)}
    for kpi in truth.kpis:
        if kpi.key not in findings:
            continue
        found = findings[kpi.key]
        assert found.page > 0
        # The finding applies its own suffix: a CIM writes "£66k" and
        # means 66,000.
        assert found.value == pytest.approx(kpi.value), (
            f"{kpi.key}: truth {kpi.value}, retrieved {found.value} "
            f"from {found.sentence!r}")


def test_retrieval_does_not_mistake_a_decoy_for_a_company_metric(document):
    """The fixtures scatter currency figures that are NOT company
    revenue — a customer's ARR, the market size, a funding round. An
    extractor that grabs the nearest plausible figure returns the Series
    A, and 79 of 84 pages carry a currency amount."""
    doc, _ = document
    for finding in find_kpis(doc):
        if finding.key == "market_size":
            # The market is sized in billions; every decoy is in millions.
            assert (finding.unit_hint or "").lower() == "b", finding.sentence


def test_no_kpi_is_reported_without_the_sentence_it_came_from(document):
    """A figure without the words around it cannot be checked, and every
    one of these is going to be checked by a human."""
    doc, _ = document
    for finding in find_kpis(doc):
        assert finding.sentence.strip()
        assert finding.raw_value in finding.sentence
