# Deal Screening Workbench — project instructions for Claude Code

Read this file before every task. It is the contract for how we work
together on this project.

## 1. Who I am and what this is

I am a growth-equity / private-equity investor building my own tool. I am
not a software engineer. I am building this for two reasons:

1. To run my real deal workflow: turn company documents into a
   standardised onboarding paper, a financial scorecard and a comparison
   across live deals, then expand over time into the later diligence
   stages (customer cohort analysis, market and competitor work,
   valuation, IC paper).
2. To be able to explain and defend every part of it in technical
   interviews. Producing code I cannot explain is a failure, even if the
   code works.

Treat me as a capable, motivated learner. Explain things in plain
language. Do not skip steps because they seem obvious to an engineer.

## 2. How we work (non-negotiable)

- **Plan before code.** For every task, first explain in plain language:
  what we are building, why, the simplest design, the trade-off you
  rejected, and which files will change. Wait for my go-ahead before
  writing code.
- **One small change at a time.** Never generate more than one module or
  one feature per step. Show me the diff and explain it line by line
  where it matters.
- **Run it and show me the data.** After every change, show me how to run
  it and how to inspect the intermediate output (the database row, the
  raw API response, the calculated number). I should see inputs and
  outputs, not just "tests pass".
- **I write two modules myself.** `core/calculations.py` and
  `core/reconciliation.py` are mine. You may write the tests and the
  function signatures, and you may review my code and point out bugs, but
  do not write the function bodies. If I ask you to, remind me of this
  rule first.
- **Give me a small task after each step.** Something I can do in 10-20
  minutes: change a schema field, add a check, break a test and fix it,
  query the database by hand.
- **Interview notes.** After each step, append 3-6 lines to
  `docs/INTERVIEW_NOTES.md`: what we built, the design decision, the
  alternative we rejected, and one question an interviewer might ask with
  a short answer. Keep this file honest and in my words where possible.
- **Decision log.** Record every architectural decision in
  `docs/DECISIONS.md` with the date and the reason.
- **Never invent data.** Missing values are missing. Conflicting values
  are stored side by side. Nothing is silently overwritten.

## 3. Week-one scope

See `docs/ROADMAP.md`. Build it in that order, on synthetic data, and
nothing else until it works end to end.

Interface: Streamlit. Do not spend time on styling or on a JavaScript
front end.

## 4. Architecture rules (so it can grow for years)

```
app/            Streamlit pages only. No business logic here.
core/           schema.py, calculations.py, reconciliation.py, review.py
ingestion/      pdf.py, excel.py, chunking.py
llm/            provider.py (abstract), mistral_api.py, local_ollama.py,
                prompts/ (versioned)
retrieval/      simple keyword/section retrieval; embeddings later
                behind the same interface
reports/        scorecard_xlsx.py, onboarding_docx.py
storage/        SQLAlchemy models, migrations (alembic from day one)
tests/          unit tests + fixtures; evaluation harness in tests/eval/
docs/           DECISIONS.md, INTERVIEW_NOTES.md, ROADMAP.md
```

- Every later diligence stage is a module that writes to the same deal
  record: `modules/cohorts` (customer CUBE), `modules/market`,
  `modules/valuation` (LBO / DCF / comps), `modules/ic_paper`. Design the
  deal record and the evidence model now so these can be added without
  changing the core.
- **The LLM provider is an interface.** Nothing outside `llm/` may import
  the Mistral SDK. The provider is chosen by config: `mistral_api` for
  development and demos, `local_ollama` (open-weight Mistral models
  running on my Mac) for confidential deals.
- Prompts are versioned files, and every analysis run records the prompt
  version and model used.
- Secrets live in `.env`, never in code, never committed.

## 5. Data protection rules

- Real deal documents never go into this repository folder, never into a
  prompt to you, and never to a hosted API unless I have explicitly
  enabled it for that deal. They live in `deals_private/` (git-ignored)
  or outside the repo.
- Each deal has a `confidentiality` setting: `synthetic`, `public`,
  `confidential`. `confidential` deals may only use the `local_ollama`
  provider; the code must refuse to send them to a hosted API. Write a
  test for this.
- Development and all demonstrations use the synthetic companies only.

## 6. Roadmap after week one

See `docs/ROADMAP.md`. Do not start until I say so.
