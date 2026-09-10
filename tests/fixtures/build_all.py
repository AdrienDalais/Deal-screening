"""Regenerate every fixture from its CompanyTruth.

    python -m tests.fixtures.build_all

The documents and the answer key are always produced together, in one
run, from one source. That is what makes the key trustworthy: there is no
sequence of events in which the documents change and the key does not.
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures import (
    build_answer_key, build_cim, build_cim_slides, build_workbook,
)
from tests.fixtures.companies.thornbury import THORNBURY
from tests.fixtures.truth import CompanyTruth

FIXTURE_ROOT = Path(__file__).resolve().parent
COMPANIES: list[CompanyTruth] = [THORNBURY]

# The slide deck is the primary CIM: it matches the shape of a real
# one. The portrait prose version is kept as a deliberately easy
# regression fixture — when extraction fails on slides, running the
# same prompt against clean prose says immediately whether the
# problem is the format or the logic.
SLIDE_PAGES = 84
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

    slides_path, slide_marks, slide_count = build_cim_slides.build_to_page_count(
        truth, out_dir, SLIDE_PAGES)
    prose_path, _, prose_count = build_cim.build_to_page_count(
        truth, out_dir, FULL_PAGES)
    short_path, _, short_count = build_cim.build_to_page_count(
        truth, out_dir, SHORT_PAGES, suffix="_short")

    # Pages whose figures exist only as pixels: the rasterised chart, and
    # the graphic-only divider carrying no text at all.
    unreadable = sorted({slide_marks["unreadable_chart"],
                         slide_marks["blank_divider"]})
    key_path = build_answer_key.build(
        truth, out_dir, slide_marks, rows,
        cim_filename=slides_path.name, workbook_filename=workbook_path.name,
        unreadable_pages=unreadable)

    return {
        "name": truth.name, "dir": out_dir,
        "slides": slides_path, "slide_pages": slide_count,
        "prose": prose_path, "prose_pages": prose_count,
        "short": short_path, "short_pages": short_count,
        "workbook": workbook_path, "key": key_path,
        "financial_table_page": slide_marks["financial_table"],
        "unreadable": unreadable,
        "defects": len(truth.defects),
    }


def main() -> None:
    for truth in COMPANIES:
        r = build_company(truth)
        print(f"{r['name']}  ->  {r['dir'].relative_to(FIXTURE_ROOT.parent.parent)}")
        print(f"    {r['slides'].name:<32} {r['slide_pages']:>3} pages  "
              f"PRIMARY — financial summary on p.{r['financial_table_page']}")
        print(f"    {r['prose'].name:<32} {r['prose_pages']:>3} pages  "
              f"easy-case regression fixture")
        print(f"    {r['short'].name:<32} {r['short_pages']:>3} pages  "
              f"fast test loop")
        print(f"    {r['workbook'].name:<32}")
        print(f"    {r['key'].name:<32} {r['defects']} defects, "
              f"{len(r['unreadable'])} unreadable page(s)")


if __name__ == "__main__":
    main()
