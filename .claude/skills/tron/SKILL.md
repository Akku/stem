---
name: tron
description: Guide the interactive parts of a Tron mode run (unattended build of one approved milestone) - prepare the milestone with the user, run the readiness check, start the run in the background, read the finished report. Use when the user wants to run a milestone unattended, asks for Tron mode, or a Tron report is ready to read.
---

# Tron mode: before and after a run

Rules: `R-TRON` in `docs/agent/TRON.md` (session duties, role tiers), `R-BATCHING` (approval of a batch), `R-DESIGN` (alignment). Do not repeat them here. The runner is `scripts/tron.py`; this skill starts a run only after the user's go (section 3).

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
- Starting the run must not trigger a permission prompt: if `.claude/settings.local.json` (or `.claude/settings.json`) lacks `Bash(scripts/tron.py:*)` and `Bash(python3 scripts/tron.py:*)` under `permissions.allow`, add them to `.claude/settings.local.json` with the user's yes.
- Edit `docs/agent/stem-config.json` only with the user's yes; commit it so the tree is clean.

## 3. Check and start
- Run `python3 scripts/tron.py check --milestone <id>` and fix what it lists (it exits 1 with a list; warnings do not block).
- When it prints `READY`, show the exact `start:` line and the budget (a run costs money), ideally run `--dry-run` first; ask once for the go.
- After the go, start the run yourself with `--detach` (the `start:` line) as a background command that notifies you when it exits (Claude Code: Bash with `run_in_background`); `--detach` makes the run its own process, so it goes on when this session ends. Never ask the user to start it, open a terminal or type a command. Say once where the report will appear and that you read it yourself when the run ends.
- While the run holds `docs/agent/tron/LOCK`, commit nothing on `tron/<milestone>` (the pre-commit hook refuses it); repairs wait until the run has stopped (`docs/agent/tron/STOP` stops it after the current session). A resume moves the interrupted task's base past such repair commits.
- During the run ask nothing and wait for no input: no questions, no "tell me when it is done". When the process exits, read `docs/agent/tron/REPORT-<run>.md` yourself and continue with section 4.

## 4. After the run
- Read `docs/agent/tron/REPORT-<run>.md` with the user: Done, Blocked (with the draft questions), evaluator findings, cost, branch `tron/<milestone>`. Assumptions come grouped by basis, `none` first; when the user corrects one, add a line to `docs/agent/PRECEDENTS.md` (`P-<n> | date | kind | ruling | source report <run>`; keep it at 60 lines or fewer) and commit it.
- The user decides on merging; the run never pushed, tagged or merged. Answer Blocked questions, then offer to run again (it resumes).
- Defects the user finds go into the tasks as evidence; do not fix them silently.
- Ask once: "Did you find defects?" Record each one: `python3 scripts/tron.py defect --run <run> --task TASK-n --text "<what is wrong>"`; it notes whether the evaluator had passed the task (a miss); when there is none (left), run `defect --run <run> --none` so the metric `evaluator_misses` is known. For misses run `python3 scripts/tron.py calibrate --run <run>` (one analyst session; cost shown in the report), show each drafted example from `docs/agent/tron/CALIBRATION-<run>.md` one per message and ask: apply to `.claude/agents/evaluator.md`? Then `calibrate --accept D<n>` or `--reject D<n>`; commit the evaluator file (the CALIBRATION file is runner output like the journal). Never apply without the user's yes (tier 3, `R-TRON`).
