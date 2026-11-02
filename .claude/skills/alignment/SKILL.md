---
name: alignment
description: Short, interruptible interview that builds a shared understanding before planning - one question at a time, each with a recommended answer, walking the open decisions in dependency order. Use for unclear or new features, before a large task, when output surprised the user, or optionally during setup.
---

# Design alignment ("grill", small and stoppable)

Rules: `R-CONCEPT` (product/UI direction), `R-DESIGN`, `R-AUTONOMY` (do not invent product decisions).

1. **Scope the budget first, tell the user:** small change 2-4 questions; feature 5-12; new product 10-20 in rounds with a pause in between. Say "stop any time; for the rest I decide and write down my assumptions".
2. **Explore before asking:** whatever the repository, vision doc, glossary (`docs/GLOSSARY.md` if it exists) or `docs/ARCHITECTURE.md` already answers, do not ask.
3. **One question at a time**, in dependency order (a decision others depend on comes first). Each question: why it matters in one sentence, 2-3 options, your recommendation. Questions the user can hardly judge: decide yourself and record the assumption.
4. **Stop** when no open decision could change the plan materially, when the budget is used, or when the user says stop. Then list the assumptions you made.
5. **Write the result down** where it lives (one place): vision doc or PRD (`backlog doc`), or acceptance criteria in the tasks, with date; new domain terms into `docs/GLOSSARY.md` if the project has one. Only then plan and create tasks.
6. Offer a batch if the resulting tasks are related (`R-BATCHING`).

If a step did not fit or you deviated from it: `Learning: skill alignment: <what> -> <change>` in the task notes (`R-LEARNING`).
