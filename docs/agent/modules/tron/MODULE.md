---
name: tron
purpose: Tron mode: build one approved milestone unattended with runner, gate and independent evaluator
when_useful: Projects with a prepared milestone, clear acceptance criteria and budget for unattended agent sessions; not for small projects
version: 1
refs:
  - file: docs/agent/ADVANCED.md
    after: "| `R-ROUTING` |"
    line: "| `R-TRON` | Tron mode (optional module): rule is in `docs/agent/TRON.md`, not here |"
files:
  - scripts/tron.py
  - .claude/agents/evaluator.md
  - .claude/agents/planner.md
  - .claude/agents/doctor.md
  - .claude/agents/retro-analyst.md
  - .claude/skills/tron/SKILL.md
  - docs/agent/DECISION_FRAME.md
  - docs/agent/INVARIANTS.md
  - docs/agent/PRECEDENTS.md
  - docs/agent/TRON.md
---

# tron module

`scripts/tron.py` (`run`, `check`, `report`, ...) hands one approved milestone to unattended agent sessions, gates each task, lets the `evaluator` judge, and writes a report; the `tron` skill guides preparation and reading the report. Rule `R-TRON` (session duties, retro tiers, calibration) lives in `docs/agent/TRON.md`. Templates: `DECISION_FRAME.md`, `INVARIANTS.md`, `PRECEDENTS.md`.

A run costs real money; run it in the sandbox. Not useful for small projects. Run output (`docs/agent/tron/`) and the `tron` block of `docs/agent/stem-config.json` stay in place when the module is off.

Switch on/off: `python3 scripts/module.py enable tron` / `disable tron` (moves the files between their places and `docs/agent/modules/tron/files/`; nothing is deleted). When enabling, fill `DECISION_FRAME.md` and `INVARIANTS.md` with the user (the `tron` skill, step 1).
