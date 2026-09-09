# Deal Screening Workbench

A tool for turning company documents into a standardised onboarding paper,
a financial scorecard, and a comparison across live deals.

## What it is

The database is **not a spreadsheet of company financials**. It is a
**ledger of observations**.

A spreadsheet says: *Revenue for FY23 is £12.4m.*

This system says: *An LLM reading page 14 of the CIM saw a line labelled
"Turnover" with the value 12.4, in a table headed "£m", covering the year
ended 31 December 2023, presented as an actual. It has not yet been
reviewed by a human.*

Two rules follow, and they drive nearly every design choice:

1. **Rows are never overwritten.** A correction creates a new record and
   marks the old one superseded. The original extraction stays, because
   it is the evidence of what the document said.
2. **Disagreement is stored, not resolved.** Two documents claiming
   different FY23 revenue produce two live rows. The system's job is to
   surface the conflict, not to pick a winner.

## Setup

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your keys
```

## Confidentiality

Every deal carries a `confidentiality` setting: `synthetic`, `public`, or
`confidential`.

- Real deal documents live in `deals_private/` (git-ignored) or outside
  the repository entirely. They are never committed.
- Deals marked `confidential` may only use the `local_ollama` provider.
  The code refuses to send them to a hosted API, and there is a test that
  proves it.
- All development and all demonstrations use the synthetic companies in
  `tests/fixtures/`.

## Layout

| Directory    | Contains                                                     |
|--------------|--------------------------------------------------------------|
| `app/`       | Streamlit pages only. No business logic.                     |
| `core/`      | Schema helpers, calculations, reconciliation, review logic.  |
| `ingestion/` | Reading PDFs and Excel workbooks.                            |
| `llm/`       | Provider interface + implementations. Nothing outside this   |
|              | directory may import an LLM SDK.                             |
| `retrieval/` | Finding relevant passages. Keyword first, embeddings later.  |
| `reports/`   | Scorecard (xlsx) and onboarding paper (docx) generation.     |
| `storage/`   | SQLAlchemy models and Alembic migrations.                    |
| `tests/`     | Unit tests, synthetic fixtures, evaluation harness.          |
| `docs/`      | Decision log, interview notes, roadmap.                      |

## Documentation

- `docs/DECISIONS.md` — every architectural decision, dated, with reasons.
- `docs/INTERVIEW_NOTES.md` — what was built, what was rejected, and why.
- `docs/ROADMAP.md` — what comes after week one.
