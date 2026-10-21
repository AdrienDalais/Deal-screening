"""Reconciliation: find what does not add up. Pure functions, no database.

Each check takes observations and returns issues. Nothing is stored —
decision 004 — because a stored issue can disagree with the data it
describes. What *is* stored is the analyst's resolution of an issue
(decision 011), keyed by the fingerprint each issue carries.

-----------------------------------------------------------------------
What an issue is, and is not
-----------------------------------------------------------------------

An issue is a statement that two things the documents say cannot both be
true, or that a label does not describe its own inputs. It is not a
judgement about which one is right. A CIM commonly restates a figure on a
different basis, and the restatement is not an error — so severity
distinguishes "this is wrong" from "these disagree and someone should
say why".

The checks never choose a winner and never modify an observation.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence

from storage.enums import Basis, BreakdownAxis, RuleOf40Variant

# Two figures standardised to whole currency units are "equal" within
# this many units. Rounding in a source document is not a finding:
# a model printing 10.9 for 10,873,000 is doing its job.
TOLERANCE = 50_000.0


class Severity(str, Enum):
    """How much a finding matters.

    ERROR     something is wrong and a number is affected.
    DISAGREE  two sources differ. Neither is necessarily wrong, and the
              analyst must record which basis the paper uses.
    WARNING   worth a look; no figure is demonstrably wrong.
    """

    ERROR = "error"
    DISAGREE = "disagree"
    WARNING = "warning"


@dataclass(frozen=True)
class Observation:
    """What reconciliation needs to know about one extracted figure.

    Deliberately not the SQLAlchemy model: this module must be callable
    on extraction output before anything is persisted, and must stay
    testable without a database.
    """

    metric: str
    period_label: str
    value_standardised: float | None
    basis: Basis
    currency: str | None = None
    original_label: str | None = None
    breakdown_axis: BreakdownAxis = BreakdownAxis.NOT_APPLICABLE
    document: str | None = None
    source_ref: str | None = None
    is_adjusted_as_presented: bool = False
    observation_id: int | None = None
    # Set by the extractor when a document said two contradictory things
    # about one figure and it declined to choose.
    needs_review: bool = False
    ambiguity_reason: str | None = None

    @property
    def cite(self) -> str:
        """Human-readable provenance, for issue messages."""
        where = self.source_ref or "unknown location"
        return f"{self.document or 'unknown document'} {where}"


@dataclass(frozen=True)
class Issue:
    check: str
    severity: Severity
    message: str
    metric: str | None = None
    period_label: str | None = None
    observations: tuple[Observation, ...] = field(default_factory=tuple)

    @property
    def fingerprint(self) -> str:
        """A stable identifier for this finding.

        Built from the check, the metric, the period and the figures
        involved — so the same finding on the same data always produces
        the same fingerprint, and a resolution recorded against it
        survives recomputation. Change any figure and the fingerprint
        changes, which invalidates the resolution automatically. That is
        the mechanism behind decision 011.
        """
        parts = [self.check, self.metric or "", self.period_label or ""]
        parts += sorted(
            f"{o.document}|{o.source_ref}|{o.value_standardised}"
            for o in self.observations
        )
        return hashlib.sha256("::".join(parts).encode()).hexdigest()[:16]


# =====================================================================
# Helpers
# =====================================================================

def _by_metric_period(observations: Iterable[Observation]
                      ) -> dict[tuple[str, str], list[Observation]]:
    """Group observations by (metric, period), keeping every one.

    Grouping rather than de-duplicating is the point: two documents
    disagreeing about FY24 revenue must both survive into the group so
    the disagreement can be seen.
    """
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for obs in observations:
        grouped[(obs.metric, obs.period_label)].append(obs)
    return dict(grouped)


def _one(observations: Sequence[Observation], metric: str, period: str
         ) -> Observation | None:
    """The single live figure for a metric and period, or None.

    Returns None when there are none *and* when there are several: a
    check that silently picked one of two conflicting figures would be
    reporting on data it invented. The conflict itself is reported by
    check_sources_agree.
    """
    matches = [o for o in observations
               if o.metric == metric and o.period_label == period
               and o.value_standardised is not None]
    return matches[0] if len(matches) == 1 else None


# =====================================================================
# The checks
# =====================================================================

def check_gross_profit(observations: Sequence[Observation]) -> list[Issue]:
    """Gross profit must equal revenue less cost of sales.

    Catches the Thornbury re-keying slip: FY23 cost of sales entered at
    the CIM's scale into a sheet denominated in thousands, understating
    it by a factor of 1,000.

    One issue per period that fails, severity ERROR, naming all three
    figures and where each came from.
    """
    issues: list[Issue] = []

    periods = {o.period_label for o in observations}

    for period in sorted(periods):
        revenue = _one(observations, "revenue", period)
        cogs = _one(observations, "cogs", period)
        gross_profit = _one(observations, "gross_profit", period)

        if revenue is None or cogs is None or gross_profit is None:
            continue

        expected = revenue.value_standardised - cogs.value_standardised
        difference = gross_profit.value_standardised - expected

        if abs(difference) <= TOLERANCE:
            continue

        issues.append(Issue(
            check="gross_profit",
            severity=Severity.ERROR,
            metric="gross_profit",
            period_label=period,
            message=(
                f"{period}: gross profit of "
                f"{gross_profit.value_standardised:,.0f} does not equal "
                f"revenue {revenue.value_standardised:,.0f} less cost of "
                f"sales {cogs.value_standardised:,.0f} "
                f"(= {expected:,.0f}). Out by {difference:,.0f}. "
                f"Revenue from {revenue.cite}, cost of sales from "
                f"{cogs.cite}, gross profit from {gross_profit.cite}."
            ),
            observations=(revenue, cogs, gross_profit),
        ))

    return issues


def check_ebitda(observations: Sequence[Observation]) -> list[Issue]:
    """Adjusted EBITDA must equal gross profit less total opex, plus
    adjustments.

    Catches the Thornbury mislabelled row: the CIM prints "EBITDA" for a
    figure that is after exceptional items, so it exceeds gross profit
    less overheads by exactly the adjustments line.

    Where the difference equals the adjustments figure, say so in the
    message — that is the diagnosis, not just the symptom.
    """
    issues: list[Issue] = []

    for period in sorted({o.period_label for o in observations}):
        gross_profit = _one(observations, "gross_profit", period)
        total_opex = _one(observations, "total_opex", period)
        if gross_profit is None or total_opex is None:
            continue

        adjustments = _one(observations, "ebitda_adjustments", period)
        adjustment_value = (
            adjustments.value_standardised if adjustments else 0.0)

        # The figure may be reported as either metric, and which one it
        # is labelled as is exactly what this check interrogates.
        reported = (_one(observations, "adjusted_ebitda", period)
                    or _one(observations, "ebitda", period))
        if reported is None:
            continue

        statutory = (gross_profit.value_standardised
                     - total_opex.value_standardised)
        adjusted = statutory + adjustment_value

        involved = tuple(o for o in (gross_profit, total_opex, adjustments,
                                     reported) if o is not None)
        presented_as_adjusted = (reported.metric == "adjusted_ebitda"
                                 or reported.is_adjusted_as_presented)

        if abs(reported.value_standardised - adjusted) <= TOLERANCE:
            if presented_as_adjusted:
                continue
            # Matches the adjusted figure but is not labelled as
            # adjusted. The difference *is* the adjustments line, and
            # saying so turns a symptom into a diagnosis.
            issues.append(Issue(
                check="ebitda_label",
                severity=Severity.ERROR,
                metric=reported.metric,
                period_label=period,
                message=(
                    f"{period}: the row labelled "
                    f"{reported.original_label or reported.metric!r} shows "
                    f"{reported.value_standardised:,.0f}, which is gross "
                    f"profit less overheads ({statutory:,.0f}) plus the "
                    f"adjustments line ({adjustment_value:,.0f}). It is an "
                    f"adjusted figure presented without saying so. From "
                    f"{reported.cite}."
                ),
                observations=involved,
            ))
            continue

        if abs(reported.value_standardised - statutory) <= TOLERANCE:
            continue

        issues.append(Issue(
            check="ebitda",
            severity=Severity.ERROR,
            metric=reported.metric,
            period_label=period,
            message=(
                f"{period}: EBITDA of {reported.value_standardised:,.0f} "
                f"equals neither gross profit less overheads "
                f"({statutory:,.0f}) nor that plus adjustments "
                f"({adjusted:,.0f}). From {reported.cite}."
            ),
            observations=involved,
        ))

    return issues


def check_revenue_components(observations: Sequence[Observation]
                             ) -> list[Issue]:
    """Revenue must equal recurring plus non-recurring plus other."""
    issues: list[Issue] = []

    for period in sorted({o.period_label for o in observations}):
        revenue = _one(observations, "revenue", period)
        if revenue is None:
            continue

        parts = [_one(observations, m, period) for m in
                 ("recurring_revenue", "non_recurring_revenue",
                  "other_revenue")]
        present = [p for p in parts if p is not None]
        if len(present) < 2:
            continue

        summed = sum(p.value_standardised for p in present)
        difference = revenue.value_standardised - summed
        if abs(difference) <= TOLERANCE:
            continue

        issues.append(Issue(
            check="revenue_components",
            severity=Severity.ERROR,
            metric="revenue",
            period_label=period,
            message=(
                f"{period}: revenue of {revenue.value_standardised:,.0f} "
                f"does not equal its components "
                f"({' + '.join(f'{p.metric} {p.value_standardised:,.0f}' for p in present)}"
                f" = {summed:,.0f}). Out by {difference:,.0f}. Revenue from "
                f"{revenue.cite}."
            ),
            observations=tuple([revenue] + present),
        ))

    return issues


def check_expense_axes(observations: Sequence[Observation]) -> list[Issue]:
    """Each expense breakdown axis must reconcile to total opex on its own.

    Catches the Calderwood overlap: costs presented by nature and by
    function for one cost base, where summing every row gives exactly
    twice the real total.

    An axis that reconciles is not an issue. An axis that does not is an
    ERROR. Where two axes are present and both reconcile, raise a
    WARNING saying only one may be used in any calculation.
    """
    issues: list[Issue] = []

    for period in sorted({o.period_label for o in observations}):
        total = _one(observations, "total_opex", period)
        if total is None:
            continue

        reconciling: list[BreakdownAxis] = []
        for axis in (BreakdownAxis.BY_NATURE, BreakdownAxis.BY_FUNCTION):
            rows = [o for o in observations
                    if o.period_label == period and o.breakdown_axis == axis
                    and o.value_standardised is not None]
            if not rows:
                continue

            summed = sum(o.value_standardised for o in rows)
            difference = summed - total.value_standardised
            if abs(difference) <= TOLERANCE:
                reconciling.append(axis)
                continue

            issues.append(Issue(
                check="expense_axis",
                severity=Severity.ERROR,
                metric="total_opex",
                period_label=period,
                message=(
                    f"{period}: the {axis.value} expense breakdown sums to "
                    f"{summed:,.0f}, which does not equal total operating "
                    f"expenses of {total.value_standardised:,.0f}. Out by "
                    f"{difference:,.0f}. Rows: "
                    f"{', '.join(o.metric for o in rows)}."
                ),
                observations=tuple(rows + [total]),
            ))

        # Two axes that each reconcile are not an error — but they
        # describe the same cost base twice, so summing every expense row
        # double counts it entirely.
        if len(reconciling) > 1:
            issues.append(Issue(
                check="expense_axis_overlap",
                severity=Severity.WARNING,
                metric="total_opex",
                period_label=period,
                message=(
                    f"{period}: operating costs are presented on "
                    f"{len(reconciling)} overlapping breakdowns "
                    f"({', '.join(a.value for a in reconciling)}), each "
                    f"reconciling to total operating expenses on its own. "
                    f"Only one may be used in any calculation; summing "
                    f"across them double counts the whole cost base."
                ),
                observations=(total,),
            ))

    return issues


def check_sources_agree(observations: Sequence[Observation]) -> list[Issue]:
    """Two documents stating different values for one metric and period.

    Catches the Thornbury exec summary restatement and the Calderwood
    management accounts.

    Severity DISAGREE, not ERROR: neither document is necessarily wrong.
    Never picks a winner.
    """
    issues: list[Issue] = []

    # Grouped by basis as well as metric and period: an actual and a
    # forecast for one period are different questions, not conflicting
    # answers to the same one.
    grouped: dict[tuple[str, str, Basis], list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.value_standardised is None:
            continue
        grouped[(obs.metric, obs.period_label, obs.basis)].append(obs)

    for (metric, period, _basis), group in sorted(
            grouped.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if len(group) < 2:
            continue

        spread = (max(o.value_standardised for o in group)
                  - min(o.value_standardised for o in group))
        if spread <= TOLERANCE:
            continue

        stated = "; ".join(
            f"{o.value_standardised:,.0f} ({o.cite})"
            for o in sorted(group, key=lambda o: -o.value_standardised))

        issues.append(Issue(
            check="sources_disagree",
            severity=Severity.DISAGREE,
            metric=metric,
            period_label=period,
            message=(
                f"{period}: {len(group)} sources state different values "
                f"for {metric}, {spread:,.0f} apart — {stated}. Both are "
                f"retained. Neither is preferred; record which basis the "
                f"paper uses."
            ),
            observations=tuple(group),
        ))

    return issues


def check_basis_consistency(observations: Sequence[Observation]
                            ) -> list[Issue]:
    """One period presented as both actual and forecast.

    Catches the Larkspur over-spanning header: FY25 labelled as a
    forecast while sitting under "Historicals".
    """
    issues: list[Issue] = []

    for period in sorted({o.period_label for o in observations}):
        rows = [o for o in observations if o.period_label == period]
        bases = {o.basis for o in rows}
        if len(bases) < 2:
            continue

        described = "; ".join(
            f"{o.metric} is {o.basis.value} ({o.cite})"
            for o in sorted(rows, key=lambda o: o.basis.value)[:4])

        issues.append(Issue(
            check="basis_consistency",
            severity=Severity.ERROR,
            period_label=period,
            message=(
                f"{period} is presented on more than one basis "
                f"({', '.join(sorted(b.value for b in bases))}). One period "
                f"is either an actual or a forecast, not both. {described}. "
                f"Any growth rate or margin spanning this period is "
                f"unsafe until it is resolved."
            ),
            observations=tuple(rows),
        ))

    return issues


def check_currency_and_units(observations: Sequence[Observation]
                             ) -> list[Issue]:
    """All observations for one deal must share a currency."""
    issues: list[Issue] = []

    currencies = {o.currency for o in observations if o.currency}
    if len(currencies) > 1:
        examples = "; ".join(
            f"{o.metric} {o.period_label} in {o.currency} ({o.cite})"
            for o in sorted(observations, key=lambda o: o.currency or "")[:4])
        issues.append(Issue(
            check="currency_consistency",
            severity=Severity.ERROR,
            message=(
                f"Figures for this deal are stated in more than one "
                f"currency ({', '.join(sorted(currencies))}). Currencies "
                f"are never silently converted, so no comparison across "
                f"them is valid until the basis is decided explicitly. "
                f"{examples}."
            ),
            observations=tuple(observations),
        ))

    return issues


def check_extraction_flags(observations: Sequence[Observation]) -> list[Issue]:
    """Surface figures the extractor itself could not read confidently.

    Extraction flags a figure when a document says two contradictory
    things about it — Larkspur's FY25 column, labelled as a forecast
    while sitting under a header reading "Historicals". The extractor
    records both signals and declines to choose, which is correct, but
    the flag then has to travel: a defect detected at extraction and not
    reported is a defect missed.

    Grouped by reason, so one contradiction affecting twelve figures
    produces one finding rather than twelve.
    """
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.needs_review and obs.ambiguity_reason:
            grouped[obs.ambiguity_reason].append(obs)

    issues: list[Issue] = []
    for reason, group in sorted(grouped.items()):
        periods = sorted({o.period_label for o in group})
        issues.append(Issue(
            check="extraction_ambiguity",
            severity=Severity.ERROR,
            period_label=periods[0] if len(periods) == 1 else None,
            message=(
                f"{reason} {len(group)} figure(s) affected, covering "
                f"{', '.join(periods)}. The document contradicts itself, so "
                f"the basis was not resolved during extraction and any "
                f"growth rate or margin spanning these periods is unsafe."
            ),
            observations=tuple(group),
        ))
    return issues


def check_metric_variant_inputs(
    observations: Sequence[Observation],
    declared_variant: RuleOf40Variant,
) -> list[Issue]:
    """A named metric variant must be computable from what is reported.

    Catches the Larkspur label: a deal declaring the CARR variant that
    reports no CARR anywhere. Decision 008 makes this an ERROR, not a
    warning.
    """
    from core.calculations import variant_growth_metric

    required = variant_growth_metric(declared_variant)
    reported = {o.metric for o in observations
                if o.value_standardised is not None}

    if required in reported:
        return []

    return [Issue(
        check="metric_variant_inputs",
        severity=Severity.ERROR,
        metric=required,
        message=(
            f"This deal declares the {declared_variant.value} variant of "
            f"Rule of 40, which is computed from {required}. No {required} "
            f"is reported anywhere in its documents. The label names an "
            f"input that does not exist, so the metric cannot be produced "
            f"as described. Reported metrics: "
            f"{', '.join(sorted(reported)) or 'none'}."
        ),
        observations=tuple(observations),
    )]


def check_arr_bridge(
    bridge_rows: Sequence[dict],
    observations: Sequence[Observation],
) -> list[Issue]:
    """An ARR bridge must tie to itself and to the ARR line.

    Catches the Thornbury bridge: components sum correctly to 14.4 and
    print 14.4, while the financial summary shows 14.1.

    Two separate findings, and the distinction matters — a bridge whose
    own components do not sum is arithmetic; a bridge disagreeing with
    the accounts is a question about which is current.
    """
    issues: list[Issue] = []

    for row in bridge_rows:
        period = row["period_label"]
        implied = (row["opening"] + row["new_business"]
                   + row["expansion"] - row["churn"])
        printed = row["closing"]

        if abs(implied - printed) > TOLERANCE:
            issues.append(Issue(
                check="arr_bridge_components",
                severity=Severity.ERROR,
                metric="arr",
                period_label=period,
                message=(
                    f"{period}: the ARR bridge components give "
                    f"{implied:,.0f} (opening {row['opening']:,.0f} + new "
                    f"{row['new_business']:,.0f} + expansion "
                    f"{row['expansion']:,.0f} - churn {row['churn']:,.0f}) "
                    f"but a closing ARR of {printed:,.0f} is printed."
                ),
            ))
            continue

        arr = _one(observations, "arr", period)
        if arr is None:
            continue

        difference = printed - arr.value_standardised
        if abs(difference) <= TOLERANCE:
            continue

        issues.append(Issue(
            check="arr_bridge_vs_accounts",
            severity=Severity.ERROR,
            metric="arr",
            period_label=period,
            message=(
                f"{period}: the ARR bridge closes at {printed:,.0f} and is "
                f"internally consistent, but the ARR line shows "
                f"{arr.value_standardised:,.0f} ({arr.cite}). Out by "
                f"{difference:,.0f}. A bridge built before a later "
                f"adjustment to the accounts does exactly this."
            ),
            observations=(arr,),
        ))

    return issues


def reconcile(
    observations: Sequence[Observation],
    *,
    declared_variant: RuleOf40Variant | None = None,
    bridge_rows: Sequence[dict] = (),
) -> list[Issue]:
    """Run every check and return the findings, most severe first."""
    issues: list[Issue] = []
    issues += check_gross_profit(observations)
    issues += check_ebitda(observations)
    issues += check_revenue_components(observations)
    issues += check_expense_axes(observations)
    issues += check_sources_agree(observations)
    issues += check_basis_consistency(observations)
    issues += check_extraction_flags(observations)
    issues += check_currency_and_units(observations)
    if declared_variant is not None:
        issues += check_metric_variant_inputs(observations, declared_variant)
    if bridge_rows:
        issues += check_arr_bridge(bridge_rows, observations)

    order = {Severity.ERROR: 0, Severity.DISAGREE: 1, Severity.WARNING: 2}
    return sorted(issues, key=lambda i: (order[i.severity], i.check,
                                         i.period_label or ""))
