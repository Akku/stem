---
name: tron
purpose: Tron mode: build one approved milestone unattended with runner, gate and independent evaluator
when_useful: Projects with a prepared milestone, clear acceptance criteria and budget for unattended agent sessions; not for small projects
version: 1
refs:
  - file: docs/agent/ADVANCED.md
    after: "| `R-ROUTING` |"
    line: "| `R-TRON` | Tron mode (optional module): rule is in `docs/agent/TRON.md`, not here |"
  - file: docs/agent/OPERATING_MODEL.md
    after: "`BLOCKED` is a valid outcome. Autonomy does not authorize"
    line: "**In a Tron run** (`R-TRON`) the decision frame (`docs/agent/DECISION_FRAME.md`) comes before stop-and-ask: a reversible choice inside the task's ACs is decided and recorded (`Assumption: ... (basis: ...)`), not asked; a missing basis is allowed and the report lists it for the user. The frame's 'Must come back' items and invariants still stop the task (draft question, Blocked)."
  - file: docs/agent/OPERATING_MODEL.md
    after: "Do not infer plan approval merely"
    line: "In a Tron run (`R-TRON`) the approved milestone plus the answered sweep (`SWEEP-<milestone>.md`) count as plan approval for every task of the run, size-L included; a new public contract or an ownership or permission change still needs a ruling (frame 'Must come back')."
  - file: docs/agent/OPERATING_MODEL.md
    after: "- **Owned interfaces:**"
    line: "  - In a Tron run (`R-TRON`) an additive, internal (no contract others call), backward-compatible interface is decided by the agent and recorded with a `Decision: ...` line in the task notes; the report lists every such line for the user's review. A breaking or public contract, ownership, permissions or a migration comes back (draft question, Blocked)."
  - file: docs/agent/OPERATING_MODEL.md
    after: "For coherent low/medium-risk batches"
    line: "**In a Tron run** (`R-TRON`) the runner's evaluator counts as this independent review only when its brief covers the trigger and the full diff; the report names every evaluation whose brief was cut or shortened, and such a task with a review trigger is reviewed by the user after the run. A worker never asks for a review waiver during the run."
  - file: docs/agent/OPERATING_MODEL.md
    after: "**Decision records.**"
    line: "In a Tron run (`R-TRON`) decisions stay notes only (`Assumption:` or `Decision:` lines); an ADR or a precedent (`PRECEDENTS.md`) is written only after the user reviewed the run."
  - file: AGENTS.md
    after: "6. **Stop conditions** (`R-AUTONOMY`)"
    line: "   In a Tron run the decision frame comes first (`R-AUTONOMY`)."
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
