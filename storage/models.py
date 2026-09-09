"""Database schema for the deal screening workbench.

The organising idea: this is a **ledger of observations**, not a table of
company financials.

A spreadsheet says: revenue for FY23 is 12.4m.

This schema says: an LLM reading page 14 of the CIM saw a line labelled
"Turnover" with the value 12.4, in a table headed "millions", covering
the year ended 31 December 2023, presented as an actual, and no human has
reviewed it yet.

Two rules follow, and they drive nearly every choice below:

1. Rows are never overwritten. A correction writes a new row and marks
   the old one superseded. The original stays, because it is the evidence
   of what the document said, and because it is the only data we have for
   measuring whether the extractor works.
2. Disagreement is stored, not resolved. Two documents claiming different
   FY23 revenue produce two live rows. See the deliberate absence of a
   uniqueness constraint on FinancialObservation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, event, func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from storage import enums as E


def enum_col(python_enum: type, **kwargs: Any):
    """An enum column stored as its readable string value.

    `native_enum=False` makes SQLAlchemy emit VARCHAR plus a CHECK
    constraint rather than a database-native ENUM type. SQLite has no
    native enum, and the CHECK constraint means an invalid value is
    rejected by the database itself, not only by Python.
    """
    return mapped_column(
        Enum(
            python_enum,
            native_enum=False,
            length=50,
            values_callable=lambda e: [m.value for m in e],
        ),
        **kwargs,
    )


class Base(DeclarativeBase):
    """Every table gets an integer primary key and a creation timestamp."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite ignores foreign keys unless asked not to.

    Off by default for backwards compatibility with very old versions.
    Without this, a FK pointing at a deleted row is silently accepted —
    which in this system would mean an observation with no source.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


# =====================================================================
# 1. Deals
# =====================================================================

class Deal(Base):
    __tablename__ = "deals"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_name: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(120))
    subsector: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(80))

    # The currency the company reports in. Never converted on storage;
    # see docs/DECISIONS.md #006.
    reporting_currency: Mapped[str | None] = mapped_column(String(3))

    # Fiscal year end as a month number, 1-12. Without this, "FY23"
    # cannot be turned into real dates, and comparing two companies on
    # "2023" silently compares different twelve-month windows.
    fiscal_year_end_month: Mapped[int | None] = mapped_column(Integer)

    confidentiality: Mapped[E.Confidentiality] = enum_col(
        E.Confidentiality, nullable=False,
        default=E.Confidentiality.CONFIDENTIAL,
    )
    stage: Mapped[E.DealStage] = enum_col(
        E.DealStage, nullable=False, default=E.DealStage.SOURCED,
    )

    # Which Rule of 40 definition applies here. Printed in every label.
    rule_of_40_variant: Mapped[E.RuleOf40Variant] = enum_col(
        E.RuleOf40Variant, nullable=False,
        default=E.RuleOf40Variant.ARR_GROWTH_PLUS_EBITDA_MARGIN,
    )

    source_description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="deal", cascade="all, delete-orphan"
    )
    observations: Mapped[list[FinancialObservation]] = relationship(
        back_populates="deal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "fiscal_year_end_month IS NULL OR "
            "(fiscal_year_end_month BETWEEN 1 AND 12)",
            name="ck_deals_fiscal_month_valid",
        ),
        # Defence in depth. The provider check also lives in llm/, but a
        # rule this important should be true of the data, not only of the
        # code path that happens to be running.
        CheckConstraint(
            "confidentiality IN ('synthetic', 'public', 'confidential')",
            name="ck_deals_confidentiality_known",
        ),
    )

    @property
    def requires_local_model(self) -> bool:
        return self.confidentiality == E.Confidentiality.CONFIDENTIAL


# =====================================================================
# 2. Documents
# =====================================================================

class Document(Base):
    __tablename__ = "documents"

    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)

    # Path on disk. The file itself is never stored in the database:
    # keeps it small, and keeps confidential documents out of anything
    # that might be committed.
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    # SHA-256 of the file contents. Answers "is this the same model I
    # read three weeks ago?" when a banker sends v4_FINAL twice and the
    # two files differ.
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    document_type: Mapped[E.DocumentType] = enum_col(
        E.DocumentType, nullable=False, default=E.DocumentType.OTHER
    )
    document_date: Mapped[date | None] = mapped_column(Date)
    page_count: Mapped[int | None] = mapped_column(Integer)
    sheet_names: Mapped[str | None] = mapped_column(Text)  # newline separated

    ingestion_status: Mapped[E.IngestionStatus] = enum_col(
        E.IngestionStatus, nullable=False, default=E.IngestionStatus.PENDING
    )
    ingestion_error: Mapped[str | None] = mapped_column(Text)

    deal: Mapped[Deal] = relationship(back_populates="documents")

    __table_args__ = (
        # The same file may legitimately appear on two different deals,
        # but not twice on one.
        Index("ix_documents_deal_hash", "deal_id", "file_hash", unique=True),
    )


# =====================================================================
# 3. Financial observations — the heart of the system
# =====================================================================

class FinancialObservation(Base):
    """One number, as it appeared in one place, in one document.

    Not "the company's revenue" — "the number printed on page 14".
    """

    __tablename__ = "financial_observations"

    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable only for manual entry, where there is no source document.
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), index=True
    )

    # --- what this is ------------------------------------------------
    metric: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # The words actually printed in the document: "Turnover", "Net
    # revenues", "Gross bookings". Without this you can never re-audit a
    # mapping, and a wrong one becomes permanent and invisible.
    original_label: Mapped[str | None] = mapped_column(String(300))

    # Which named variant this figure is, where the metric has variants
    # (Rule of 40, gross margin). Null where the metric has only one
    # definition.
    metric_variant: Mapped[str | None] = mapped_column(String(80))

    # --- the number as printed ---------------------------------------
    value_original: Mapped[float | None] = mapped_column(Float)
    unit_original: Mapped[E.Unit] = enum_col(
        E.Unit, nullable=False, default=E.Unit.UNITS
    )
    currency_original: Mapped[str | None] = mapped_column(String(3))

    # --- the comparable number ---------------------------------------
    # Whole units of the *original* currency: 12,400,000 rather than
    # 12.4. Standardisation is scale only. Currency is never converted;
    # an FX rate baked into a stored figure is a hidden assumption that
    # becomes impossible to find later. See docs/DECISIONS.md #006.
    value_standardised: Mapped[float | None] = mapped_column(Float)
    # An FX rate is never applied to a stored figure. Where a comparison
    # needs one, it is recorded here: visible, and dated, because a rate
    # without a date is not a fact.
    fx_rate_to_gbp: Mapped[float | None] = mapped_column(Float)
    fx_rate_date: Mapped[date | None] = mapped_column(Date)

    # --- period ------------------------------------------------------
    # Real dates, not just a year. "FY23" for a June year-end covers
    # Jul-22 to Jun-23.
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date, index=True)
    period_label: Mapped[str | None] = mapped_column(String(40))
    period_type: Mapped[E.PeriodType] = enum_col(
        E.PeriodType, nullable=False, default=E.PeriodType.FISCAL_YEAR
    )

    # --- what kind of number ------------------------------------------
    basis: Mapped[E.Basis] = enum_col(
        E.Basis, nullable=False, default=E.Basis.ACTUAL, index=True
    )
    is_adjusted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    adjustment_note: Mapped[str | None] = mapped_column(Text)

    sign_convention_source: Mapped[E.SignConvention] = enum_col(
        E.SignConvention, nullable=False,
        default=E.SignConvention.NOT_APPLICABLE,
    )
    breakdown_axis: Mapped[E.BreakdownAxis] = enum_col(
        E.BreakdownAxis, nullable=False,
        default=E.BreakdownAxis.NOT_APPLICABLE,
    )

    # --- where it came from -------------------------------------------
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_sheet: Mapped[str | None] = mapped_column(String(120))
    source_cell: Mapped[str | None] = mapped_column(String(20))
    source_excerpt: Mapped[str | None] = mapped_column(Text)

    extraction_method: Mapped[E.ExtractionMethod] = enum_col(
        E.ExtractionMethod, nullable=False
    )

    # --- review -------------------------------------------------------
    # The model's own "I was not confident about this mapping". Without
    # it everything looks equally trustworthy, so you review everything
    # or nothing.
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    ambiguity_reason: Mapped[str | None] = mapped_column(Text)
    model_confidence: Mapped[float | None] = mapped_column(Float)

    review_status: Mapped[E.ReviewStatus] = enum_col(
        E.ReviewStatus, nullable=False,
        default=E.ReviewStatus.UNREVIEWED, index=True,
    )

    # --- correction chain ---------------------------------------------
    # Corrections write a new row and point the old one here. Nothing is
    # ever updated in place.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_observations.id", ondelete="SET NULL")
    )

    deal: Mapped[Deal] = relationship(back_populates="observations")
    document: Mapped[Document | None] = relationship()

    __table_args__ = (
        # NOTE THE ABSENCE of a unique constraint on
        # (deal_id, metric, period_end).
        #
        # That absence is the single most important design decision in
        # this file. Two documents disagreeing about FY23 revenue must be
        # able to coexist as two live rows. A unique constraint would
        # force the system to silently pick one — the exact behaviour
        # this tool exists to prevent. The index below makes the lookup
        # fast without making it exclusive.
        Index("ix_obs_lookup", "deal_id", "metric", "period_end", "is_active"),
        CheckConstraint(
            "model_confidence IS NULL OR "
            "(model_confidence >= 0.0 AND model_confidence <= 1.0)",
            name="ck_obs_confidence_range",
        ),
        CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR "
            "period_start <= period_end",
            name="ck_obs_period_ordered",
        ),
        # A figure with no document must say it was entered by hand.
        CheckConstraint(
            "document_id IS NOT NULL OR extraction_method = 'manual_entry'",
            name="ck_obs_source_or_manual",
        ),
    )


# =====================================================================
# 4. Claims — the things documents assert that are not numbers
# =====================================================================

class Claim(Base):
    """An assertion made by a document. A number gets recalculated; a
    claim gets tested — and often cannot be, yet."""

    __tablename__ = "claims"

    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )

    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[E.ClaimType] = enum_col(
        E.ClaimType, nullable=False, default=E.ClaimType.OTHER, index=True
    )
    # Where the claim is about a metric we also extract, e.g. a stated
    # NRR of 120% that the cohort module will later test.
    subject_metric: Mapped[str | None] = mapped_column(String(80))
    stated_value: Mapped[float | None] = mapped_column(Float)
    stated_unit: Mapped[E.Unit | None] = enum_col(E.Unit)
    period_label: Mapped[str | None] = mapped_column(String(40))

    source_page: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[Text | None] = mapped_column(Text)
    extraction_method: Mapped[E.ExtractionMethod] = enum_col(
        E.ExtractionMethod, nullable=False
    )

    verification_status: Mapped[E.VerificationStatus] = enum_col(
        E.VerificationStatus, nullable=False,
        default=E.VerificationStatus.UNVERIFIED, index=True,
    )
    verification_note: Mapped[str | None] = mapped_column(Text)

    review_status: Mapped[E.ReviewStatus] = enum_col(
        E.ReviewStatus, nullable=False, default=E.ReviewStatus.UNREVIEWED
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# =====================================================================
# 5. Corrections — the record of human judgement
# =====================================================================

class Correction(Base):
    """Why a figure changed. The reason is mandatory.

    Not bureaucracy: in four months someone will ask why FY22 revenue is
    12.1 and not the 12.4 in the CIM. "The CIM used pre-rebate gross
    revenue; the audited accounts are net" is an answer. A silent edit is
    not. The pattern across reasons is also the error log for the
    extractor.
    """

    __tablename__ = "corrections"

    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)

    field_changed: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_by: Mapped[str] = mapped_column(String(120), nullable=False)

    # The new observation this correction produced, where it produced one.
    resulting_observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_observations.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('financial_observation', 'claim', 'assessment')",
            name="ck_corrections_target_type",
        ),
        # An empty reason is not a reason.
        CheckConstraint("length(trim(reason)) > 0", name="ck_corrections_reason"),
        Index("ix_corrections_target", "target_type", "target_id"),
    )


# =====================================================================
# 6. Analysis runs — one row per time the machine did something
# =====================================================================

class AnalysisRun(Base):
    """Reproducibility, and the proof that confidential deals stayed local."""

    __tablename__ = "analysis_runs"

    deal_id: Mapped[int | None] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )

    run_type: Mapped[E.RunType] = enum_col(E.RunType, nullable=False)
    provider: Mapped[E.Provider] = enum_col(E.Provider, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))

    prompt_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_estimate: Mapped[float | None] = mapped_column(Float)

    status: Mapped[E.RunStatus] = enum_col(E.RunStatus, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Path on disk, not the payload. When structured output fails to
    # parse, the parsed object does not exist — the raw text is the only
    # thing that says why.
    raw_response_path: Mapped[str | None] = mapped_column(String(1000))

    # Recorded at the time of the run, so that a later change to the
    # deal's setting cannot rewrite history.
    confidentiality_at_run: Mapped[E.Confidentiality | None] = enum_col(
        E.Confidentiality
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # The confidentiality guarantee, enforced by the database itself.
        # A confidential deal recorded against a hosted provider is not
        # merely a bug to be caught in review — it cannot be written.
        CheckConstraint(
            "confidentiality_at_run IS NULL "
            "OR confidentiality_at_run != 'confidential' "
            "OR provider IN ('local_ollama', 'none')",
            name="ck_runs_confidential_stays_local",
        ),
    )


# =====================================================================
# 7-9. Screening: decisions, criteria, information requests
# =====================================================================

class ScreeningDecision(Base):
    __tablename__ = "screening_decisions"

    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[E.Decision] = enum_col(E.Decision, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(120), nullable=False)

    # Append-only, like everything else. The history of a view changing
    # is the point: "what did we know when we passed?" is the most
    # valuable question this database will ever answer.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("screening_decisions.id", ondelete="SET NULL")
    )

    criteria: Mapped[list[ScreeningCriterion]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )
    information_requests: Mapped[list[InformationRequest]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )


class ScreeningCriterion(Base):
    """One threshold test in the opportunity snapshot, scored n of N.

    Recomputed from reviewed data rather than typed.
    """

    __tablename__ = "screening_criteria"

    decision_id: Mapped[int] = mapped_column(
        ForeignKey("screening_decisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    criterion_key: Mapped[str] = mapped_column(String(80), nullable=False)
    criterion_label: Mapped[str] = mapped_column(String(300), nullable=False)
    threshold_description: Mapped[str] = mapped_column(String(200), nullable=False)

    result: Mapped[E.CriterionResult] = enum_col(
        E.CriterionResult, nullable=False,
        default=E.CriterionResult.NOT_EVALUABLE,
    )
    evidence_summary: Mapped[str | None] = mapped_column(Text)

    # Every criterion carries its own period, because a snapshot that
    # scores one year against a header naming another is a real and
    # common failure.
    period_label: Mapped[str | None] = mapped_column(String(40))

    decision: Mapped[ScreeningDecision] = relationship(back_populates="criteria")


class InformationRequest(Base):
    __tablename__ = "information_requests"

    decision_id: Mapped[int] = mapped_column(
        ForeignKey("screening_decisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[E.InformationRequestStatus] = enum_col(
        E.InformationRequestStatus, nullable=False,
        default=E.InformationRequestStatus.OPEN,
    )
    answer_note: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    decision: Mapped[ScreeningDecision] = relationship(
        back_populates="information_requests"
    )


# =====================================================================
# 10. Assessments — rated qualitative dimensions
# =====================================================================

class Assessment(Base):
    __tablename__ = "assessments"

    deal_id: Mapped[int] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dimension: Mapped[E.AssessmentDimension] = enum_col(
        E.AssessmentDimension, nullable=False
    )
    rating: Mapped[E.Rating] = enum_col(E.Rating, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    assessed_by: Mapped[str] = mapped_column(String(120), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_assessments_deal_dim", "deal_id", "dimension", "is_active"),
    )


# =====================================================================
# 11. Evidence links
# =====================================================================

class EvidenceLink(Base):
    """Connects anything that makes a statement to the evidence for it.

    One generic table rather than five near-identical link tables
    (criterion->observation, assessment->claim, claim->observation,
    narrative section->observation, and every later diligence module).

    The trade-off, stated honestly: a polymorphic link cannot be enforced
    by a foreign key, so the database cannot guarantee that
    consumer_id 7 of type 'screening_criterion' exists. That is checked
    in application code and covered by a test.

    Accepted because CLAUDE.md requires the evidence model to support
    modules that do not exist yet — cohorts, market, valuation, IC paper
    — without changing the core. Five link tables would become nine.
    """

    __tablename__ = "evidence_links"

    consumer_type: Mapped[str] = mapped_column(String(40), nullable=False)
    consumer_id: Mapped[int] = mapped_column(Integer, nullable=False)

    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # 'supports', 'contradicts', 'input_to' — the last is how a
    # calculation records which observations fed it.
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="supports")

    __table_args__ = (
        CheckConstraint(
            "consumer_type IN ('screening_criterion', 'assessment', 'claim', "
            "'narrative_section', 'calculation', 'reconciliation_issue')",
            name="ck_evidence_consumer_type",
        ),
        CheckConstraint(
            "evidence_type IN ('financial_observation', 'claim', 'document')",
            name="ck_evidence_evidence_type",
        ),
        CheckConstraint(
            "role IN ('supports', 'contradicts', 'input_to', 'context')",
            name="ck_evidence_role",
        ),
        Index("ix_evidence_consumer", "consumer_type", "consumer_id"),
        Index("ix_evidence_evidence", "evidence_type", "evidence_id"),
    )
