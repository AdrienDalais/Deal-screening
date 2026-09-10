# Synthetic fixtures

**Every company here is invented.** No figure, name, date or source
reference derives from a real deal. These files are safe to commit, share
and demonstrate.

## Why they are generated rather than written

Each company has one source of truth — a `CompanyTruth` object in
`companies/`. The CIM, the financials workbook and the answer key are all
rendered from it in a single run:

```
                    ┌──→  <slug>_cim.pdf          (full length)
truth (one object) ─┼──→  <slug>_cim_short.pdf    (fast test loop)
                    ├──→  <slug>_financials.xlsx
                    └──→  expected.json           (the answer key)
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

## Two document lengths

The full CIM runs to ~81 pages, matching the 80-100 of a real one. That
length is deliberate: a fixture small enough to fit in a single model
call would let us build a pipeline that works against a hosted model in a
demo and fails on the local model — which is the only provider
`confidential` deals are permitted to use.

The short variant is ~24 pages with identical figures, defects and
decoys, for the fast test loop.

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

### Larkspur Systems — EUR, June year end

*Not yet built.* Forecasts inside the historical table (the merged
header spans one column too far); Rule of 40 labelled "(CARR + EBITDA)"
but computed from ARR growth, with no CARR line present.

### Calderwood Health — USD, March year end

*Not yet built.* CIM and management accounts disagree on the same year's
revenue; overlapping opex breakdowns by nature and by function; a check
formula that errors permanently.
