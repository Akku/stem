# Tron mode rule (module `tron`)

Load rule `R-TRON` with the ID mechanism of `OPERATING_MODEL.md`, on this file. Present only while the module is on (`docs/agent/modules/INDEX.md`).


<!-- RULE:R-TRON:START -->
## Tron mode: duties of a session the runner started

Applies when session start prints the Tron mode line (`STEM_TRON=1`). An unattended run hands one approved milestone to `scripts/tron.py`; nobody answers questions during the run.

**Session duties**
- Work on exactly one task, the one named in the prompt, on the run branch the runner prepared. No push, tag, release or merge; no other branch.
- Search the code before writing new code; reuse what exists.
- Finding outside the task: write a draft task, do not fix it silently.
- A stub, placeholder or TODO never counts as Done.
- Propose Done with evidence lines; the runner's gate confirms it. Measured means measured: a figure extrapolated or estimated is grade E1, never E2.
- Task notes: append (`--append-notes`), never overwrite; a line that was there before your session must still be there afterwards.
- Never edit acceptance criteria, the gate and runner files, `docs/agent/stem-config.json`, `DECISION_FRAME.md` or `INVARIANTS.md`.

**Ambiguity** (`DECISION_FRAME.md` lists what may be decided alone)
- Small, reversible, inside the frame: search `DECISION_FRAME.md` and `PRECEDENTS.md` first, then decide and record `Assumption: <text> (basis: <frame line, precedent ID such as P-3, or none>)` in the task notes. A line without a basis is a warning in the journal; `none` is listed first in the report for the user to rule on.
- Outside the frame or touching an invariant (`INVARIANTS.md`): record the question as a draft task, set the task Blocked, stop; the runner continues with an independent task; milestone tasks that depend on the Blocked one (directly or indirectly) never become ready in this run: the journal lists them (`stranded`), the stop reason and the report name them with the task they wait for.
- Red baseline: before the next task the runner starts one baseline repair session (`tron.baseline_prompt` or the default text, always followed by the duties: at least 3 green verification runs, one `baseline:` commit, clean tree, and the answered questions of `SWEEP-<milestone>.md`); still red after its gate stops the run.
- Stalled task (same failure twice, no diff, or the second to last repair failed): with `tron.doctor_cmd` set, the runner calls the Doctor once (read-only, `.claude/agents/doctor.md`) for exactly one verdict: retry with hint (one more repair), split task (subtasks with the parent's AC texts verbatim, parent closes when all pass), environment problem (one baseline repair), needs the user (draft question, Blocked). Every step is in the journal and the report. Split instead of Blocked (TASK-373): when only some ACs need the user (interface or ownership decision, real data, judgement) and the rest can be built without the answer, the agent decides the split itself: the Doctor's `needs_user` names them in `split_out`, the runner moves them verbatim into a new task outside the milestone (labels `waiting`, `tron-user`; question, diagnosis and recommendation in its description), the task goes on in the same run, and the report lists it under 'Split out for you' as info, not as a question. Before the run, `python3 scripts/tron.py split-out --milestone <id>` does the same for the sweep's `## Needs the user` lines. It still blocks when the remaining ACs depend on the answer, when every AC needs the user, or when the decision touches an invariant or a 'Must come back' frame line for the remaining work. Skipped by the sweep: a task named in a `Skip: TASK-n, ...` line or a decision line `the run skips TASK-n, ...` of `SWEEP-<milestone>.md` is set Blocked by the runner itself, without a session; it costs nothing, does not count towards `max_tasks` and shows in the REPORT as 'skipped by sweep'.

**Unattended retro (analysis):** with `tron.retro` set to `on` (and `tron.retro_cmd`), the runner starts the retro analyst (read-only, `.claude/agents/retro-analyst.md`) once at every run end, stopped and incomplete runs included (a resumed run keeps the earlier one as `RETRO-<run>-stop<n>.md`); applying its changes (`tron.retro_apply`) stays limited to complete runs; `python3 scripts/tron.py retro --run <id>` does it by hand. Output `docs/agent/tron/RETRO-<run>.md`: every failure in exactly one layer (task_quality, rule, environment, model, evaluator_miss) with evidence, at most three proposals (target, tier, metric, effect), a check of the previous retro; the runner rejects a file that breaks this. The report links it; the guided retro stays in the `retro` skill.

**Retro changes in tiers** (the only definition; `tron.retro_apply` set to `on`, or `python3 scripts/tron.py retro --run <id> --apply`):
- Tier 1: lines added to `docs/agent/PITFALLS.md` (at most 30 project entries) and new regression test files (named like `test_x.py`, `x_test.go`, `x.test.ts`; `tron.test_globs` adds patterns). An applier session (`tron.applier_cmd`, else `worker_cmd`) applies each proposal on the run branch in commits with the prefix `retro:`; tier 1 paths only gain lines (also inside a tier 2 change), existing test files stay unchanged, and the verification command must pass, otherwise the runner reverts it with a `retro: revert` commit.
- Tier 2: other project rule or skill text (`AGENTS.md`, `CLAUDE.md`, Markdown under `docs/agent/` outside `docs/agent/tron/`, skill Markdown). Applied the same way, then the runner records it in `docs/agent/EXPERIMENTS.md` with metric and baseline value (taken before any change; the retro's own sessions do not count as run cost). The next run's retro compares the metric (lower is better); a worse value reverts the change commits and the row records it. The check needs the change on that run's branch (merge the run branch first).
- Tier 3: the protected paths: gate and runner (`scripts/tron.py`, `scripts/run.sh`, files of the verification command), `docs/agent/stem-config.json` with its limits, `DECISION_FRAME.md`, `INVARIANTS.md`, `EXPERIMENTS.md`, the agent files of evaluator, Doctor, planner and retro analyst, security and deny rules (`.claude/settings*.json`, `scripts/deny-guard.py`, `scripts/hooks/`, `scripts/githooks/`). Only proposed in the report; an applier session whose diff touches one fails the gate and is reverted.
- Any other path, a missing `retro:` prefix or a dirty tree fails the gate too; a STOP file or a limit stops applying, and a later `--apply` continues.

**Milestone evaluator brief:** the diff since the run start is grouped by task (each accepted task's commits, then commits of no task such as baseline or milestone repairs), with a size budget per part (`tron.brief_diff_chars`, default 60000, split evenly, at least 4000 per part); every cut part names the exact `git diff` or `git show` command that shows it in full.

**Evaluator calibration:** defects the user finds after a run are recorded with `python3 scripts/tron.py defect --run <id> --task TASK-n --text "..."` (the `tron` skill asks for them; `--none` records that there is none, until then `evaluator_misses` is unknown); each record notes whether the evaluator had passed the task (its last verdict, else the milestone verdict; a failed milestone verdict counts only for tasks its findings name). For each miss, `python3 scripts/tron.py calibrate --run <id>` starts the retro analyst once in calibration mode, which drafts an example verdict into `docs/agent/tron/CALIBRATION-<run>.md` (one paragraph and one fail verdict, stored re-serialized; anything else rejects the draft); `tron.py retro` does the same for misses without an example and lists the defects in its brief; each is a tier 3 proposal for `.claude/agents/evaluator.md` and is appended there only with `--accept D<n>` on the user's yes (never inside an unattended session). The report lists the defects and the metric `evaluator_misses` per run.

**Roles by tier** (tendencies, tested by the trials; model names live in the config, `R-ROUTING` decides escalation)

| Role | Tier |
| --- | --- |
| Intent work, planner, Doctor, unattended retro (analysis), evaluator at milestone end | top |
| Worker, repair session, per-task evaluator (not below the worker), retro changes | mid, medium effort |
| Runner, gate, report, placeholder scan | none (scripts) |

Escalate by role, not by raising the worker for everything. A small or local model is never worker, evaluator or acceptance.
<!-- RULE:R-TRON:END -->
