"""Glue between extraction, calculations and reconciliation.

These three modules are deliberately ignorant of each other:
calculations takes value objects and knows nothing about spreadsheets,
reconciliation knows nothing about how figures were read. This module is
where they meet, and it is the only place that needs to change when a new
source of observations is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import calculations as calc
from core.calculations import Figure
from core.reconciliation import (
    TOLERANCE, Issue, Observation, reconcile,
)
from ingestion.excel import CheckRow, extract, read_checks
from storage.enums import Basis, RuleOf40Variant, Unit


@dataclass
class DealReport:
    name: str
    currency: str
    observations: list[Observation]
    issues: list[Issue]
    checks: list[CheckRow]
    metrics: dict[str, dict[str, float | None]]   # metric -> period -> value
    variant: RuleOf40Variant
    documents: list[str]


def _figure(obs: Observation) -> Figure:
    """An Observation as a Figure, for the calculation layer.

    Standardised values are already whole units of the original
    currency, so the unit is UNITS and no rescaling happens here.
    """
    return Figure(
        value=obs.value_standardised, metric=obs.metric,
        period_label=obs.period_label, basis=obs.basis,
        unit=Unit.UNITS, currency=obs.currency,
        is_adjusted=obs.is_adjusted_as_presented,
    )


def _load(path: Path, document: str, sheet: str | None = None
          ) -> list[Observation]:
    result = extract(path, sheet_name=sheet)
    return [Observation(
        metric=o.metric, period_label=o.period_label,
        value_standardised=o.value_standardised, basis=o.basis,
        currency=o.currency_original, original_label=o.original_label,
        breakdown_axis=o.breakdown_axis, document=document,
        source_ref=o.source_cell,
        is_adjusted_as_presented=o.is_adjusted_as_presented,
        needs_review=o.needs_review, ambiguity_reason=o.ambiguity_reason,
    ) for o in result.observations]


def _pick(observations: list[Observation], metric: str, period: str
          ) -> Observation | None:
    """The one figure to show, or nothing.

    Several sources stating the same figure is corroboration, not a
    conflict, so the figure is shown. Where they genuinely differ this
    returns None and the report shows a dash with the disagreement
    listed beside it — the figure is contested, not missing, and a
    scorecard that quietly picked one would hide that.
    """
    matches = [o for o in observations
               if o.metric == metric and o.period_label == period
               and o.value_standardised is not None]
    if not matches:
        return None

    spread = (max(o.value_standardised for o in matches)
              - min(o.value_standardised for o in matches))
    return matches[0] if spread <= TOLERANCE else None


def build_report(
    name: str,
    workbooks: list[tuple[Path, str, str | None]],
    *,
    variant: RuleOf40Variant,
    bridge_rows: list[dict] | None = None,
) -> DealReport:
    observations: list[Observation] = []
    checks: list[CheckRow] = []
    for path, document, sheet in workbooks:
        observations += _load(path, document, sheet)
        checks += read_checks(path, sheet_name=sheet)

    issues = reconcile(observations, declared_variant=variant,
                       bridge_rows=bridge_rows or ())

    periods = sorted({o.period_label for o in observations})
    actual_periods = [p for p in periods if any(
        o.period_label == p and o.basis == Basis.ACTUAL for o in observations)]

    metrics: dict[str, dict[str, float | None]] = {
        k: {} for k in ("revenue", "revenue_growth", "recurring_share",
                        "gross_margin", "ebitda_margin", "rule_of_40")
    }

    for index, period in enumerate(periods):
        revenue = _pick(observations, "revenue", period)
        metrics["revenue"][period] = (
            revenue.value_standardised if revenue else None)

        prior = periods[index - 1] if index else None
        prior_revenue = _pick(observations, "revenue", prior) if prior else None

        def safe(fn, *args):
            """Calculations raise on inputs that should not be combined.

            In a report that is not a crash: it is a figure that cannot
            honestly be shown, and the reason is already in the issues
            list. Returning None leaves a blank rather than a wrong
            number.
            """
            try:
                return fn(*args)
            except calc.CalculationError:
                return None

        metrics["revenue_growth"][period] = (
            safe(calc.revenue_growth, _figure(prior_revenue), _figure(revenue))
            if prior_revenue and revenue else None)

        recurring = _pick(observations, "recurring_revenue", period)
        metrics["recurring_share"][period] = (
            safe(calc.share_of_total, _figure(recurring), _figure(revenue))
            if recurring and revenue else None)

        gross_profit = _pick(observations, "gross_profit", period)
        metrics["gross_margin"][period] = (
            safe(calc.margin, _figure(gross_profit), _figure(revenue))
            if gross_profit and revenue else None)

        ebitda = (_pick(observations, "adjusted_ebitda", period)
                  or _pick(observations, "ebitda", period))
        metrics["ebitda_margin"][period] = (
            safe(calc.margin, _figure(ebitda), _figure(revenue))
            if ebitda and revenue else None)

        growth_metric = calc.variant_growth_metric(variant)
        current_figures, prior_figures = {}, {}
        for key, src_period, target in (("current", period, current_figures),
                                        ("prior", prior, prior_figures)):
            if src_period is None:
                continue
            for metric in (growth_metric, "revenue", "adjusted_ebitda"):
                found = _pick(observations, metric, src_period)
                if found:
                    target[metric] = _figure(found)
        try:
            metrics["rule_of_40"][period] = calc.rule_of_40(
                variant, current=current_figures, prior=prior_figures)
        except (calc.CalculationError, KeyError):
            metrics["rule_of_40"][period] = None

    currency = next((o.currency for o in observations if o.currency), "?")
    return DealReport(
        name=name, currency=currency, observations=observations,
        issues=issues, checks=checks, metrics=metrics, variant=variant,
        documents=[d for _, d, _ in workbooks],
    )
