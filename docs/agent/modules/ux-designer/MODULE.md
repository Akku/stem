---
name: ux-designer
purpose: UX/UI designer agent for mockups, UI reviews and implementable design specs
when_useful: Projects with a user interface, especially the concept phase (R-CONCEPT) and UI reviews
version: 1
files:
  - .claude/agents/ux-designer.md
---

# ux-designer module

A subagent (`.claude/agents/ux-designer.md`) that creates desktop and mobile mockups, reviews screens and flows, and delivers implementable specs (states, spacing, tokens, accessibility). `R-CONCEPT` delegates the mockup rounds to it.

Not useful for projects without a UI (CLI tools, libraries, backends).

Switch on/off: `python3 scripts/module.py enable ux-designer` / `disable ux-designer` (moves the file between `.claude/agents/` and `docs/agent/modules/ux-designer/files/`; nothing is deleted).
