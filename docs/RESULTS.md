# Results from using STEM on itself

Three curves from the author's own work. They are **dogfooding data, not a benchmark**: 291 Claude Code sessions in 14 projects, one user, 2026-10-03 to 2026-11-07, no control group without STEM. Numbers only; no project names or session content. A controlled comparison (STEM vs. a plain agent) is planned as experiment G2 in [EXPERIMENTS.md](agent/EXPERIMENTS.md).

## 1. Traceability: commits that carry a task ID

![Share of commits with a task ID per week](assets/results-traceability.png)

Between 56 % and 91 % of all commits reference a backlog task, in every week; the latest week is the highest (91 %), after a dip to 56 % in mid-October. A commit with a task ID can be traced to a goal, a plan and evidence lines. Time windows tie commits to sessions, so the figures are approximate.

## 2. The rulebook grows, the always-loaded part does not

![AGENTS.md vs OPERATING_MODEL.md size per release](assets/results-always-loaded.png)

From v0.1.0 to v1.14.0 the rules file doubled (25 kB to 50 kB), while `AGENTS.md`, the only file loaded in every session, grew from 2.8 kB to 5.5 kB (roughly 1.5k tokens) and has stayed there since late October. Rules are loaded by ID when their trigger applies. Sizes are taken from the release tags.

## 3. Sessions stay manageable

![Median peak context per week](assets/results-session-size.png)

The median peak context of a session fell from several hundred thousand tokens in the first weeks to 129k to 140k since 2026-10-19 (the earlier weeks rest on 2 to 5 sessions each). The handoff rule (start a new session by about 100k) and the context notice are the intended cause, but this data cannot prove it; session habits changed too.

## What these curves do not show

- Not a with/without comparison, and not generalised beyond one user.
- Not fewer model calls per task: that figure stayed flat in the same period.
- The start context of a session (about 58k at the start, about 71k now) is mostly Claude Code itself, global settings and tools, not STEM.
