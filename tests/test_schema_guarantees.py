"""The schema's promises, written down as tests.

Each test here corresponds to a claim made in docs/DECISIONS.md. If one
of these fails, a design decision has been quietly reversed.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from storage import enums as E
from storage.db import get_engine, get_sessionmaker
from storage.models import (
    AnalysisRun, Base, Correction, Deal, Document, FinancialObservation,
)


@pytest.fixture()
def session():
    """A fresh in-memory database for each test."""
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with get_sessionmaker(engine)() as s:
        yield s


@pytest.fixture()
def deal(session) -> Deal:
    d = Deal(name="Meridian Software", confidentiality=E.Confidentiality.SYNTHETIC)
    session.add(d)
    session.commit()
    return d


def _document(session, deal: Deal, filename: str, file_hash: str) -> Document:
    doc = Document(
        deal_id=deal.id, filename=filename,
        stored_path=f"/tmp/{filename}", file_hash=file_hash,
    )
    session.add(doc)
    session.commit()
    return doc


def _observation(deal: Deal, doc: Document, value: float, **kwargs):
    defaults = dict(
        deal_id=deal.id, document_id=doc.id, metric="revenue",
        value_original=value, unit_original=E.Unit.MILLIONS,
        currency_original="GBP", value_standardised=value * 1_000_000,
        period_label="FY23", period_end=date(2023, 12, 31),
        basis=E.Basis.ACTUAL,
        extraction_method=E.ExtractionMethod.LLM_STRUCTURED,
    )
    defaults.update(kwargs)
    return FinancialObservation(**defaults)


# ---------------------------------------------------------------------
# Decision 002: disagreement is stored, not resolved
# ---------------------------------------------------------------------

def test_two_documents_may_disagree_about_the_same_figure(session, deal):
    """The central promise. Two sources, one metric, one period, two
    different values — both stored, both live."""
    cim = _document(session, deal, "cim.pdf", "a" * 64)
    accounts = _document(session, deal, "accounts.pdf", "b" * 64)

    session.add(_observation(deal, cim, 12.4, source_page=14))
    session.add(_observation(deal, accounts, 12.1, source_page=3))
    session.commit()

    rows = session.query(FinancialObservation).filter_by(
        deal_id=deal.id, metric="revenue", is_active=True
    ).all()

    assert len(rows) == 2
    assert {r.value_original for r in rows} == {12.4, 12.1}
    # And each one still knows where it came from.
    assert {r.document_id for r in rows} == {cim.id, accounts.id}


def test_a_correction_supersedes_rather_than_overwrites(session, deal):
    """The original extraction survives its own correction."""
    cim = _document(session, deal, "cim.pdf", "c" * 64)
    original = _observation(deal, cim, 12.4)
    session.add(original)
    session.commit()

    corrected = _observation(deal, cim, 12.1, review_status=E.ReviewStatus.ACCEPTED)
    session.add(corrected)
    session.flush()

    original.is_active = False
    original.review_status = E.ReviewStatus.CORRECTED
    original.superseded_by_id = corrected.id
    session.add(Correction(
        target_type="financial_observation", target_id=original.id,
        field_changed="value_original", old_value="12.4", new_value="12.1",
        reason="CIM used pre-rebate gross revenue; audited accounts are net.",
        corrected_by="adrien", resulting_observation_id=corrected.id,
    ))
    session.commit()

    assert session.get(FinancialObservation, original.id).value_original == 12.4
    assert session.query(FinancialObservation).filter_by(is_active=True).count() == 1


# ---------------------------------------------------------------------
# Decision 005 / CLAUDE.md section 2: never invent data
# ---------------------------------------------------------------------

def test_a_correction_without_a_reason_is_rejected(session, deal):
    session.add(Correction(
        target_type="financial_observation", target_id=1,
        field_changed="value_original", old_value="12.4", new_value="12.1",
        reason="   ", corrected_by="adrien",
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_figure_with_no_document_must_declare_itself_manual(session, deal):
    orphan = FinancialObservation(
        deal_id=deal.id, document_id=None, metric="revenue",
        extraction_method=E.ExtractionMethod.LLM_STRUCTURED,
    )
    session.add(orphan)
    with pytest.raises(IntegrityError):
        session.commit()


def test_manual_entry_without_a_document_is_allowed(session, deal):
    session.add(FinancialObservation(
        deal_id=deal.id, document_id=None, metric="revenue",
        value_original=12.4, unit_original=E.Unit.MILLIONS,
        extraction_method=E.ExtractionMethod.MANUAL_ENTRY,
    ))
    session.commit()
    assert session.query(FinancialObservation).count() == 1


# ---------------------------------------------------------------------
# CLAUDE.md section 5: confidential deals never reach a hosted API
# ---------------------------------------------------------------------

def test_a_confidential_deal_cannot_be_recorded_against_a_hosted_provider(session):
    """Enforced by the database, not only by the code path in llm/."""
    confidential = Deal(
        name="Project Redacted",
        confidentiality=E.Confidentiality.CONFIDENTIAL,
    )
    session.add(confidential)
    session.commit()

    session.add(AnalysisRun(
        deal_id=confidential.id, run_type=E.RunType.EXTRACTION,
        provider=E.Provider.MISTRAL_API, model_name="mistral-large-latest",
        status=E.RunStatus.SUCCESS,
        confidentiality_at_run=E.Confidentiality.CONFIDENTIAL,
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_confidential_deal_may_use_the_local_provider(session):
    confidential = Deal(
        name="Project Redacted",
        confidentiality=E.Confidentiality.CONFIDENTIAL,
    )
    session.add(confidential)
    session.commit()

    session.add(AnalysisRun(
        deal_id=confidential.id, run_type=E.RunType.EXTRACTION,
        provider=E.Provider.LOCAL_OLLAMA, model_name="mistral",
        status=E.RunStatus.SUCCESS,
        confidentiality_at_run=E.Confidentiality.CONFIDENTIAL,
    ))
    session.commit()
    assert session.query(AnalysisRun).count() == 1


def test_deals_default_to_confidential(session):
    """The safe default. A deal you forgot to classify is not sent anywhere."""
    d = Deal(name="Unclassified")
    session.add(d)
    session.commit()
    assert d.confidentiality == E.Confidentiality.CONFIDENTIAL
    assert d.requires_local_model is True


# ---------------------------------------------------------------------
# Decision 008: Rule of 40 variant is per deal, and defaults
# ---------------------------------------------------------------------

def test_rule_of_40_defaults_to_arr_growth_plus_ebitda_margin(session):
    d = Deal(name="Default Variant Co")
    session.add(d)
    session.commit()
    assert d.rule_of_40_variant == E.RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN


# ---------------------------------------------------------------------
# Other integrity promises
# ---------------------------------------------------------------------

def test_the_same_file_cannot_be_ingested_twice_for_one_deal(session, deal):
    _document(session, deal, "cim.pdf", "d" * 64)
    session.add(Document(
        deal_id=deal.id, filename="cim_copy.pdf",
        stored_path="/tmp/cim_copy.pdf", file_hash="d" * 64,
    ))
    with pytest.raises(IntegrityError):
        session.commit()


def test_a_period_cannot_end_before_it_starts(session, deal):
    cim = _document(session, deal, "cim.pdf", "e" * 64)
    session.add(_observation(
        deal, cim, 12.4,
        period_start=date(2023, 12, 31), period_end=date(2023, 1, 1),
    ))
    with pytest.raises(IntegrityError):
        session.commit()
