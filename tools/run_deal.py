"""Run the pipeline over a synthetic deal and print what it found.

    python -m tools.run_deal                # all three companies
    python -m tools.run_deal thornbury      # one

There is no interface yet — step 6 of the week-one scope. This exists so
that the pipeline can be run and inspected now, which is what CLAUDE.md
asks for: see the inputs and the outputs, not only that tests pass.

Every figure printed is derived from reviewed-shape observations and
every finding cites the cell it came from.
"""

from __future__ import annotations

import argparse

from core.pipeline import build_report
from tests.fixtures.build_all import COMPANIES, FIXTURE_ROOT

RULE = "─" * 78


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:,.1f}%"


def _money(value: float | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{currency} {value / 1_000_000:,.1f}m"


def report_for(truth):
    directory = FIXTURE_ROOT / truth.slug
    workbooks = [(directory / f"{truth.slug}_financials.xlsx",
                  f"{truth.slug}_financials.xlsx", None)]
    if truth.management_accounts:
        workbooks.append((
            directory / f"{truth.slug}_management_accounts.xlsx",
            f"{truth.slug}_management_accounts.xlsx", "Management Accounts"))

    bridge = [{"period_label": b.period_label, "opening": b.opening,
               "new_business": b.new_business, "expansion": b.expansion,
               "churn": b.churn, "closing": b.closing} for b in truth.bridge]

    return build_report(truth.name, workbooks,
                        variant=truth.rule_of_40_variant, bridge_rows=bridge)


def show(truth) -> None:
    report = report_for(truth)
    periods = sorted(report.metrics["revenue"])

    print(f"\n{RULE}\n{report.name}   {report.currency}   "
          f"year end month {truth.fiscal_year_end_month}\n{RULE}")
    print(f"documents  : {', '.join(report.documents)}")
    print(f"observations: {len(report.observations)}")
    print(f"rule of 40 : {report.variant.value}")

    print(f"\nSCORECARD")
    header = f"  {'':<22}" + "".join(f"{p:>11}" for p in periods)
    print(header)
    print("  " + "─" * (len(header) - 2))

    rows = [
        ("Revenue", "revenue", lambda v: _money(v, report.currency)),
        ("Revenue growth", "revenue_growth", _pct),
        ("Recurring share", "recurring_share", _pct),
        ("Gross margin", "gross_margin", _pct),
        ("EBITDA margin", "ebitda_margin", _pct),
        ("Rule of 40", "rule_of_40", _pct),
    ]
    for label, key, fmt in rows:
        cells = "".join(f"{fmt(report.metrics[key].get(p)):>11}"
                        for p in periods)
        print(f"  {label:<22}{cells}")

    print(f"\n  A dash means the figure cannot honestly be shown: either it")
    print(f"  is absent, or sources disagree and nothing has been chosen.")

    print(f"\nFINDINGS  ({len(report.issues)})")
    if not report.issues:
        print("  none")
    for issue in report.issues:
        print(f"\n  [{issue.severity.value.upper():<8}] {issue.check}")
        text = issue.message
        while text:
            print(f"    {text[:72]}")
            text = text[72:]
        print(f"    fingerprint {issue.fingerprint}")

    unevaluable = [c for c in report.checks if not c.evaluable]
    print(f"\nWORKBOOK CONTROLS  ({len(report.checks)} found, "
          f"{len(unevaluable)} not evaluable)")
    for check in report.checks:
        mark = "ok" if check.evaluable else "NOT EVALUABLE"
        print(f"  [{mark:<13}] {check.label}")
        if check.reason:
            print(f"                  {check.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company", nargs="?",
                        choices=[c.slug for c in COMPANIES])
    args = parser.parse_args()

    chosen = ([c for c in COMPANIES if c.slug == args.company]
              if args.company else COMPANIES)
    for truth in chosen:
        show(truth)
    print()


if __name__ == "__main__":
    main()
