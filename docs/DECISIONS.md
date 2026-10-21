# Decision log

Every architectural decision, with the date and the reason.
Newest last.

---

## 2026-09-09 — 001: SQLite via SQLAlchemy, with Alembic from day one

**Decision.** Store everything in a single SQLite file, accessed through
SQLAlchemy, with Alembic migrations from the very first schema.

**Why.** SQLite is a single file — easy to back up, easy to inspect by
hand with the `sqlite3` command, and it needs no server. SQLAlchemy means
the move to Postgres later is a connection-string change rather than a
rewrite. Alembic from day one because the schema *will* change, and
without migrations the only way to change it is to delete the database
and lose the reviewed data.

**Rejected.** Storing extractions as JSON files. Fast to start, but no
way to query across deals, and no way to enforce that every observation
carries its source reference.

---

## 2026-09-09 — 002: The database is a ledger of observations, not a table of figures

**Decision.** One row in `financial_observations` = one number as it
appeared in one place in one document. Rows are immutable. Corrections
create new rows and mark old ones superseded. No uniqueness constraint on
(deal, metric, period).

**Why.** The absent uniqueness constraint is the important part. Two
documents disagreeing about FY23 revenue must be able to coexist as two
live rows. A unique constraint would force the system to silently pick
one — the exact behaviour we are building this tool to prevent.

**Rejected.** A "current value" table with an audit log beside it. Simpler
to query, but it forces a single truth to exist at all times, and it
destroys the record of what the extractor originally produced — which is
the only data we have for measuring whether the extractor is any good.

---

## 2026-09-09 — 003: Calculated metrics are computed on demand, never stored

**Decision.** Revenue growth, margins and Rule of 40 are computed by pure
functions in `core/calculations.py` from reviewed observations, every time
they are needed. They are not written to the database.

**Why.** A stored derived value can go stale relative to a correction.
Computing on demand makes "a correction recalculates dependent metrics"
free — there is nothing to recalculate, because calculated figures are
always live.

**Trade-off accepted.** Slower at scale. At three deals it is instant; if
it becomes slow we add a cache, which is a much easier problem than
hunting stale derived values.

**Exception.** Narrative text *is* stored and *can* go stale. Paper
sections therefore record which observations they were written from and
are marked stale when any of those change.

---

## 2026-09-09 — 004: Reconciliation issues are also computed on demand

**Decision.** `core/reconciliation.py` is a pure function returning a list
of issues. Issues are not persisted.

**Why.** Same reasoning as 003. An issue list stored in the database can
disagree with the data it describes.

---

## 2026-09-09 — 005: An eighth table, `information_requests`

**Decision.** Add `information_requests` (linked to a screening decision:
question, category, status) as a table in its own right.

**Why.** The information-request list generated with a screening decision
has to be editable and trackable — items get answered one at a time. A
JSON blob on the decision row cannot express "this question was answered
on the 14th".

---

## 2026-09-09 — 006: Standardisation is scale only. Currency is never converted.

**Decision.** `value_standardised` is the figure expressed in whole units
of the **original currency** (12,400,000 rather than 12.4). Currency is
carried through unchanged; no FX conversion is ever applied to a stored
figure.

**Why.** An FX rate baked into a stored number is a hidden assumption that
becomes impossible to find later. Scale, by contrast, is a property of
how the document printed the number, and normalising it removes a whole
category of error. Where a comparison genuinely needs a common currency,
the rate is an explicit, visible input at the point of comparison.

---

## 2026-09-09 — 007: Plain venv and requirements.txt, not Poetry or uv

**Decision.** Standard library `venv`, `pip`, and a `requirements.txt`.

**Why.** Slower than uv and less rigorous than Poetry, but it is the setup
every tutorial and every interviewer assumes, and there is no tool sitting
between the user and what is actually happening. The goal is a system its
author can explain end to end.

**Revisit when.** Dependency resolution starts costing real time.

---

## 2026-09-09 — 008: Rule of 40 has a default variant, set per deal, never assumed

**Decision.** The default variant is **ARR growth % + EBITDA margin %**.
Where a deal reports signed CARR, the variant may be set to
**CARR growth % + EBITDA margin %**. A revenue-growth variant is also
supported. The choice is stored on the deal record, printed in the row
label wherever the metric appears, and recorded alongside the specific
observation IDs that fed the calculation.

**Why.** ARR + EBITDA is the normal case. CARR is used on deals where
signed but not yet live contracts are the meaningful measure of momentum
— that is a real, deal-specific judgement, so the system must hold it as
configuration rather than as a hardcoded formula.

**The check this makes possible.** Reconciliation compares the variant
named in the label against the inputs actually used. A row labelled
"CARR + EBITDA" whose formula reads an ARR growth cell is a **hard
error**, not a warning. This exact mismatch was found in a real working
template — the same metric name computed from different inputs on two
sheets of one workbook — which is why it is treated as an error.

**Rejected.** Picking one definition and enforcing it everywhere. Cleaner
to implement, but it would silently rewrite the analyst's judgement, and
on a deal where CARR is the right measure it would produce a number that
looks authoritative and is wrong.

**Consequence for the comparison table.** Two deals using different
variants may not appear in the same column under one heading. The
comparison view either splits the column by variant or shows the variant
name against each figure.

---

## 2026-09-09 — 009: Six schema additions derived from existing working templates

**Decision.** Reviewing real working templates before designing the
schema surfaced six requirements that were not obvious from first
principles. All six are adopted:

1. **Sign convention.** Costs arrive negative, so gross profit is revenue
   *plus* COGS. Normalised to positive magnitudes on storage, with the
   source convention recorded on the observation.
2. **`breakdown_axis`** on expense observations (`by_nature` /
   `by_function` / `total`). Cost lines arrive on two overlapping cuts of
   one cost base; summing them double-counts everything.
3. **`metric_variant`** plus the observation IDs that fed each
   calculation — see 008.
4. **`is_adjusted`** with an adjustment note. Templates computed EBITDA
   margin from adjusted EBITDA while labelling it simply "EBITDA margin".
5. **`screening_criteria`** table. The snapshot scores explicit
   thresholds and reports *n* of *N*; that score should be recomputed
   from reviewed data, not typed.
6. **`assessments`** table for rated qualitative dimensions, on a single
   normalised scale (see `docs/PAPER_SPEC.md` §A13).

**Why this is worth recording.** The four defects that motivated these
additions were found in live working files, not invented as test cases:
a metric label inconsistent with its inputs, an FX reference off by one
row that silently zeroed a derived line, a permanently broken check
formula that read as decoration, and CAGR cells that were half live
formulas and half pasted values. Each one was correct when written. The
schema exists to stop them staying wrong.

---

## 2026-09-09 — 010: Obsidian is a read-only surface. The database is the system of record.

**Decision.** Deal records live in SQLite. Obsidian receives a one-way
generated export and holds the analyst's own hand-written notes. There is
no path by which Obsidian writes back into the database.

**Why not store deal records in Obsidian.** Markdown cannot enforce that
a figure carries its units, basis, period, source page and review status.
The moment a number lives in a note it is a bare number again — the exact
failure this project exists to prevent. Cross-deal comparison and "show
me every unreviewed figure" are queries, and a folder of notes cannot be
queried.

**Why use Obsidian at all.** Qualitative work — call notes, market
reading, threads across deals and people — is genuinely better there, and
it is where the analyst already works.

**The three connection points.**

1. **Generated export, database → vault.** One note per deal, with YAML
   front-matter (deal id, stage, headline metrics, open issue count) and
   links. Headed `GENERATED — DO NOT EDIT`, rewritten on every export.
2. **Hand-written notes are ingestible.** A note in a `notes/` subfolder
   can be registered as a document with `doc_type = analyst_note`, so
   claims made in it carry the same evidence treatment as claims in a
   CIM. The tool reads that folder and never writes to it.
3. **Never two-way sync.** A number corrected in a generated note that
   the database does not know about is a second truth, which breaks
   "nothing is silently overwritten" directly.

**Rejected.** Markdown files as the primary store, with the database as
an index built from them. Appealing because everything stays readable in
a plain text editor, but it puts the source of truth in a format that
cannot express review status or hold two conflicting figures side by
side without ambiguity.

**Confidentiality guard.** Export is blocked for `confidential` deals
unless the vault is on local disk only. This is enforced by inspecting
the path at runtime, not by trusting the `OBSIDIAN_VAULT_SYNC` setting:

- reject any path under `~/Library/Mobile Documents/` (iCloud Drive)
- reject any path under `~/Library/CloudStorage/` (Dropbox, Google
  Drive, OneDrive and similar via the macOS File Provider API)
- **reject any path under `~/Desktop/` or `~/Documents/` when iCloud
  Desktop & Documents sync is enabled** — this machine has it enabled,
  so a vault moved into either folder would sync to Apple silently
- reject a vault containing `.obsidian/sync.json` (Obsidian Sync)
- reject a path containing `.icloud` placeholder files

**Why check rather than trust the setting.** The setting records
intent. A vault dragged into `~/Documents` starts syncing without the
setting changing. The check must look at where the files actually are.

Same shape as the LLM provider rule, and it gets the same test:
a confidential deal plus a synced vault must raise, not warn.

**Scope.** The export itself is not week-one work. The decision is
recorded now because it constrains the deal record; the exporter is
built after the week-one scope is complete.

---

## 2026-09-09 — 011: Issues are computed; resolutions are stored

**Decision.** Reconciliation issues remain computed on demand and are
never persisted (decision 004 stands). The analyst's **resolution** of an
issue *is* persisted, in an `issue_resolutions` table keyed by a
deterministic fingerprint of the issue: deal, check type, metric, period
and the sorted observation ids involved.

A resolution is automatically invalidated if any observation in its
fingerprint changes, so an explanation cannot outlive the figures it
explained.

**Why.** Two figures disagreeing is not always an error. A CIM commonly
restates a headline figure in more than one place, and the versions can
differ for legitimate reasons — continuing operations only, net of
rebates, pre-acquisition. The analyst sense-checks and concludes the
difference is proper.

Without stored resolutions that finding resurfaces every time the deal is
opened, forever. The analyst learns to ignore the issues list, and an
ignored issues list is worse than none: it provides the appearance of a
control while providing none of the substance.

**Why not simply store the issues and mark them closed.** Because then
the stored issue can disagree with the data it describes — the failure
mode decision 004 exists to prevent. Storing only the judgement keeps
findings live and derived, while making the human contribution durable.

**Consequence.** Reconciliation output carries three states rather than
two: open, resolved-with-reason, and *stale resolution* — where an
explanation existed but the underlying figures have since changed and it
must be revisited.

**Built when.** Week-one step 5. Recorded now because it came out of
describing how CIMs actually behave, and it changes what reconciliation
returns.

---

## 2026-10-21 — 012: How core/calculations.py came to be written

**What happened.** CLAUDE.md section 2 reserves `core/calculations.py`
and `core/reconciliation.py` for Adrien to write, with Claude providing
signatures, tests and review only. Partway through step 3 that was
changed, at Adrien's instruction, to Claude writing the implementations
with a line-by-line explanation of each one.

**Why it is recorded.** A decision log that omits the decisions that
went differently from the plan is not a decision log. Anyone reading
this repository — including an interviewer — should be able to see which
parts were written by whom.

**The reason for the change.** Four successive attempts failed on
mechanics rather than on the finance: terminal commands pasted into the
source file, illustrative code fragments pasted as if they were real
code, a docstring terminator deleted, and an indentation error. The
obstacle was Python syntax and editor handling, not the calculations.
Explaining complete, working code in place turned out to be a better way
through than describing fragments to be assembled.

**What was retained.** Adrien wrote the arithmetic of `revenue_growth`
himself — the first three tests to pass. The design decisions stand as
originally specified and were made before any implementation: figures as
value objects rather than bare floats, and the distinction between
raising and returning None.

**What was lost.** The original intent was that this module be
defensible line by line because it had been typed line by line. That
guarantee is weaker now. The compensating measure is this entry, plus
the explanations recorded in the session — the code should still be
defensible, but on the basis of having been understood rather than
having been authored.

**Still outstanding.** `core/reconciliation.py` is unwritten. Whether
the same approach applies there is an open question, and worth deciding
deliberately rather than by drift.
