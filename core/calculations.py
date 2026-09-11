"""Financial calculations. Pure functions, no database access.

WRITTEN BY ADRIEN. Claude wrote these signatures, docstrings and the
tests in tests/test_calculations.py. The bodies are mine. See CLAUDE.md
section 2.

-----------------------------------------------------------------------
The design decision these functions rest on
-----------------------------------------------------------------------

Every function here takes `Figure` objects rather than bare floats.

A function that receives `(11_600_000, 15_400_000)` can divide them. It
cannot know that the first is an actual and the second a management
forecast, or that one is in euros and the other in pounds, or that one is
adjusted EBITDA and the other statutory. It will return 32.8% growth,
confidently, and be wrong in a way nobody can see.

Passing the context with the number is what lets these functions refuse.

-----------------------------------------------------------------------
Two different kinds of "no answer", and they must not be confused
-----------------------------------------------------------------------

**Return None** when the inputs are fine but the answer does not exist:
a figure is missing, or the denominator is zero. Missing data is missing.
Returning 0.0 would invent a fact.

**Raise** when the inputs should never have been combined: different
currencies, different units, a change of basis, or a metric variant
naming an input that was not supplied. These are not "no answer" — they
are a question that should not have been asked, and swallowing them
silently is how a screening paper ends up quoting a growth rate that
spans an actual and a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from storage.enums import Basis, RuleOf40Variant, Unit


# =====================================================================
# Errors
# =====================================================================

class CalculationError(Exception):
    """Base class. Inputs that should not have been combined."""


class CurrencyMismatch(CalculationError):
    """Two figures in different currencies.

    Never silently converted: an FX rate baked into a result is a hidden
    assumption with no date attached. See docs/DECISIONS.md #006.
    """


class UnitMismatch(CalculationError):
    """Two figures at different scales, or of incompatible kinds.

    Standardise before calculating. A percentage is not a quantity of
    money and cannot be divided by one.
    """


class BasisMismatch(CalculationError):
    """An actual combined with a forecast.

    Growth from an actual to a management forecast is not a growth rate,
    it is a plan. Presenting one as the other is the most common way a
    screening paper becomes embarrassing. Catches the Larkspur fixture.
    """


class PeriodMismatch(CalculationError):
    """A ratio whose numerator and denominator cover different periods."""


class VariantInputMissing(CalculationError):
    """A named metric variant requires an input that was not supplied.

    Decision 008: a row labelled "CARR + EBITDA" computed from ARR is a
    hard error, not a warning. Catches the Larkspur fixture.
    """


# =====================================================================
# The value object
# =====================================================================

@dataclass(frozen=True)
class Figure:
    """One standardised number, with everything needed to use it safely.

    `value` is in **whole units of `currency`** for monetary metrics —
    15_400_000, not 15.4. Standardisation happens on the way out of the
    database; these functions never rescale.

    `value` may be None: a figure that is absent is still a figure we
    know we are missing, and that is different from a figure of zero.
    """

    value: float | None
    metric: str
    period_label: str
    basis: Basis
    unit: Unit = Unit.UNITS
    currency: str | None = None
    is_adjusted: bool = False

    @property
    def is_monetary(self) -> bool:
        return self.unit in (Unit.UNITS, Unit.THOUSANDS, Unit.MILLIONS,
                             Unit.BILLIONS)


# =====================================================================
# The functions. Bodies are Adrien's.
# =====================================================================

def revenue_growth(earlier: Figure, later: Figure) -> float | None:
    """Period-on-period growth, as a decimal fraction. 0.25 means 25%.

    Returns
    -------
    (later.value / earlier.value) - 1

    Return None when
        - either value is None
        - earlier.value is zero (growth from nothing is undefined; it is
          not "infinite" and it is certainly not 0)

    Raise
        CurrencyMismatch  currencies differ
        UnitMismatch      units differ, or either figure is not monetary
        BasisMismatch     one is an actual and the other is not
        PeriodMismatch    the two figures carry the same period label

    Worked example from the Thornbury fixture:
        FY23 revenue 11_600_000, FY24 revenue 15_400_000
        15_400_000 / 11_600_000 - 1 = 0.327586...
    """
    raise NotImplementedError("Adrien writes this one")


def cagr(earlier: Figure, later: Figure, years: float) -> float | None:
    """Compound annual growth rate over `years` years.

    (later / earlier) ** (1 / years) - 1

    Return None when either value is None, earlier.value is zero, or
    `years` is zero. Raise the same mismatches as revenue_growth.

    Also return None when either value is negative: a compound rate
    across a sign change is not a real number, and numpy would happily
    hand you a complex one.
    """
    raise NotImplementedError("Adrien writes this one")


def share_of_total(part: Figure, total: Figure) -> float | None:
    """What fraction of `total` is `part`. Used for recurring revenue share.

    part.value / total.value

    Return None when either value is None or total.value is zero.

    Raise
        CurrencyMismatch, UnitMismatch as above
        PeriodMismatch    the two figures cover different periods
        BasisMismatch     one is an actual and the other is not

    Worked example from Thornbury FY24:
        recurring 12_300_000 / revenue 15_400_000 = 0.798701...
    """
    raise NotImplementedError("Adrien writes this one")


def margin(numerator: Figure, revenue: Figure) -> float | None:
    """A margin: numerator over revenue. Used for gross and EBITDA margin.

    Deliberately one function rather than two. A gross margin and an
    EBITDA margin are the same arithmetic; what differs is which figure
    you hand it, and that choice belongs to the caller, who can also
    record which observations fed the result.

    numerator.value / revenue.value

    Return None when either value is None or revenue.value is zero.
    Negative margins are real and must be returned, not suppressed:
    Larkspur's FY22 adjusted EBITDA is negative.

    Raise the same mismatches as share_of_total.

    Worked examples from Thornbury FY24:
        gross profit 10_900_000 / revenue 15_400_000 = 0.707792...
        adj. EBITDA   1_500_000 / revenue 15_400_000 = 0.097402...
    """
    raise NotImplementedError("Adrien writes this one")


def variant_growth_metric(variant: RuleOf40Variant) -> str:
    """Which metric a Rule of 40 variant takes its growth from.

    arr_growth_plus_ebitda_margin    -> "arr"
    carr_growth_plus_ebitda_margin   -> "carr"
    sales_growth_plus_ebitda_margin  -> "revenue"

    Small, and worth having as its own function: it is the single place
    that knows what a variant name means, and reconciliation will need
    the same mapping to check a label against the inputs actually used.
    """
    raise NotImplementedError("Adrien writes this one")


def rule_of_40(
    variant: RuleOf40Variant,
    *,
    current: Mapping[str, Figure],
    prior: Mapping[str, Figure],
) -> float | None:
    """Rule of 40 for the named variant.

    growth of the variant's metric  +  adjusted EBITDA margin

    `current` and `prior` map metric name to Figure for one period each —
    for example {"arr": Figure(...), "revenue": Figure(...),
    "adjusted_ebitda": Figure(...)}.

    The variant decides which growth metric is used. If that metric is
    absent from either mapping, raise VariantInputMissing. **This is the
    point of the function.** A deal whose scorecard is labelled
    "CARR + EBITDA" while reporting no CARR anywhere must fail loudly
    rather than quietly substituting ARR — decision 008, and the Larkspur
    fixture exists to prove it does.

    Also raise VariantInputMissing when "revenue" or "adjusted_ebitda" is
    missing from `current`, since the margin cannot be formed without them.

    Return None when the growth or the margin is None: an incomplete
    Rule of 40 is not a Rule of 40.

    Worked example from Thornbury FY24, ARR variant:
        ARR growth  14_100_000 / 10_200_000 - 1 = 0.382352...
        EBITDA margin 1_500_000 / 15_400_000    = 0.097402...
        total                                   = 0.479755...
    """
    raise NotImplementedError("Adrien writes this one")
