# Tron mode: user guide (preview)

[🇩🇪 Deutsch](TRON-GUIDE.de.md) · [README](../README.md#optional-tron-mode-one-milestone-built-unattended)

Tron lets agent sessions build one approved milestone while you are away, for example overnight. It builds the clearly specified part and returns one report with everything that needs you. It never pushes, tags or merges: you decide what goes into `main`.

**Preview.** Measured so far: a 6-task fixture costs 0.21-0.30 USD per accepted task. Three real runs on other projects: the first two cost 2.98-3.60 USD per accepted task with 42-67 % of tasks blocked (mostly an environment the sandbox lacked); the third, after the fixes for those runs, ended complete (3 of 3 tasks accepted, 0 blocked, 1.16 USD per accepted task, no defects found by the user afterwards). The independent evaluator is about half of the cost. Expect to prepare the milestone carefully.

## Is it for you?

- Yes, when a milestone has tasks with clear, testable acceptance criteria and you can run it in a sandbox.
- No, for small projects, vague goals, or tasks that need your judgement, real data or paid services during the run. Tron is off by default; say "turn on Tron" to the agent to enable the `tron` module.

## 1. Prepare (with the agent, about 15-30 minutes)

Say "run milestone m-N with Tron". The `tron` skill then:
1. Sends **one setup message** with defaults: task order, decision frame (what the agents may decide alone and what must come back to you), project invariants, acceptance scenario (what you would click or run to judge the result, on one platform), limits, models. Answer compactly, e.g. `ok` or `2b, 7: sonnet`.
2. Runs a **question sweep**: a planner reads the whole milestone and pre-decides small questions as assumptions. You veto by number (`veto A2`) and answer the few real questions. Criteria that need you are moved into separate tasks, so the run does not stall on them.
3. Checks the **environment**: every service, tool or file the tasks need is checked inside the sandbox before the run, not discovered mid-run.
4. Runs `python3 scripts/tron.py check --milestone m-N` until it prints `READY`.

## 2. Start

The agent shows one question with the start command, the **budget** (`max_cost`, `max_hours`, `max_tasks`) and the expected cost. Your yes approves the budget and starts the run; there is no second confirmation.

- **Sandbox:** run it inside the STEM Docker sandbox (`scripts/sandbox.sh`, see the README) with `--permission-mode bypassPermissions`, so no permission prompt can stop the run and the agents cannot touch your computer. Never a narrow tool allowlist.
- **Budget:** the run stops at the first limit it reaches; each evaluator session is capped too. A run costs real money.
- **Keep awake:** for runs over an hour the agent asks whether the Mac should stay awake (`scripts/sandbox.sh start <name> --keep-awake`).

## 3. Watch (optional)

The agent starts the run in the background and watches it itself: after 1-2 minutes it reads the head of the log to see that the run really works, then checks the status about every 2 hours. You do not need to keep a terminal open. To stop early, create `docs/agent/tron/STOP` (the run ends after the current session and can be resumed).

## 4. Read the report

When the run ends, the agent reads `docs/agent/tron/REPORT-<run>.md` and tells you: tasks done and blocked, evaluator findings, cost, and the branch `tron/<milestone>`. It then asks the report's **questions for you** in one numbered message (blocked tasks, assumptions without a basis, risks, and whether you found defects). Answer compactly (`1a, 3b`). Then:
- try the result yourself (the acceptance scenario),
- merge the branch when you are satisfied,
- start the run again for blocked tasks you have answered: it resumes where it stopped.

Defects you find later go back as evidence (`tron.py defect`), so the evaluator learns from what it missed (only with your yes).

## Where the details live

Rules for the agents: `docs/agent/TRON.md` (`R-TRON`). The agent's step-by-step procedure: the `tron` skill. Changes per version: [CHANGELOG](../CHANGELOG.md).
