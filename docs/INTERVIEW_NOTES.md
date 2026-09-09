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
