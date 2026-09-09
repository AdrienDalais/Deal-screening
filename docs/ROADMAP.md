# Roadmap

## Week one — the working version

Build in this order. Nothing else until it works end to end on synthetic
data.

1. **Schema and storage.** SQLite via SQLAlchemy, Alembic initialised.
2. **Synthetic test set.** Three fictional companies, each with a
   CIM-style PDF and a financials workbook, with deliberate planted
   defects. These are also the evaluation set.
3. **Calculations.** Growth, recurring share, gross margin, EBITDA
   margin, Rule of 40 with explicitly named variants. Pure functions,
   no database access, hand-checked expected values.
   *(Written by Adrien.)*
4. **Extraction.** Mistral with structured output against a Pydantic
   schema. Text PDFs first; fixed-layout Excel read directly with
   openpyxl, cell references preserved.
5. **Reconciliation.** Components vs totals, gross profit vs revenue less
   COGS, EBITDA vs gross profit less opex, unit and currency consistency,
   forecasts mixed with actuals, overlapping expense breakdowns, metric
   labels inconsistent with their inputs.
   *(Written by Adrien.)*
6. **Review screen.** Figures beside their source reference; accept,
   correct with a reason, or reject.
7. **Scorecard export** to Excel from reviewed data.
8. **Onboarding paper draft.** Section by section, from reviewed figures
   plus retrieved passages. Every material statement tagged
   reported / recalculated / analyst judgement.
9. **Comparison table** across deals. Actuals and forecasts separated,
   currencies shown, unreviewed figures flagged. No automatic score.
10. **Screening decision** with rationale and an editable
    information-request list.

## After week one — do not start until confirmed

- Evaluation harness with held-out examples and a written results summary.
- Customer cohort module (retention, NRR, cohort curves) that
  cross-checks the retention claims in the onboarding paper.
- Management forecast extraction shown beside actuals; later, an analyst
  scenario model with explicit assumptions.
- Market and competitor module with manually supplied sources.
- Valuation module (LBO / DCF / comps) reading the same reviewed figures.
- Authentication and backup, before anything confidential touches it.
- Embedding-based retrieval — only if keyword retrieval is shown to miss
  evidence.
