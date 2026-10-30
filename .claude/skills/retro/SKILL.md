---
name: retro
description: Run a short process retrospective for the agentic harness - turn measured evidence, task learnings, skill feedback and an independent read of the raw data into a few testable process changes, and check last retro's changes for effect. Use when session start reports "RETRO DUE", after a milestone, a run of related tasks, recurring friction, or for the first retro of a new project.
---

# Retro

Rules: `R-RETRO`, `R-LEARNING` (`docs/agent/OPERATING_MODEL.md`) and `R-MEASUREMENT` (`docs/agent/ADVANCED.md`), loaded by ID as described in AGENTS.md. Do not read other files in full.

**Stage.** *Light* (default, e.g. after "RETRO DUE" or recurring friction): the sections up to *Close*. *Full*: also read `full-stage.md` (next to this file) and do its sections, when a milestone was completed, a STEM update was adopted, about 20 or more tasks have passed since the last retro, or the user asks. No retro notes yet means the first retro: also do "First retro". Say the stage in one line before starting.

## Extra topics
Run `python3 scripts/retro-topics.py` (second retro on the same day: `--retro YYYY-MM-DDb`). It records what it gives in `docs/agent/retro-topics-state.json` (commit it with the retro notes) and prints topics with reason and a guiding question: due fixed triggers and signals without cap, filled up to 2 with once or rotating topics. Treat them as topics of *Pick*, exempt from its pick limit; each one ends as a decision, a task, or a dropped item with a reason. Catalog and thresholds: `docs/agent/retro-topics.json` (project additions: `retro-topics.local.json`). Exit 2 or an error: say so, continue without.

## User input
If the retro was started without further instructions, ask the user once (one short message), with "no" as a fine answer, for: (a) problems, ideas or goals; (b) full stage only: were explanations, summaries, questions and links right (too much, too little, too many questions) - adjust the `Communication` block in `AGENTS.md` if needed. Record the answers verbatim in the retro notes under "User view". Use them as evidence and as the topics' tie-breaker; never block on them.

## Measure
For Claude Code projects run `python3 scripts/context-report.py` (numbers only; where the context went, longest sessions, skills used; check the session-length hypothesis in `R-BATCHING`; unknown format means "not evaluable"). Then `scripts/retro-metrics.sh [since]` if it exists (second retro on the same day: pass `'YYYY-MM-DD HH:MM'`, the commit time of the first notes file, and add a `## Second retro HH:MM` section to that day's notes file instead of a new file; session start counts from that file's last commit) (done/open tasks, Done tasks with unchecked boxes or open dependencies, tasks with Learning notes, retro tasks still open, deleted-line share, fix/review commits, CI conclusions). Then read `docs/agent/NEXT_RETRO.md` (every section is input), `Learning:` lines in recent task notes (`backlog search "Learning:"`), `git log --oneline -30`. Failed or long CI runs only via `scripts/run.sh`.
- **Silent inefficiency:** from the `context-report.py` "biggest carried results" and the commit/task record list up to 3 things that worked but were costly or repeated (same large output carried for many turns, the same command run again, a step redone, a detour without a `Learning:` note, rework after release such as a retag, revert, rename or task in the wrong project, with its cause); per item ask whether it was needed and name a cheaper way. These are topics even without a `Learning:` line.
- **Unverified evidence:** list every Done task whose notes say "not yet run / exercised / tested", every unchecked acceptance criterion in open tasks, and every claim resting on a desk check or simulation. Give each task an evidence grade: *run* (executed on the target), *simulated* (scratch copy or stand-in), *static* (read or analysed only). Each item gets an owner and a date, a follow-up task, or is dropped with a reason. This list, not the cost numbers, is the main risk view.
- **Unrecorded decisions:** list lasting decisions of this period found in task notes or the user's input (what `R-DECISION` names: rule, interface, cost trade-off, chosen direction) that have no record in `backlog/decisions`; each one gets a record or a reason to drop it.
- **Cost series:** write one line `Series: <date> | tasks | turns/task | cache_read/task | output/task | models+effort | first-to-last commit span | handoff commits per task | share of commits without task ID` in the retro notes, copied from the metrics output (for STEM projects pass the product repo: `scripts/retro-metrics.sh --repo <path> [since-date]`), and compare it with the `Series:` lines of all earlier retro notes (not only the last one) so small samples add up; state the total number of tasks behind the trend.

## Check last changes
For each adopted change compare its metric with the data and name the evidence grade (`R-MEASUREMENT`). For cost-carrying rules use the entry in `docs/agent/EXPERIMENTS.md`: metric per accepted task against the stored baseline and the preset threshold, with confounders (models and effort appear in `scripts/retro-metrics.sh` output). Say "effective" only from grade G2; below that write "indication" and tighten, extend or drop the change. Implemented is not effective.

## Skill review
For each skill used since the last retro (usage in the `context-report.py` output) read the `Learning: skill <name>` lines and ask: did the run follow the skill's steps, where did it deviate, what was missing or unnecessary? Each concrete finding becomes a topic (improve the skill via a normal task). Skills never used: see "Optional and advanced practices" in `full-stage.md`.

## Pick
Gather the topics from *Measure*, *Check last changes*, *Skill review*, the user's input and the full stage, backed by concrete evidence (task ID, commit, run). Pick at most 3 (light) or 3-5 (full), not counting the step 0 topics. Classify each: Adopt / Experiment / Defer / Discard / Promote (see `docs/agent/PROCESS_IMPROVEMENTS.md`). Prefer outputs that a machine enforces (check, hook, script, template, test) over new written rules; a rule costs context in every session.

## Record and implement
For each adopted change write the change, where it lives (one authoritative location, no copies), the problem it solves, a **metric** and the date or retro at which to check it; mark it *implemented*, never *effective* until a later retro shows it. Give every changed skill or rule a first-use check: the next retro reports "used / not used" for it (from `context-report.py` and task notes). Every action item that may be worth doing becomes a Backlog task (description, acceptance criteria, metric), created by the retro without asking again; the user sets priority. Only changes so small that they are done in a few minutes are implemented directly (still noted in the retro notes). Do not decide for the user problems only the user can solve (e.g. release timing): note them, do not create tasks; write the retro notes to `docs/agent/retros/YYYY-MM-DD.md` (exactly this name; session start counts tasks since its commit). Remove resolved items from `NEXT_RETRO.md` and add there what the next retro must check (pointers to the metric or task, not copies); keep retro-created tasks visible until done.

## Close
After the notes are written.
- **Promote check:** run `scripts/promote-check.sh`. If it lists items, recommend the `promote-learning` skill for them in one line each: it sends the pattern to STEM as a public, anonymized pull request, so other projects get the improvement. The user decides; mark a promoted item `promoted <PR link>`.
- **Field report (offer, never send unasked):** read `field-report.md` (next to this file) and follow it.

**First retro** (no `docs/agent/retros/` notes yet): also work through the `First retro` section of `NEXT_RETRO.md`, then delete that section. The communication question (*User input*, b) is mandatory here; keep changes to the `Communication` block small.

Output to the user: decisions needed, changes made, open criteria. Max 15 lines.

If a step did not fit or you deviated from it: `Learning: skill retro: <what> -> <change>` in the task notes.
