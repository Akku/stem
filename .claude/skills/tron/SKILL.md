---
name: tron
description: Guide the interactive parts of a Tron mode run (unattended build of one approved milestone) - prepare the milestone with the user, run the readiness check, show the start command, read the finished report together. Use when the user wants to run a milestone unattended, asks for Tron mode, or a Tron report is ready to read.
---

# Tron mode: before and after a run

Rules: `R-TRON` (session duties, role tiers), `R-BATCHING` (approval of a batch), `R-DESIGN` (alignment). Do not repeat them here. The runner is `scripts/tron.py`; this skill never starts a run by itself.

## 1. Prepare the milestone with the user (one question at a time, recommendation each)
1. Milestone and tasks: every task has acceptance criteria and a `size-*` label; list the ready tasks in order.
2. Decision frame (`docs/agent/DECISION_FRAME.md`): show it, adjust for this milestone.
3. Invariants (`docs/agent/INVARIANTS.md`): add project-specific lines.
4. Acceptance scenario: a short file `docs/agent/tron/ACCEPTANCE-<milestone>.md` (or `tron.acceptance_scenario`): what the user would click or run to judge the result.
5. Budget and limits: `max_cost`, `max_hours`, `max_tasks`; evaluator mode (`off|milestone|task`); `pause_after`.
6. Start-and-smoke command: `smoke_cmd` or `preview_cmd`/`preview_url` for the product.

7. Question sweep: run `python3 scripts/tron.py sweep --milestone <id>` (a fresh planner session; cost shown), read `docs/agent/tron/SWEEP-<id>.md`, ask its questions one per message with the planner's recommendation, and record each answer in the file (tick `[x]`, add `Answer: ...`). Answers that change a task or an AC go through the `backlog` CLI now, before the run, so the AC freeze covers them; use the draft acceptance scenario as the base of step 4. Commit the file. The check fails while the sweep is missing or has open questions (`tron.sweep: false` opts out).

## 2. Commands and models
- Show the configured commands of every role (`worker_cmd`, `evaluator_cmd`, ...; a missing one falls back to `worker_cmd`) and `verify_cmd`. The user confirms them.
- Propose a model per role from the `R-TRON` tier table; model names live in the config. Warn if `CLAUDE_CODE_EFFORT_LEVEL` is set (it beats `--effort`).
- Edit `docs/agent/stem-config.json` only with the user's yes; commit it so the tree is clean.

## 3. Check and start
- Run `python3 scripts/tron.py check --milestone <id>` and fix what it lists (it exits 1 with a list; warnings do not block).
- When it prints `READY`, show the exact `start:` line, ideally `--dry-run` first. The user starts it in a sandbox or with an allowlist; a run costs money, so name the budget again.

## 4. After the run
- Read `docs/agent/tron/REPORT-<run>.md` with the user: Done, Blocked (with the draft questions), evaluator findings, cost, branch `tron/<milestone>`.
- The user decides on merging; the run never pushed, tagged or merged. Answer Blocked questions, then offer to run again (it resumes).
- Defects the user finds go into the tasks as evidence; do not fix them silently.
