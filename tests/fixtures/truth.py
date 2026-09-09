"""The single source of truth for each synthetic company.

Every fixture is generated from one of these objects: the CIM, the
financials workbook, and the answer key all come from the same data.

That is the whole point. If the documents were written by hand, the
"correct" answer would be whatever we remembered putting in them, and the
answer key would drift silently every time a fixture was tweaked. Because
the key is generated alongside the documents, it is correct by
construction.

All values are stored in **whole units of the company's reporting
currency** — 8_200_000, not 8.2 and not 8,200. Each generator then
renders at whatever scale that document uses. The scale differences
between documents are therefore produced deliberately, in one place,
rather than being a property of how someone typed the number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from storage import enums as E


@dataclass(frozen=True)
class Period:
    """One reporting period, with real dates.

    `label` is what the documents print. `basis` is the truth about what
    kind of figure it holds — which a document may or may not state
    correctly. That gap is where defects live.
    """

    label: str
    start: date
    end: date
    basis: E.Basis


@dataclass(frozen=True)
class LineItem:
    """One row of the financials, across all periods.

    Two labels because documents disagree about wording, and preserving
    both is what lets us test whether the extractor maps them correctly:
    a CIM saying "Turnover" and a workbook saying "Revenue" must both
    arrive as metric `revenue`.
    """

    metric: str
    cim_label: str
    workbook_label: str
    values: dict[str, float]              # period label -> whole units
    is_adjusted: bool = False
    adjustment_note: str | None = None
    breakdown_axis: E.BreakdownAxis = E.BreakdownAxis.NOT_APPLICABLE
    is_cost: bool = False                 # printed negative in the workbook


@dataclass(frozen=True)
class Defect:
    """A deliberate flaw, and what finding it looks like.

    `expected_detection` is the contract with the reconciliation module:
    if reconciliation cannot produce this finding, it has failed on this
    fixture. It is written in plain language because it also serves as
    the description in the evaluation report.
    """

    key: str
    kind: str
    where: str
    description: str
    expected_detection: str
    # Some differences are legitimate and must NOT be reported as errors
    # once the analyst has explained them. See docs/DECISIONS.md #011.
    is_genuine_error: bool = True


@dataclass(frozen=True)
class Kpi:
    """A metric asserted in the CIM narrative rather than in a table.

    These become `claims`, not `financial_observations`: they are
    assertions to be tested, not figures to be recalculated.
    """

    key: str
    label: str
    stated_text: str
    value: float | None
    unit: E.Unit
    period_label: str | None = None


@dataclass(frozen=True)
class CompanyTruth:
    name: str
    sector: str
    subsector: str
    country: str
    currency: str
    fiscal_year_end_month: int

    # Scale each document is printed at. The CIM quotes millions; the
    # working model runs in thousands. That difference is normal
    # practice, not a defect — the defect is a conversion done wrong.
    cim_unit: E.Unit
    workbook_unit: E.Unit

    rule_of_40_variant: E.RuleOf40Variant

    periods: list[Period]
    line_items: list[LineItem]
    kpis: list[Kpi] = field(default_factory=list)
    narrative: dict[str, str] = field(default_factory=dict)
    filler_sections: list[tuple[str, str]] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)

    # ---------------------------------------------------------------
    def period(self, label: str) -> Period:
        for p in self.periods:
            if p.label == label:
                return p
        raise KeyError(f"{self.name}: no period labelled {label!r}")

    def item(self, metric: str) -> LineItem:
        for i in self.line_items:
            if i.metric == metric:
                return i
        raise KeyError(f"{self.name}: no line item for metric {metric!r}")

    @property
    def actual_periods(self) -> list[Period]:
        return [p for p in self.periods if p.basis == E.Basis.ACTUAL]

    @property
    def slug(self) -> str:
        return self.name.lower().split()[0]

    def check_internal_consistency(self) -> list[str]:
        """Verify the truth is arithmetically sound before we distort it.

        A fixture built on inconsistent numbers would fail reconciliation
        for reasons that have nothing to do with the planted defects, and
        we would never know which was which.
        """
        problems: list[str] = []

        def value(metric: str, label: str) -> float | None:
            try:
                return self.item(metric).values.get(label)
            except KeyError:
                return None

        for p in self.periods:
            checks = [
                ("revenue = recurring + non-recurring", "revenue",
                 ["recurring_revenue", "non_recurring_revenue"]),
                ("gross profit = revenue - cogs", "gross_profit",
                 ["revenue", "-cogs"]),
                ("total opex = personnel + s&m + g&a", "total_opex",
                 ["personnel_expenses", "sales_and_marketing", "general_and_admin"]),
            ]
            for name, total_metric, parts in checks:
                total = value(total_metric, p.label)
                if total is None:
                    continue
                summed = 0.0
                missing = False
                for part in parts:
                    negate = part.startswith("-")
                    v = value(part.lstrip("-"), p.label)
                    if v is None:
                        missing = True
                        break
                    summed += -v if negate else v
                if missing:
                    continue
                if abs(summed - total) > 1.0:
                    problems.append(
                        f"{p.label}: {name} — expected {total:,.0f}, "
                        f"components give {summed:,.0f}"
                    )

            gp = value("gross_profit", p.label)
            opex = value("total_opex", p.label)
            adj = value("ebitda_adjustments", p.label) or 0.0
            ebitda = value("adjusted_ebitda", p.label)
            if None not in (gp, opex, ebitda):
                expected = gp - opex + adj
                if abs(expected - ebitda) > 1.0:
                    problems.append(
                        f"{p.label}: adj. EBITDA — expected {ebitda:,.0f}, "
                        f"gross profit less opex plus adjustments gives {expected:,.0f}"
                    )

        return problems
