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

## Step 2a revised — the fixture format was wrong (2026-09-10)

**What changed.** The CIM fixture was rebuilt as an 84-page landscape
slide deck, because that is what a CIM actually is. The portrait prose
version is kept as a deliberately easy regression case.

**How we knew.** `tools/inspect_pdf.py` reports a PDF's structure and
nothing else — page geometry, text density, fragmentation, image sizes.
No words, no figures. That let a confidential IM be characterised without
any part of it being disclosed, which is the same principle as the local
model provider: the measurement goes to the document, not the document to
the measurer.

**Design decision.** Slide elements are emitted in a partially shuffled
z-order, tuned to match the 18% reading-order disorder measured on a real
deck. PowerPoint writes text boxes in creation order, not reading order.

**Alternative rejected.** Drawing slides tidily top to bottom. It would
have let us build an extractor that quietly depends on reading order and
then fails on every real document. A *full* shuffle was rejected too —
48% disorder, harder than reality rather than equal to it.

**Two instrument errors caught, both the same mistake.** The reading-order
metric first reported 47% disorder on a document of pure prose, because
PDF text matrices are relative to the current transformation matrix. The
image metric reported "an image covers 25% of the page on 84 of 84
pages", because it assumed 96 DPI and a background template tripped it
everywhere. Both produced confident, meaningless numbers until tested
against a document whose answer was already known.

**Interviewer question.** *"How did you validate your fixtures against
reality without access to real documents?"*
By measuring structure rather than content. The inspector emits only
counts and dimensions, so it can run against a confidential file and the
output discloses nothing. The fixture was then tuned until its structural
profile matched — page geometry, text density, fragmentation, the share
of pages carrying no text. That is a weaker guarantee than validating
against real content, and I would say so: it establishes the fixture is
the right *shape*, not that it is representative in substance.

---

## Step 2b — Larkspur and Calderwood (2026-09-11)

**What we built.** Two more fixture companies, in the slide format, and
the machinery their defects needed: an over-spanning merged header, an
inert check formula, and a second restating document.

**Design decision.** The internal consistency check is now driven by
`breakdown_axis` rather than by hardcoded metric names. Calderwood
presents operating costs twice — by nature and by function — for one cost
base, so each axis is checked against total opex independently. Summing
every expense row gives exactly twice the real figure.

**Alternative rejected.** Listing the expense metrics to sum. It worked
for one company and would have silently double counted the moment a
second axis appeared, which is precisely the error the field exists to
prevent.

**Why three year ends.** December, June and March. Larkspur's FY24 runs
July 2023 to June 2024. Any code assuming a fiscal year matches a
calendar year now fails a test rather than producing a plausible wrong
answer on a live deal.

**The defect I am most pleased with.** Calderwood's CIM says FY24 revenue
was 31.8; its management accounts, issued later, say 30.9 — restated to
exclude a divested line. Neither document is wrong. This is the case the
whole schema was built around, and until now nothing exercised it.

**Interviewer question.** *"Two of your documents disagree. Which one
does your system believe?"*
Neither, and that is the design. Both observations stay live, each
carrying its own source and basis, and the conflict is surfaced rather
than resolved. `financial_observations` has no uniqueness constraint on
(deal, metric, period) specifically so that this is representable. What
gets stored is the analyst's explanation of *why* they differ — decision
011 — so the finding is raised once rather than every time the deal is
opened.

---

## Step 3 — Calculations: signatures and specification (2026-09-11)

**What Claude built.** `core/calculations.py` as signatures, docstrings
and worked examples, plus 31 tests in `tests/test_calculations.py` with
every expected value computed from the fixtures and shown with its
arithmetic. The bodies are mine to write.

**The design decision.** Every function takes `Figure` objects, not bare
floats. A function handed `(11_600_000, 15_400_000)` can divide them but
cannot know that one is an actual and the other a forecast, or that they
are in different currencies. It returns 32.8% growth, confidently, and is
wrong in a way nobody can see. Passing the context alongside the number
is what allows the function to refuse.

**Alternative rejected.** Bare floats with validation performed by the
caller. Simpler functions, but the check then lives in every call site
and is omitted in one of them eventually — and the failure is silent.

**The distinction I have to hold while writing these.** Returning None
and raising are not interchangeable. None means the inputs were fine and
the answer does not exist: a figure is missing, a denominator is zero.
Raising means the inputs should never have been combined. Conflating
them either hides a real data problem or turns an ordinary gap into a
crash.

**Interviewer question.** *"Why does your growth function raise on a
forecast rather than returning the number with a warning?"*
Because a warning has to be carried, displayed and read, and at some
point it will not be. The number would be in the scorecard regardless.
Growth from an actual to a management forecast is not a growth rate, it
is a plan; there is no context in which reporting it as growth is
correct, so the function should not be able to produce it.

---

## Step 4a — Excel extraction, the deterministic control (2026-09-11)

**What we built.** `ingestion/labels.py` maps printed labels onto
metrics; `ingestion/excel.py` reads a workbook directly with openpyxl,
preserving every cell reference. No model involved.

**Design decision.** Spreadsheets are not sent to an LLM. A fixed-layout
sheet is a solved problem, and a model would add cost, latency and a
failure mode in exchange for nothing. More usefully, this becomes the
control: when LLM extraction from a PDF scores 94%, the question is
whether the missing 6% is the model or the pipeline, and a deterministic
path scoring 100% on the same fixtures answers it.

**The rule the extractor follows.** It transcribes; it never corrects.
Thornbury's mis-keyed cost of sales comes back as -3.5, not -3,500.
An extractor that repairs figures destroys the evidence that the
document was wrong, which on a real deal is often the most valuable
thing found.

**What it does when a document contradicts itself.** Larkspur's FY25
column is labelled as a forecast and sits under a merged header reading
"Historicals". The extractor records both signals, flags the row, and
declines to choose. Which is right is a judgement, and judgements belong
to the analyst.

**Interviewer question.** *"Your extractor found a cell that is obviously
wrong by a factor of 1,000. Why not fix it?"*
Because the two jobs have different correct answers. Extraction is scored
on faithful transcription, reconciliation on catching errors, and they
carry separate accuracy numbers. If extraction silently repaired the
cell, reconciliation would find nothing, the scorecard would look clean,
and nobody would ever learn that the model handed over by the seller had
a broken formula in it.

---

## Step 3 complete — calculations (2026-10-21)

**What exists.** Six functions, 31 tests, all passing. Growth, CAGR,
share of total, margin, the Rule of 40 variant mapping, and Rule of 40
itself.

**The design decision, made before any code.** Every function takes a
`Figure` — value plus currency, unit, basis and period — rather than a
bare float. A function handed two numbers can divide them but cannot know
that one is an actual and the other a forecast. It returns a confident,
invisible error.

**The distinction the module is built on.** Raising and returning None
are not interchangeable. None means the inputs were fine and no answer
exists: a figure is missing, a denominator is zero, a compound rate
crosses zero. Raising means the inputs should never have been combined.

**A validation that came free.** `cagr` with `years=1` must equal
`revenue_growth` exactly, and a test asserts it. Two independent
implementations agreeing is stronger evidence than either one looking
right.

**Honest note on authorship.** See docs/DECISIONS.md #012. Claude wrote
most of these implementations with line-by-line explanation, after four
failed attempts that failed on Python syntax rather than on the finance.
I wrote the arithmetic of `revenue_growth` myself.

**Interviewer question.** *"Walk me through why your growth function
raises instead of returning a number."*
Growth from an actual to a management forecast is not a growth rate, it
is a plan. A warning would have to be carried, displayed and read, and
eventually one of those fails while the number sits in the scorecard
regardless. There is no context in which reporting it as growth is
correct, so the function should not be able to produce it.

---

## Step 5 — Reconciliation (2026-10-21)

**What exists.** Ten checks, 42 tests, and an end-to-end suite that runs
extraction and reconciliation over the fixtures on disk and verifies each
planted defect produces a finding.

**Design decision.** Every issue carries a fingerprint: a hash of the
check, metric, period and the figures involved. A resolution recorded
against a fingerprint survives recomputation, and changing any figure
changes the fingerprint — which invalidates the resolution
automatically. That is the mechanism behind decision 011: issues stay
computed, resolutions get stored.

**Severity distinguishes three things, not two.** ERROR means a figure is
demonstrably wrong. DISAGREE means two sources differ and neither is
necessarily wrong. WARNING means worth a look. Collapsing DISAGREE into
ERROR would mean a CIM restating a figure on a different basis looked
like a mistake, and the issues list would be ignored within a week.

**Two defects were silently not caught, and running it end to end was
the only way to find out.** Both unit test suites passed completely while
two of the nine planted defects produced no finding at all.

The first: the extractor dropped `breakdown_axis`, so the
overlapping-opex check had nothing to work with. The fix had a trap in
it — the axis is a property of the *sheet*, not the metric. Thornbury's
"Personnel" sits inside a functional breakdown; Calderwood's is half of a
breakdown by nature presented beside a functional one. A static
metric-to-axis map would have double counted the first and missed the
second, so it is inferred per sheet.

The second: extraction resolves Larkspur's contradictory basis signal to
one value and flags the row, so by the time reconciliation saw it there
was one basis per period and nothing to find. The flag was correct; it
just never travelled. A defect detected and not reported is a defect
missed.

**Interviewer question.** *"Your unit tests all passed and two of nine
defects weren't caught. What does that tell you about your tests?"*
That they tested the components and not the seams. Each check worked on
data constructed to exercise it, and the data it actually receives is
built by a different module that was dropping a field. The fix was a
suite that runs the real pipeline over the real fixtures and asserts on
declared defects rather than on function behaviour — and that suite is
now the one I would run first.

---

## Step 6 — The interface (2026-10-21)

**What exists.** A Streamlit app with four tabs: scorecard, findings,
evidence, and a comparison across deals. `app/` contains formatting and
nothing else — every figure on screen comes from `core/pipeline.py`,
which the test suite covers. The app cannot compute a number of its own.

**Design decision.** A blank cell in the scorecard is never a zero and
never a rounding. It means the figure cannot honestly be shown, for one
of three reasons: it is absent, two sources state it differently and
neither has been chosen, or the calculation would have spanned a change
of basis. The reason is always in the findings tab.

**Alternative rejected.** Showing the figure with a warning icon. The
number would be read, the icon would not, and by the time it reached a
paper the caveat would be gone. If a figure cannot be defended it should
not be displayed.

**What the comparison tab deliberately does not have.** An overall score.
Three currencies and three year ends sit in that table — Larkspur's FY24
runs July to June, Calderwood's April to March. The figures are
comparable; the companies are not reducible to one number, and producing
one would be the single most misleading thing this tool could do.

**Interviewer question.** *"Why is there no business logic in the
interface?"*
Because anything computed there is untested and unversioned. If a margin
were worked out in a Streamlit callback it would exist in exactly one
place, be covered by no test, and disagree with the same margin computed
anywhere else the moment either changed. The app formats what the
pipeline produces.

---
