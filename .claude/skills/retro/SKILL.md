---
name: retro
description: Run a short process retrospective for the agentic harness - turn measured evidence, task learnings, skill feedback and an independent read of the raw data into a few testable process changes, and check last retro's changes for effect. Use when session start reports "RETRO DUE", after a milestone, a run of related tasks, recurring friction, or for the first retro of a new project.
---

# Retro

Rules: `R-RETRO`, `R-LEARNING` (`docs/agent/OPERATING_MODEL.md`), `R-MEASUREMENT` (`docs/agent/ADVANCED.md`), loaded by ID (AGENTS.md). Read no other files in full.

**Stage.** *Light* (default, e.g. after "RETRO DUE" or recurring friction): the sections up to *Close*. *Full*: also read `full-stage.md` (next to this file) and do its sections, when a milestone was completed, a STEM update was adopted, about 20 or more tasks have passed since the last retro, or the user asks. No retro notes yet means the first retro: also do "First retro". Name the stage first.

**Guided run.** `python3 scripts/retro-run.py start --stage light|full [--flag milestone-completed]` (resume: `status`). `docs/agent/retro-steps.json` lists the steps, their stage, kind and required evidence; this skill says how to do each (`ref` names its section). Technical steps: `retro-run.py run <step>`; analysis and decision steps: `done <step> --evidence <result> --ref <task/commit/file>`; only the user may waive a step: `waive <step> --reason <why> --author-said "<their words>"` (never on your own proposal). `finish --adopted N --signals N` fails while a step is open, blocked, stale or undecided, stores the result (0/0 doubles the due threshold) and prints the run's cost line. A changed step file or referenced skill section makes the step's evidence stale; only the user may keep it (`revalidate --note <why unaffected> --author-said "<their words>"`).

## STEM version
Every retro (light too): `retro-run.py version-check`. It stores source, time and result; offline or unreachable counts as blocked, never as current. A newer version: read its `CHANGELOG.md` entries, show the user the changes and let them choose `decide --choice update|keep --note <reason>`; never update unasked (`stem-update` does the update as its own task). Results that depend on changed instructions are rechecked after an update.

## Extra topics
Run `python3 scripts/retro-topics.py` (second retro on the same day: `--retro YYYY-MM-DDb`). It records its output in `docs/agent/retro-topics-state.json` (commit it with the notes) and prints topics with reason and guiding question: due triggers and signals without cap, filled up to 2 with once or rotating topics. They are topics of *Pick*, exempt from its limit; each ends as a decision, a task, or a dropped item with a reason. Catalog: `docs/agent/retro-topics.json` (additions: `retro-topics.local.json`). Exit 2 or an error: say so, continue without.

## User input
If the retro was started without further instructions, ask the user once (one short message), with "no" as a fine answer, for problems, ideas or goals. Record the answers verbatim in the retro notes under "User view". Use them as evidence and as the topics' tie-breaker; never block on them.

## Measure
Run `python3 scripts/context-report.py` (numbers only; check the session-length hypothesis in `R-BATCHING`; unknown format = "not evaluable"); for a metric starting after a change add `--since <time>` (local `YYYY-MM-DD HH:MM` or ISO with `Z`) and check the printed UTC window. Then `scripts/retro-metrics.sh [since]` if it exists (second retro on the same day: pass the commit time of the first notes file and add a `## Second retro HH:MM` section to that day's notes file). Then read `docs/agent/NEXT_RETRO.md` (every section is input), `Learning:` lines in recent task notes (`backlog search "Learning:"`), `git log --oneline -30`. Failed or long CI runs only via `scripts/run.sh`.
- **Silent inefficiency:** from "biggest carried results" and the commit/task record list up to 3 things that worked but were costly or repeated (large output carried for many turns, a command or step redone, a detour without a `Learning:` note, rework after release such as a retag, revert or rename, with its cause); per item name a cheaper way. These are topics even without a `Learning:` line.
- **Unverified evidence:** list Done tasks whose notes say "not yet run / exercised / tested", unchecked acceptance criteria in open tasks, and claims resting on a desk check or simulation. Grade each: *run* (on the target), *simulated* (stand-in), *static* (read only). Report a metric in the notes: count and share of weak items and what they have in common. List individually only items without owner or follow-up; omit what the user accepted at release. No per-item triage with the user, who decides only on a pattern (e.g. a missing test tool). This, not the cost numbers, is the main risk view.
- **Unrecorded decisions:** lasting decisions of this period (what `R-DECISION` names) in task notes or the user's input without a record in `backlog/decisions` get a record or a reason to drop.
- **Cost series:** write `Series: <date> | tasks | turns/task | cache_read/task | output/task | models+effort | first-to-last commit span | handoff commits per task | share of commits without task ID` in the notes, copied from the metrics output (STEM projects: `scripts/retro-metrics.sh --repo <path> [since-date]`), compare with all earlier `Series:` lines and state the total task count behind the trend. Append the cost line of `retro-run.py finish` as `retro cost: <stage> turns=.. tool_calls=.. cache_read=.. output=..`.

## Start context
Every retro: `python3 scripts/start-context.py report` (median start context per session, trend; numbers only; compare a change with `--compare <time>`, same model only). Write the median into the retro notes next to `Series:`. In the **second or third retro** (once, unless the user asks again) read `start-context.md` (next to this file) and run its dialog.

## Check last changes
For each adopted change compare its metric with the data and name the evidence grade (`R-MEASUREMENT`). For cost-carrying rules use the entry in `docs/agent/EXPERIMENTS.md`: metric per accepted task against the stored baseline and the preset threshold, with confounders (models and effort appear in `scripts/retro-metrics.sh` output). Say "effective" only from grade G2; below that write "indication" and tighten, extend or drop the change. Implemented is not effective.

## Skill review
For each skill used since the last retro (usage in the `context-report.py` output) read the `Learning: skill <name>` lines and ask: did the run follow the skill's steps, where did it deviate, what was missing or unnecessary? Each concrete finding becomes a topic (improve the skill via a normal task). Skills never used: see "Optional and advanced practices" in `full-stage.md`.

## Pick
Gather topics from *Measure*, *Check last changes*, *Skill review*, the user's input and the full stage, each with evidence (task ID, commit, run). Pick at most 3 (light) or 3-5 (full), not counting *Extra topics*. Classify each: Adopt / Experiment / Defer / Discard / Promote (see `docs/agent/PROCESS_IMPROVEMENTS.md`). Prefer what a machine enforces (check, hook, script, test) over new written rules; a rule costs context in every session.

## Record and implement
For each adopted change write the change, where it lives (one authoritative location, no copies), the problem it solves, a **metric** and the date or retro at which to check it; mark it *implemented*, never *effective* until a later retro shows it. Every changed skill or rule gets a first-use check: the next retro reports "used / not used". Every action item worth doing becomes a Backlog task (description, acceptance criteria, metric) without asking again (exception to `R-LIFECYCLE` 1.7: the user started the retro); the user sets priority. Changes done in a few minutes are implemented directly and noted. Problems only the user can solve (e.g. release timing) are noted, not tasked. Write the notes to `docs/agent/retros/YYYY-MM-DD.md` (exactly this name; session start counts tasks since its commit). Remove resolved items from `NEXT_RETRO.md` and add there what the next retro must check (pointers to the metric or task, not copies); keep retro-created tasks visible until done.

## Close
After the notes are written.
- **Promote check:** run `scripts/promote-check.sh`. If it lists items, recommend the `promote-learning` skill for them in one line each: it sends the pattern to STEM as a public, anonymized pull request, so other projects get the improvement. The user decides; mark a promoted item `promoted <PR link>`.
- **Field report (offer, never send unasked):** read `field-report.md` (next to this file) and follow it.

**First retro** (no `docs/agent/retros/` notes yet): also work through the `First retro` section of `NEXT_RETRO.md`, then delete that section. The communication question (*User input*, b) is mandatory here; keep changes to the `Communication` block small.

Output to the user: decisions needed, changes made, and every open criterion, in as few lines as the content allows.

If a step did not fit or you deviated from it: `Learning: skill retro: <what> -> <change>` in the task notes.
