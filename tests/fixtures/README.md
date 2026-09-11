# Synthetic fixtures

**Every company here is invented.** No figure, name, date or source
reference derives from a real deal. These files are safe to commit, share
and demonstrate.

## Why they are generated rather than written

Each company has one source of truth — a `CompanyTruth` object in
`companies/`. The CIM, the financials workbook and the answer key are all
rendered from it in a single run:

```
                    ┌──→  <slug>_cim_slides.pdf   PRIMARY — 84-page deck
truth (one object) ─┼──→  <slug>_cim.pdf          easy-case regression
                    ├──→  <slug>_cim_short.pdf    fast test loop
                    ├──→  <slug>_financials.xlsx
                    └──→  expected.json           the answer key
```

If the documents were written by hand, the "correct" answer would be
whatever we remembered putting in them, and the answer key would drift
silently every time a fixture was tweaked. Generating them together makes
the key correct by construction.

## Rebuilding

```bash
python -m tests.fixtures.build_all
```

Deterministic: the same truth always produces the same key. Verified by
`tests/test_fixtures.py::test_rebuilding_produces_an_identical_answer_key`.

## The two scores

The answer key has two independent halves, and conflating them would make
both meaningless.

| Score | Measured against | Example |
|---|---|---|
| **Extraction** | What each document literally says, defects included | The mis-keyed cost of sales cell must be extracted as `-3.5` |
| **Reconciliation** | `expected_reconciliation_findings` | The same cell must be *reported* as wrong |

An extractor that "helpfully" corrects a figure is failing, not helping.
Silently repairing a document is the behaviour this system exists to
prevent.

## Three CIM variants, and why

The **slide deck is the primary fixture**. A CIM arrives as a PowerPoint
export, and that is a different extraction problem from a flowing
document: text comes back as positioned fragments with no guaranteed
reading order, and some figures live only inside images.

`build_cim_slides.py` was calibrated against a real 84-page IM,
characterised with `tools/inspect_pdf.py` — which reports structure only,
so a confidential document can be measured without any part of it being
disclosed:

| | Real IM | Fixture |
|---|---|---|
| pages | 84 | 84 |
| geometry | 960 x 540 pt | 960 x 540 pt |
| median characters per page | 1,156 | 1,006 |
| median text runs per page | 44 | 30 |
| reading-order disorder | 18% | 17% |
| pages under 200 characters | 17% | 18% |
| pages with no text at all | 1 | 1 |

Reading-order disorder is the number that matters most. Slide elements
are emitted in a *partially* shuffled z-order — tuned by the `DISORDER`
constant — because PowerPoint writes text boxes in creation order rather
than reading order. A fixture drawn tidily top-to-bottom would let us
build an extractor that quietly depends on reading order and then fails
on every real document. A full shuffle was also wrong: it gave 48%
disorder, making the fixture harder than reality rather than equal to it.

The **portrait prose CIM** (~81 pages) is kept as a deliberately easy
case. When extraction fails on slides, running the same prompt against
clean prose says immediately whether the problem is the format or the
logic. The **short variant** (~24 pages) keeps the fast test loop fast.

## Content that cannot be read

Two pages hold figures that text extraction cannot recover: a bar chart
rendered as pixels, and a graphic-only divider with no text at all. They
are listed in `pages_requiring_ocr_or_flagging`.

**Reporting them as unread is correct. Reporting them as empty is not.**
A screening tool that silently omits what it could not parse produces a
confident answer with a hole in it, which is worse than one that refuses.

## Decoy figures

`prose.py` scatters currency amounts through the narrative that are *not*
company revenue: a customer's ARR, the market size, historical funding
rounds, deferred income. 79 of 81 pages carry a currency figure, so
retrieval has to discriminate rather than find the only page that
mentions money. An extractor that grabs the nearest plausible figure to
the word "revenue" returns the Series A.

## Companies

### Thornbury Analytics — GBP, December year end

UK insurance-pricing SaaS. The straightforward one: clean growth, clean
margins, no structural oddities, so its three defects are testable
without other noise.

| Defect | What it is | Genuine error? |
|---|---|---|
| Re-keying scale slip | FY23 cost of sales entered as `3.5` in a sheet denominated in thousands | Yes |
| Exec summary restatement | Exec summary says FY24 revenue £15.1m (continuing operations); financial summary says £15.4m | **No** — must stop being raised once explained |
| Adjusted EBITDA mislabelled | CIM row prints as "EBITDA"; figure is after exceptional items | Yes |
| ARR bridge does not tie | FY24 bridge sums correctly to 14.4 and prints 14.4; the financial summary shows ARR of 14.1 | Yes |

### Larkspur Systems — EUR, June year end

Irish logistics SaaS. **FY24 runs 1 July 2023 to 30 June 2024** — anything
assuming FY24 means calendar 2024 breaks here.

| Defect | What it is | Genuine error? |
|---|---|---|
| Forecast inside the historical block | The merged "Historicals" header spans four columns rather than three, so FY25 sits under it while its own label reads FY25E | Yes |
| Rule of 40 label mismatch | Stated as "CARR growth plus EBITDA margin"; the company reports no CARR anywhere | Yes |

The first is deliberately subtle: two signals *within one sheet*
disagree, which is how it survives review in practice. Any growth rate
or margin spanning FY24 and FY25 crosses a change of basis and must be
refused or flagged, never reported.

### Calderwood Health — USD, March year end

US healthcare revenue-cycle software. Ships a **third document**: management
accounts issued after the CIM.

| Defect | What it is | Genuine error? |
|---|---|---|
| Documents disagree on revenue | CIM shows FY24 revenue 31.8; management accounts show 30.9, restated to exclude a divested clinic line | Neither document is wrong |
| Overlapping opex breakdowns | Operating costs presented both by nature and by function for the same cost base; each axis sums to total opex on its own | Yes, if summed across axes |
| Inert check formula | A control referencing a named range that does not exist, displayed as though it worked | Yes |

The first is the reason `financial_observations` carries no uniqueness
constraint on (deal, metric, period): **both figures stay live, and
neither is silently preferred.** The second is why `breakdown_axis`
exists — summing every expense row gives exactly twice total operating
expenses.
