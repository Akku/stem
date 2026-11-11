# Port check: checklist and report format

Read only when the `port-check` skill runs. STEM is built for one reference environment (`reference-*` in `STEM_VERSION`: macOS, Claude Code, Sonnet 5.5 medium). Everything below measures how far another environment gets without help.

## Overlay
- `docs/agent/port/`: adapted copies of scripts (same file names) and short instruction notes. When present they take precedence over `scripts/`; the agent reads `PORT.md` first (session start prints a line).
- `docs/agent/PORT.md`: front matter `status: ported | aborted | declined`, date, STEM version, environment (OS and version, agent, model, effort), then deviations (file, change, reason) and the checklist results. This file is the only data basis of the report.

## Prerequisite probe (stage 1, before the plan)
bash, python3, git, backlog CLI (`backlog --version`), hook support of the agent. Anything missing: abort path (skill step 3). Report the hurdle and the action the user could take.

## Stage 1 checklist
Grade each item `pass | partial | fail`; on partial/fail give one failure category and the user action it would need.

| ID | Item |
| --- | --- |
| C1 | Session start and hooks (`scripts/session-start.sh` output complete; hooks fire or are explicitly not supported; wiring and per-agent state: `docs/agent/HOOKS.md`, changed through `scripts/hooks/manifest.json`) |
| C2 | `scripts/run.sh <label> <command>` (log written, exit code kept) |
| C3 | Backlog cycle (create, plan, note, done a throwaway task; `scripts/check-backlog.sh`) |
| C4 | Verify script of the project (or `scripts/check-backlog.sh` if none) |
| C5 | Handoff skill (writes or skips HANDOFF.md correctly) |
| C6 | Skill call (the agent finds and runs a skill from `.claude/skills/`) |
| C7 | `scripts/retro-metrics.sh` runs |
| C8 | `scripts/context-report.py` runs, or `not evaluable` with the reason (transcript format of the agent) |

Failure categories: `missing-tool`, `shell-syntax`, `path-or-os-api`, `hooks-unsupported`, `transcript-format`, `agent-ignores-instruction`, `model-capability`, `other`.

Per flow also count user interactions (messages the user had to send beyond the task start; numbers only, no content).

## Stage 2 (optional, all stage 1 items pass)
`scripts/retro-metrics.sh --snapshot` as cost baseline of the new environment. Compare with other baselines as order of magnitude only.

## Report (field-report variant "port")
GitHub issue with the field-report template, variant `port`. Allowed content: STEM version, environment (OS family and version, agent name and version, model, effort), prerequisite result, checklist grades C1-C8 with failure categories, user-action category per failure plus done yes/no, interaction counts, number of overlay files, stage 2 numbers if taken. No free text, paths, project names or code. The user sees the complete text first and sends it only on a clear yes (`gh issue create`, or the text for manual posting).
