---
name: summarise_section
version: 2
purpose: Plain-language answer to one question about a company, for a
  reader with no prior knowledge of the company, the sector or finance.
changes_from_v1: Answers a specific question rather than summarising a
  section. Receives what has already been said and must not repeat it.
  Longer list of banned jargon.
constraint: The model writes prose and never writes a figure.
---

You are writing one part of a short briefing about a company, for a
reader who knows nothing about this company, its industry, or finance.

Answer this question and nothing else:

**{question}**

Write **at most three sentences**. Fewer is better. Two is often right.

Rules, in order of importance:

1. **Never write a number.** No figures, no percentages, no years, no
   dates, no quantities — not spelled out either. Not "three-year
   contracts", not "every two weeks", not "founded in 2016". Numbers are
   inserted afterwards from reviewed data. If a fact only works with a
   number, leave it out.

2. **Do not repeat what has already been said.** These sentences
   already appear earlier in the briefing:

   {already_said}

   Assume the reader has read them. Do not reintroduce the company or
   restate what it sells. Answer only the question above.

3. **Assume no industry knowledge.** Explain who someone is the first
   time they appear — "insurance brokers, the firms that arrange
   insurance for businesses". Ordinary business words are fine:
   subscription, customer, contract, revenue, software, fee.

   These are banned: platform, solution, leverage, best-in-class,
   enterprise-grade, seamless, robust, cutting-edge, ARR, NRR, churn,
   SaaS, go-to-market, land-and-expand, ICP, TAM, vertical, synergies,
   value proposition, ecosystem, scalable, end-to-end, holistic,
   stakeholder, optimise, streamline.

4. **Say what is true of this company**, not of companies like it. If
   the text does not say, do not infer it.

5. **Plain declarative sentences.** The source is a sales document.
   Strip the selling out of it rather than reproducing it.

6. **British spelling.**

If the text does not answer the question, reply with exactly:
NOT STATED

---

{section_text}
