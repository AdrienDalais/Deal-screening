"""Regenerate every fixture from its CompanyTruth.

    python -m tests.fixtures.build_all

The documents and the answer key are always produced together, in one
run, from one source. That is what makes the key trustworthy: there is no
sequence of events in which the documents change and the key does not.
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures import build_answer_key, build_cim, build_workbook
from tests.fixtures.companies.thornbury import THORNBURY
from tests.fixtures.truth import CompanyTruth

FIXTURE_ROOT = Path(__file__).resolve().parent
COMPANIES: list[CompanyTruth] = [THORNBURY]

FULL_PAGES = 85
SHORT_PAGES = 25


def build_company(truth: CompanyTruth) -> dict[str, object]:
    problems = truth.check_internal_consistency()
    if problems:
        raise AssertionError(
            f"{truth.name}: the truth is not internally consistent, so any "
            f"reconciliation finding against it would be meaningless:\n  "
            + "\n  ".join(problems)
        )

    out_dir = FIXTURE_ROOT / truth.slug
    workbook_path, rows = build_workbook.build(truth, out_dir)
    cim_path, pages, page_count = build_cim.build_to_page_count(
        truth, out_dir, FULL_PAGES)
    short_path, _, short_count = build_cim.build_to_page_count(
        truth, out_dir, SHORT_PAGES, suffix="_short")
    key_path = build_answer_key.build(
        truth, out_dir, pages, rows,
        cim_filename=cim_path.name, workbook_filename=workbook_path.name)

    return {
        "name": truth.name, "dir": out_dir,
        "cim": cim_path, "cim_pages": page_count,
        "short": short_path, "short_pages": short_count,
        "workbook": workbook_path, "key": key_path,
        "financial_table_page": pages["financial_table"],
        "defects": len(truth.defects),
    }


def main() -> None:
    for truth in COMPANIES:
        r = build_company(truth)
        print(f"{r['name']}  ->  {r['dir'].relative_to(FIXTURE_ROOT.parent.parent)}")
        print(f"    {r['cim'].name:<30} {r['cim_pages']:>3} pages   "
              f"financial summary on p.{r['financial_table_page']}")
        print(f"    {r['short'].name:<30} {r['short_pages']:>3} pages")
        print(f"    {r['workbook'].name:<30}")
        print(f"    {r['key'].name:<30} {r['defects']} planted defects")


if __name__ == "__main__":
    main()
