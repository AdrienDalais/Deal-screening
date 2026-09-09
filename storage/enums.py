"""Controlled vocabulary for the deal screening workbench.

Every field in the schema that can only hold a fixed set of values uses
one of these. They live in their own module because there are a lot of
them, and because the *vocabulary* is a design artefact in its own right:
the set of values a field can hold is a statement about what the system
believes exists in the world.

All of these are stored in the database as their string values rather
than as integers, so that `sqlite3 data/deals.db` shows readable words.
Debuggability beats three bytes of storage.
"""

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum. Members compare equal to their string value."""

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------

class Confidentiality(StrEnum):
    """Governs where a deal's text is allowed to be sent.

    This sits on the deal, not the document, deliberately. The question
    the code must answer before every API call is "may anything from this
    deal leave this machine?", and that must have exactly one answer.
    """

    SYNTHETIC = "synthetic"        # invented data; safe anywhere
    PUBLIC = "public"              # already in the public domain
    CONFIDENTIAL = "confidential"  # local models only. Never a hosted API.


class DealStage(StrEnum):
    SOURCED = "sourced"
    SCREENING = "screening"
    DILIGENCE = "diligence"
    IC = "ic"
    COMPLETED = "completed"
    PASSED = "passed"
    ON_HOLD = "on_hold"


class RuleOf40Variant(StrEnum):
    """Which definition of Rule of 40 applies to this deal.

    Set per deal because the choice is a real analytical judgement:
    CARR is the meaningful measure of momentum on deals where signed but
    not yet live contracts matter. See docs/DECISIONS.md #008.

    The variant name is printed wherever the metric appears, and
    reconciliation checks the name against the inputs actually used.
    """

    ARR_GROWTH_PLUS_EBITDA_MARGIN = "arr_growth_plus_ebitda_margin"    # default
    CARR_GROWTH_PLUS_EBITDA_MARGIN = "carr_growth_plus_ebitda_margin"
    SALES_GROWTH_PLUS_EBITDA_MARGIN = "sales_growth_plus_ebitda_margin"


# ---------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------

class DocumentType(StrEnum):
    CIM = "cim"
    INFORMATION_MEMORANDUM = "information_memorandum"
    MANAGEMENT_PRESENTATION = "management_presentation"
    FINANCIALS_WORKBOOK = "financials_workbook"
    MANAGEMENT_ACCOUNTS = "management_accounts"
    AUDITED_ACCOUNTS = "audited_accounts"
    ANALYST_NOTE = "analyst_note"   # our own notes, e.g. from Obsidian
    OTHER = "other"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------
# Financial observations
# ---------------------------------------------------------------------

class Basis(StrEnum):
    """What kind of number this is.

    The single most important field in the schema after the source
    reference. Growth computed from an actual to a forecast is not a
    growth rate, it is a management plan, and presenting one as the other
    is the most embarrassing failure mode in a screening paper.
    """

    ACTUAL = "actual"
    MANAGEMENT_FORECAST = "management_forecast"
    ANALYST_ASSUMPTION = "analyst_assumption"
    PRO_FORMA = "pro_forma"


class PeriodType(StrEnum):
    FISCAL_YEAR = "fiscal_year"
    HALF_YEAR = "half_year"
    QUARTER = "quarter"
    MONTH = "month"
    LTM = "ltm"                    # last twelve months
    YTD = "ytd"
    POINT_IN_TIME = "point_in_time"  # e.g. ARR as at a date, headcount


class Unit(StrEnum):
    """The scale a figure was printed at.

    Kept separately from the standardised value so that a misread scale
    can be corrected by changing one field, rather than by going back to
    the PDF for every affected row.
    """

    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"
    PERCENT = "percent"
    RATIO = "ratio"
    COUNT = "count"                # customers, employees, sites
    MONTHS = "months"              # e.g. CAC payback

    @property
    def multiplier(self) -> float | None:
        """Factor converting a printed figure to whole units.

        Returns None for units where scaling is meaningless — you cannot
        standardise a percentage into "whole units of a currency".
        """
        return {
            Unit.UNITS: 1.0,
            Unit.THOUSANDS: 1_000.0,
            Unit.MILLIONS: 1_000_000.0,
            Unit.BILLIONS: 1_000_000_000.0,
        }.get(self)


class SignConvention(StrEnum):
    """How the source document signed its costs.

    Workbooks commonly store costs as negatives, so that gross profit is
    revenue *plus* COGS. We normalise to positive magnitudes on storage
    and record which convention the source used, so the normalisation is
    auditable rather than assumed.
    """

    COSTS_NEGATIVE = "costs_negative"
    COSTS_POSITIVE = "costs_positive"
    NOT_APPLICABLE = "not_applicable"


class BreakdownAxis(StrEnum):
    """Which cut of the cost base an expense line belongs to.

    Cost lines arrive on two overlapping views of one cost base: by
    nature (personnel, non-personnel) and by function (product, S&M,
    G&A). Summing across both double-counts the entire cost base.
    """

    TOTAL = "total"
    BY_NATURE = "by_nature"
    BY_FUNCTION = "by_function"
    NOT_APPLICABLE = "not_applicable"


class ExtractionMethod(StrEnum):
    """How this figure got into the database.

    Lets us measure LLM accuracy separately from spreadsheet reading on
    the evaluation set. Without it, one accuracy number would describe
    two very different processes.
    """

    LLM_STRUCTURED = "llm_structured"
    PDF_TEXT_DIRECT = "pdf_text_direct"
    OPENPYXL_DIRECT = "openpyxl_direct"
    MANUAL_ENTRY = "manual_entry"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    FLAGGED = "flagged"      # needs a second look, not yet resolved


# ---------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------

class ClaimType(StrEnum):
    RETENTION = "retention"
    CUSTOMER_CONCENTRATION = "customer_concentration"
    MARKET_POSITION = "market_position"
    MARKET_SIZE = "market_size"
    GROWTH = "growth"
    PRODUCT = "product"
    TEAM = "team"
    PROCESS = "process"
    OTHER = "other"


class VerificationStatus(StrEnum):
    """Whether we have been able to test an assertion against data.

    A number gets recalculated. A claim gets tested — and often cannot
    be, yet. NOT_TESTABLE is an honest answer, not a failure.
    """

    UNVERIFIED = "unverified"
    SUPPORTED_BY_DATA = "supported_by_data"
    CONTRADICTED_BY_DATA = "contradicted_by_data"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_TESTABLE = "not_testable"


# ---------------------------------------------------------------------
# Analysis runs
# ---------------------------------------------------------------------

class RunType(StrEnum):
    EXTRACTION = "extraction"
    RECONCILIATION = "reconciliation"
    RETRIEVAL = "retrieval"
    NARRATIVE = "narrative"


class Provider(StrEnum):
    MISTRAL_API = "mistral_api"    # hosted. Never for confidential deals.
    LOCAL_OLLAMA = "local_ollama"  # on this machine. Always permitted.
    NONE = "none"                  # deterministic run, no model involved


class RunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    PARSE_ERROR = "parse_error"          # model replied, JSON did not fit schema
    REFUSED = "refused"                  # model declined
    BLOCKED_BY_POLICY = "blocked_by_policy"  # we refused to send it


# ---------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------

class Decision(StrEnum):
    PURSUE = "pursue"
    HOLD = "hold"
    PASS = "pass"
    REQUEST_INFORMATION = "request_information"


class CriterionResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"  # never renders as blank or as a dash


class InformationRequestStatus(StrEnum):
    OPEN = "open"
    SENT = "sent"
    ANSWERED = "answered"
    WITHDRAWN = "withdrawn"


class AssessmentDimension(StrEnum):
    QUALITY_OF_REVENUE = "quality_of_revenue"
    QUALITY_OF_EARNINGS = "quality_of_earnings"
    QUALITY_OF_CASH_GENERATION = "quality_of_cash_generation"
    QUALITY_OF_GTM = "quality_of_gtm"
    MARKET_DYNAMICS = "market_dynamics"
    CUSTOMER_FEEDBACK = "customer_feedback"
    SUPPLIER_BUYER_POWER = "supplier_buyer_power"
    AI_ANGLE = "ai_angle"


class Rating(StrEnum):
    """Single normalised scale. See docs/PAPER_SPEC.md section A13.

    The source templates mixed a quality scale (Good, Med) with a
    directional one (Strong in favour, Neutral). One ordered scale.
    """

    STRONG_IN_FAVOUR = "strong_in_favour"   # +2
    GOOD = "good"                           # +1
    NEUTRAL = "neutral"                     #  0
    WEAK = "weak"                           # -1
    STRONG_AGAINST = "strong_against"       # -2

    @property
    def score(self) -> int:
        return {
            Rating.STRONG_IN_FAVOUR: 2,
            Rating.GOOD: 1,
            Rating.NEUTRAL: 0,
            Rating.WEAK: -1,
            Rating.STRONG_AGAINST: -2,
        }[self]
