---
name: market-analysis
purpose: Lean market check before building: alternatives, comparison, build/adapt/use recommendation
when_useful: Medium and large projects at setup or before a new product-level feature
version: 1
files:
  - .claude/skills/market-analysis/SKILL.md
---

# market-analysis module

A skill (`.claude/skills/market-analysis/SKILL.md`) that searches the web for existing alternatives, compares them and recommends build, adapt or use, so the project does not rebuild what exists. Costs a few searches.

Not useful for small projects or work without a product-level decision.

Switch on/off: `python3 scripts/module.py enable market-analysis` / `disable market-analysis` (moves the file between `.claude/skills/market-analysis/` and `docs/agent/modules/market-analysis/files/`; nothing is deleted).
