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
