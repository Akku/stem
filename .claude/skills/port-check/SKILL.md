---
name: port-check
description: Adapt STEM to an environment that differs from the reference (other OS, agent or model), measure whether it works, and report back. Use when session start prints "PORT CHECK AVAILABLE" and the user agrees, or when the user asks to run STEM on another OS, agent or model.
---

# Port check

Reference environment: see `reference-*` in `STEM_VERSION`. Checklist, failure categories and report format: `docs/agent/PORT_CHECK.md` (read it first). STEM files stay untouched: adaptations go into the overlay `docs/agent/port/` and the log `docs/agent/PORT.md`, so `stem-update` does not overwrite them.

1. **Offer once.** One question to the user: run the port check now (a/b)? On no, create `docs/agent/PORT.md` with `status: declined` and the environment (stops the offer), then continue the normal task.
2. **Analyse** (read only): confirm OS, agent and model with the user (the script knows only OS and agent; compare your own model with `reference-model`). Run the stage 1 prerequisite probe (`PORT_CHECK.md`): bash, python3, git, backlog CLI, hooks support.
3. **Missing prerequisite → abort.** Write `PORT.md` (`status: aborted`), name the hurdle and what the user could do (for example Git Bash or WSL2 on Windows), then go to step 7. Substitutes (stage 2) only if the user then chooses that.
4. **Plan.** Show one plan: which scripts or instructions need an adaptation, which overlay file each goes to, what you expect to fail. **One approval for the whole plan**, then no further questions on it.
5. **Apply** as overlay: adapted copies in `docs/agent/port/`, deviations and environment in `PORT.md`. Do not edit STEM files.
6. **Measure.** Run the stage 1 checklist, record per item pass / partial / fail with failure category, the user action a failure would need (and whether the user did it) and the number of user interactions per flow. Stage 2 (optional, only if all pass): `scripts/retro-metrics.sh --snapshot`, compared with other baselines as order of magnitude only (agent and model are confounders).
7. **Report.** Build the report from `PORT.md` (numbers, IDs and categories only; format in `PORT_CHECK.md`), show it to the user in full, send only on an explicit yes. Adaptations that pass the checklist may go to STEM with `promote-learning`; the user decides.

If a step did not fit: `Learning: skill port-check: <what> -> <change>` in the task notes (`R-LEARNING`).
