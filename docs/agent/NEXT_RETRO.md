# Next retro

The one place for what the next retro needs. Read only in retros (`R-RETRO`) or when investigating process efficiency; not normal task context.
Point to the evidence (task ID, `EXPERIMENTS.md` row, commit) instead of copying it. Format: `- [TASK-ID or STEM / YYYY-MM-DD] observation or check → possible improvement`.
Add here what a later retro must look at: observations that matter beyond one task (`R-LEARNING`), checks due at a retro, questions for the user. Handling: `docs/agent/PROCESS_IMPROVEMENTS.md`.

## Due checks

## Observations

## First retro

Process every item in this section at the first retro, then delete the section.

- [STEM / first retro] Adapter structure: three adapters (Codex, Claude, Copilot) are kept so STEM works with all of them. In the first retro check whether Codex/Copilot were really used and whether the neutrality caused overhead → simplify or keep.
- [STEM / first retro] Rule loading: were rules loaded by ID as intended, or did agents read whole files? Was `scripts/run.sh` actually used, and did it hide anything needed for diagnosis → adjust the wrapper or the instructions.
- [STEM / first retro] UX designer agent: STEM now ships `.claude/agents/ux-designer.md` for projects with a UI. Was it used? Check especially the concept phase at the start (mockups and UX review before the first UI tasks) and later reviews of new screens → keep, adapt, or remove if it was never used.
- [STEM / first retro] Rule inventory: which rules in `OPERATING_MODEL.md` were never loaded? → move to `ADVANCED.md` or delete.
- [STEM / first retro] Session length: in one sample project (36 transcripts, ~6800 turns) three sessions of 1000-2000 turns caused ~80 % of cache-read tokens (avg ~360k carried tokens/turn); tool results were at most ~25 % (85 % of that Bash). Run `scripts/context-report.py`: do your sessions look similar? Did a fresh session at task/milestone boundaries (or ~300 turns) reduce cache-read per accepted task without hurting quality? → keep, tune or drop the threshold in `R-BATCHING`.
- [STEM / first retro] Model choice: which model/effort was used as default, how often was it escalated and why, did mid-tier at medium effort cause rework or quality problems? → keep, adjust the default in `R-ROUTING`, or change the setup recommendation.
- [STEM / first retro] Design alignment: did short `alignment` interviews reduce rework (compare fix/review commits and deleted-line share with earlier work)? Were they too long or skipped? → adjust the question budget or the trigger.
- [STEM / first retro] Glossary and module map: were `docs/GLOSSARY.md` / `docs/ARCHITECTURE.md` used (loaded instead of reading code), did they stay current, did they reduce verbose or inconsistent naming? → keep, shrink or remove.
- [STEM / first retro] Optional practices: which optional/advanced pieces exist in this project and were any used? → remove what is unused.
- [STEM / first retro] Baselines: `docs/agent/EXPERIMENTS.md` rows with baseline "take at first retro": run `scripts/retro-metrics.sh --snapshot` and fill them in.
- [STEM / first retro] Project CI (offer, never force): ask whether the project is long-lived and whether a GitHub repository exists or is wanted. Only if both hold and the `Verify:` command in `AGENTS.md` runs non-interactively, offer a minimal workflow `.github/workflows/verify.yml` that runs it on push and pull request (`on: [push, pull_request]`, one job on `ubuntu-latest` with `actions/checkout@v4`, the stack's setup steps, then the verify command). It adds evidence from a clean machine (forgotten files, uncommitted state) but does not replace manual checks (`R-VERIFY`). On yes: a normal task.

## Project setup

Written by `SETUP.md` (profile, size and modules, agents used); the retro checks what was used. Kept after the first retro.
