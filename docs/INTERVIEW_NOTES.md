# Interview notes

Short, honest notes after each step. What we built, the design decision,
the alternative we rejected, and a question an interviewer might ask.

---

## Step 0 — Project skeleton (2026-09-09)

**What we built.** Directory structure, `.gitignore`, `.env.example`,
`requirements.txt`, and the three docs files. No logic yet.

**Design decision.** `.gitignore` was written *before* the first
`git add`, listing `.env`, `data/` and `deals_private/`.

**Alternative rejected.** Adding `.gitignore` later, once there was
something to ignore. Rejected because removing a file from git history
after the fact is genuinely painful, and the file you most need to remove
is the one you least want to have leaked.

**Interviewer question.** *"Why is confidentiality a property of the deal
rather than of the document?"*
Because the question the code has to answer before every API call is "may
anything from this deal leave this machine?", and that must have exactly
one answer. If the setting were per-document, one mislabelled file leaks
the deal. One setting per deal, applied conservatively to everything
underneath it.

---

## Step 1 — Schema and storage (2026-09-09)

**What we built.** Eleven tables in `storage/models.py`, a controlled
vocabulary in `storage/enums.py`, Alembic wired to the models, and eleven
tests that assert the schema's promises rather than its plumbing.

**Design decision.** `financial_observations` has *no* uniqueness
constraint on (deal, metric, period). Two documents disagreeing about
FY23 revenue produce two live rows, and finding the disagreement is a
one-line GROUP BY rather than an error that blocks the insert.

**Alternative rejected.** A "current value" table with an audit log
beside it. Easier to query, but it forces a single truth to exist at all
times and destroys the record of what the extractor originally produced —
which is the only data we have for measuring whether extraction works.

**A second decision worth defending.** The rule that confidential deals
never reach a hosted model is written as a database CHECK constraint, not
only as a guard in `llm/`. A rule that important should be true of the
data, not only of the code path that happens to be running. It is
defence in depth: the application check gives a good error message, the
database check means a bug in the application cannot produce a row that
records a confidentiality breach.

**Interviewer question.** *"Why store both the original value and a
standardised one? Isn't that duplication?"*
It is, and it is deliberate. The original is what the document printed —
12.4 in a table headed "millions". The standardised value is 12,400,000.
If the scale is later found to have been misread, keeping the original
means fixing one conversion and re-deriving. Keeping only the
standardised figure means going back to the PDF for every affected row.
The duplication buys back the ability to correct a systematic error
cheaply.

**Follow-up an interviewer would ask.** *"Why not standardise the
currency too?"* Because an FX rate baked into a stored number is a hidden
assumption you cannot find again. Scale is a property of how the document
printed the figure; a exchange rate is an analytical choice with a date
attached. Scale gets normalised, currency gets carried.

---

## Step 2a — Synthetic fixtures, Thornbury (2026-09-10)

**What we built.** A generator that renders one `CompanyTruth` object as
a CIM (81 pages), a financials workbook, and the answer key — in one run,
from one source. Fourteen tests read the rendered files back off disk and
check the key describes the documents that actually exist.

**Design decision.** The answer key is generated, never written. If the
documents were handmade, the "correct" answer would be whatever I
remembered putting in them, and the key would drift silently every time a
fixture was tweaked. We would be measuring accuracy against a ruler that
moves.

**Alternative rejected.** Three PDFs made by hand in Word, with the
expected figures typed into a spreadsheet beside them. Faster to start,
and wrong within a week.

**A decision I got wrong first.** I planned 25-page CIMs because
generating filler was tedious. That would have hidden the fact that an
80-page CIM does not fit in the context window of a local model — and the
local model is the *only* provider confidential deals may use. We would
have built something that demos beautifully and fails on the deals that
matter most. Length is now a parameter, so both variants come from one
code path.

**The thing I did not anticipate.** `pypdf` returns a PDF table as a flat
vertical stream — every column header, then every row label, then every
number, with the grid gone. Extraction has to *reconstruct* the table.
Much better to meet that in a fixture than on a live deal.

**Interviewer question.** *"Your extractor reads a cell that obviously
holds a typo. Should it correct it?"*
No, and treating that as a feature would be the mistake. Extraction is
scored on faithful transcription, including of the document's errors;
reconciliation is scored on catching them. They are separate systems with
separate accuracy numbers. An extractor that quietly repairs figures
destroys the evidence that the document was wrong — which on a real deal
is often the most valuable thing you have found.

---
