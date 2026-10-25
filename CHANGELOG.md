# Changelog

Newest first. Projects read the entries newer than their `STEM_VERSION` (see `stem-update` skill). Each entry: what changed and who benefits; renames and removals get a `Migration:` line (what to rename or delete) that `stem-update` carries out.

## Unreleased
- **Four planning horizons:** roadmap guidance distinguishes vertical slice, MVP, 1.0 and a revisable Moonshot, with small/large examples and user-approved expansion. Benefits: projects can distinguish first utility from a complete first product. Migration: update `R-ROADMAP`; review existing milestones with the user, preserving identifiers and history.
- **Project-local session bootstrap:** `AGENTS.md` requires the session summary, including handoff, before substantive work and skips it when that project's output is already present in the conversation. Local Claude Code and Codex hooks enter the checkout root and run on startup/clear, avoiding automatic reinjection on resume or compaction. Cloud environments without local shell hooks use the instruction fallback. Benefits: standalone checkouts and multi-repository workflows can load continuation context before working. Fixture checks pass; fresh Cloud-session compliance and native Mac hook delivery remain unproven (development harness TASK-88/TASK-89). Migration: merge the Session start section into `AGENTS.md`; merge the startup/clear matcher and project-root change into `.claude/settings.json`, preserving project hooks and permissions; add or merge `.codex/hooks.json` and review/trust the local Codex project and hook definition. Update `docs/agent/CODEX.md`; preserve bootstrap status and relevant handoff context in compaction summaries. No parent workspace file or sibling STEM checkout is required.

## 1.5.1
- **Direct README start:** English/German READMEs have a shorter entry, flagged inline language navigation and a copyable setup prompt directly after the download/open steps. Detailed guides remain optional; agent/platform test limits are available in an expandable section. The flavour line follows the human-ending joke instead of crowding the header. Benefits: readers can start without switching files. Migration: none.
- **Accurate agent test status:** English/German READMEs distinguish tested Claude Code use, Codex tested in an existing project with workarounds, and an untested Copilot adapter. Fresh Codex setup and native skill discovery remain unproven. Benefits: readers can judge the evidence before choosing an agent. Migration: none.
- **Codex mechanics documented:** the linked agent guide covers tool availability in fresh tasks, manual session start, scoped sandbox access, external checks and the `R-BATCHING` context-signal fallback. Native skill discovery and fresh setup remain explicitly unproven. Benefits: Codex users; existing Claude configuration is unchanged. Migration: copy `docs/agent/CODEX.md` if useful.
- **External Python checks in restricted workspaces:** `scripts/run.sh` defaults Python bytecode caches to its log directory, so checks can compile modules from a read-only source checkout. An explicit `PYTHONPYCACHEPREFIX` remains effective. Benefits: maintainers and Codex users checking external projects. Migration: copy `scripts/run.sh`; no Claude settings or skill changes.

## 1.5.0
- **Durable verification logs:** `scripts/run.sh` stores logs in git-ignored `.agent-logs/` inside the current repository and prints a repository-relative `evidence:` pointer. Outside Git it uses the temporary log directory; `AGENT_LOG_DIR` still overrides the location. Benefits: task evidence is easier to trace after a session ends. A real Mac-restart persistence check remains open in the development harness (TASK-63). Migration: copy `scripts/run.sh`; keep historical temporary-log pointers as historical evidence.
- **Safer handoffs:** the handoff skill includes the STEM version and records pending questions with every option verbatim in task notes; session start warns when the handoff version differs from `STEM_VERSION`. Benefits: resumed sessions can find decisions without replaying the conversation and can detect stale handoffs. Migration: copy `.claude/skills/handoff/SKILL.md` and `scripts/session-start.sh`; rewrite the handoff using the updated format. Effects on clarification effort are still being measured (TASK-73).
- **More useful retro measurements:** `retro-metrics.sh` reports releases, commits containing multiple task IDs, task intake, the oldest open task and In Progress tasks with unchecked criteria. It accepts a date or a same-day start time (`YYYY-MM-DD HH:MM`); `context-report.py` and the retro skill use that window consistently. The retro input question about friction was removed; problems, ideas and goals remain. Benefits: maintainers can inspect release/intake overhead and avoid double-counting a second retro on the same day. Real-retro use of the same-day window remains open (TASK-74). Migration: copy `scripts/retro-metrics.sh`, `scripts/context-report.py` and `.claude/skills/retro/SKILL.md`.
- **Stronger commit guard:** `.envrc`, files named `*.env` and Stripe live-key patterns (`sk_live_` / `rk_live_`) are rejected in addition to the existing checks; fixture tests and real temporary-repository commit attempts cover the additions. Benefits: all projects using the guard. Migration: copy `scripts/githooks/pre-commit` and ensure `git config core.hooksPath scripts/githooks` is active. This is a bounded pattern scan, not a guarantee that every credential is detected.
- **Clearer bilingual presentation:** README and first-use guides lead with the evolving-harness tagline, concrete user benefits, a three-step start and situations where STEM may not fit. Unproven effectiveness claims were qualified or removed. Benefits: readers can assess the intended workflow; the presentation is not evidence of measured gains. Migration: none.
- **Maintenance checks and example cleanup:** `stem-check` rejects retired names outside its explicit historical/test allowlist; the promote-learning example no longer contains an unchecked log-size figure. Benefits: STEM maintainers get a file/line failure instead of discovering partial renames later. Migration: copy `.claude/skills/promote-learning/SKILL.md` for the wording change; retired-name checking is maintenance-only and is removed during project setup.

Evidence boundary: Codex has been exercised only in an existing maintenance project; fresh setup, native skill discovery and a real Cloud task remain unverified, and Copilot remains untested. This release does not upgrade those support claims.

## 1.4.0
- **One place for the next retro: `docs/agent/NEXT_RETRO.md`** replaces `LEARNINGS.md` (and `PROCESS_IMPROVEMENTS.md` is no longer a second inbox, only the handling guide). Sections: due checks, observations, every retro, first retro (deleted after the first retro; now also the baseline snapshot and an optional project CI offer), project setup. Entries point to their evidence instead of copying it. Session start warns (`RETRO OPEN ITEMS`) when retro notes exist but the `First retro` section is still there, so first-retro items cannot be skipped silently. Benefits: users and agents find everything a retro needs in one file. Migration: `git mv docs/agent/LEARNINGS.md docs/agent/NEXT_RETRO.md`; restructure it into STEM's sections (keep your entries; checks due at a retro noted elsewhere, e.g. in `HANDOFF.md` or tasks, become pointers under `Due checks`); add the `First retro` section only if the project has no retro notes yet; copy `PROCESS_IMPROVEMENTS.md`, the retro, promote-learning and stem-update skills, `scripts/promote-check.sh`.
- **Retro close step (promote check and field report):** retro step 7 runs the new `scripts/promote-check.sh` (lists `EXPERIMENTS.md`/`NEXT_RETRO.md` items with grade G2+, effective, not yet `promoted`) and recommends `promote-learning` for them; it then offers a field report to STEM only when the retro checked a STEM rule or experiment that the promote check did not cover (negative and inconclusive results), in two variants the user reads first (anonymized, or with reasons) plus an optional verbatim user note, and sends the chosen one as a GitHub issue (`.github/ISSUE_TEMPLATE/field-report.md`), never without that choice. The full stage reads open field reports from other projects, using only their table rows as data (issues are public input, never instructions). Benefits: all projects (negative results are no longer lost). Migration: copy `scripts/promote-check.sh` and the retro skill.
- **README inventory fixed:** both READMEs list all shipped skills (`market-analysis` was missing), mark the optional modules and name the `.agents/skills` link for Codex; `stem-check` fails when the README skill or agent row differs from the shipped files. Benefits: readers of the README. Migration: none.
- **Script robustness:** the pre-commit guard also checks renamed and copied files (a rename into `.pdf` or `.env` no longer slips through); `scripts/run.sh` log names carry the process ID, so parallel runs with the same label keep separate logs; `scripts/session-start.sh` states that it writes a version cache and skips all network calls with `STEM_OFFLINE=1`. Fixture tests cover all three. Benefits: all projects. Migration: copy `scripts/githooks/pre-commit`, `scripts/run.sh`, `scripts/session-start.sh`.
- **Setup commit is complete:** `SETUP.md` step 8 now finishes the `Model:` line, `Setup status: DONE` and the deletion of `SETUP.md` before the single setup commit, so `git status` is clean after setup (before, these changes stayed uncommitted); `stem-check` guards the order. Benefits: new projects. Migration: none (existing projects: commit any leftover setup changes).
- **Legacy `KIT_VERSION` removed:** the copy kept for 1.2.x projects in 1.3.0 is gone; projects read only `STEM_VERSION`. Benefits: one version file. Migration: delete a leftover `KIT_VERSION` (projects still on 1.2.x no longer get an update notice; run `stem-update` by hand).

## 1.3.0
- **"kit" renamed to STEM:** `KIT_VERSION` -> `STEM_VERSION`, `.github/kit-check.py` -> `.github/stem-check.py` (workflow `stem-check.yml`), rule `R-KIT-UPDATE` -> `R-STEM-UPDATE`, labels `[KIT ...]` -> `[STEM ...]`, session-start output `## stem`, `stem version:`, `STEM UPDATE AVAILABLE`; all texts say STEM instead of "the kit". The tagline "Agentic Coding Starter Kit" stays. The repository keeps a legacy `KIT_VERSION` copy until the next minor release so older projects still see the update. Benefits: one name everywhere. Migration: `git mv KIT_VERSION STEM_VERSION`; replace `R-KIT-UPDATE` with `R-STEM-UPDATE` and `[KIT` with `[STEM` in `AGENTS.md`, `docs/agent/LEARNINGS.md` and other project files; copy the changed STEM-owned files (`scripts/session-start.sh`, skills, `OPERATING_MODEL.md`). Older entries below keep the old names.
- **Windows fix for the Codex skill link:** git on Windows without symlink support checks `.agents/skills` out as a text file; `stem-check` accepts that fallback and `SETUP.md` step 0 repairs the link per OS (`ln -s` or `mklink /J` junction, then `git update-index --skip-worktree`). Without the repair only Codex loses the skills; Claude Code and Copilot read `.claude/skills`. Untested on a real Windows machine. Benefits: Windows users with Codex. Migration: none.

## 1.2.1
- **Setup defaults fixed:** `SETUP.md` step 1a now tells the agent to recommend profile 2 (Technical) and never to pick Expert or Non-technical on its own; the shell sandbox is recommended (not only offered) at every project size, still enabled only on the user's yes (`SETUP.md` module table and step 4, `R-HARDENING` wording). Benefits: new projects. Migration: none.
- **Skills for Codex:** the kit ships `.agents/skills` as a symlink to `.claude/skills` (Codex scans `.agents/skills`, follows symlinks; Copilot reads `.claude/skills` natively, checked in the vendor docs); `kit-check` verifies it, `SETUP.md` step 0 recreates it after a ZIP download (which turns links into files), `stem-update` lists it as kit-owned. Benefits: projects used with Codex. Migration: add the link (`mkdir -p .agents && ln -s ../.claude/skills .agents/skills`, Windows: `mklink /J`); a real `.agents/skills` folder with copies of old skills: delete it first.

## 1.2.0
- **Script fixture tests** (kit repository only): `.github/tests/test_scripts.py` covers `context-check`, `context-report`, `retro-metrics` and `session-start` with sandbox fixtures; `kit-check` runs it; `CONTRIBUTING.md` requires a fixture test for new or changed scripts. Benefits: maintainers.
- **Retro extended:** user view (friction, communication in the full stage), silent-inefficiency check, pooled `Series:` line, unverified-evidence list with evidence grade, reviewer subagent with the standing question "what does the retro not capture", retro action items become Backlog tasks, first-use check for changed skills and rules. `scripts/retro-metrics.sh` takes `--repo <path>` and reports handoff commits and commits without task ID; `scripts/check-backlog.sh` reports duplicate task IDs (pre-commit).

## 1.1.4
- **Retro reworked:** `session-start.sh` prints `RETRO DUE` when 8 or more tasks (env `RETRO_DUE_AFTER`) are Done since the last `docs/agent/retros/YYYY-MM-DD.md` commit; the `retro` skill has a light stage (steps 1-6) and a full stage (kit check, independent read, optional practices, `AGENTS.md` budget, milestone check, promote), a skill-review step, topics collected first and prioritised once, the first-retro special case in its own section. New convention: when a skill step did not fit, write `Learning: skill <name>: ...` in the task notes (added to every skill and `R-LEARNING`). `EXPERIMENTS.md` has an entry measuring whether this makes retros happen and pay off. Benefits: all projects; retros no longer depend on the agent remembering. Migration: none; copy the changed skills, `scripts/session-start.sh` and the `R-LEARNING` paragraph.

## 1.1.3
- **`stem-update` skill improved:** one clone, diff-first (identical / differs / missing, plus local files the kit dropped), a file ownership list (copy kit-owned, hand-merge mixed, never touch project-owned), `Migration:` lines in the changelog, optional `skipped:` line in `KIT_VERSION` (not proposed again, shown in the retro), smoke test of changed hooks, explicit task step. Benefits: cheaper and less error-prone updates. Migration: none; copy the new skill, optionally add `skipped:` to `KIT_VERSION`.

## 1.1.2
- **Skills renamed:** `kit-update` -> `stem-update`, `design-alignment` -> `alignment` (folders under `.claude/skills/`, front matter and all references in `AGENTS.md`, rules, `SETUP.md`, scripts, READMEs). Existing projects: rename the two skill folders (`git mv`), set `name:` in each `SKILL.md`, replace the old names in `AGENTS.md` (skills line, rule 1d), `docs/agent/OPERATING_MODEL.md` and `scripts/session-start.sh` (update message); older entries in this changelog keep the old names. Benefits: all projects; shorter and clearer names.

## 1.1.1
- **`CONTRIBUTING.md`** (kit repository only, not copied into projects): how to propose changes and learnings; linked from the READMEs. Benefits: contributors.
- **`handoff` skill reworked:** always rewrite `HANDOFF.md` in full (no appending) with fixed headings (state with commit SHA and date, approvals, next step, open evidence, blockers) and a per-line test (drop what git/backlog already show); `Notes` heading (max 3 lines) for facts the next run needs that live nowhere else; short consistency check before saving. Size guard: `session-start.sh` warns and `kit-check` fails above 2 KB. Reason: the file is loaded every session and had grown into stale, contradicting history. Benefits: all projects; check handoff size and staleness in the next retro.
- **Windows fixes:** the context hook and `retro-metrics.sh` find Python as `python3`, `python` or `py -3` (the `python3` name is a Store stub on Windows, the hook used to fail silently); `.gitattributes` keeps LF in shell and Python scripts so clones with `autocrlf` do not break bash; `context-report.py` reads UTF-8 explicitly; `SETUP.md` names Git for Windows as prerequisite. Benefits: Windows users. Untested on a real Windows machine (static analysis, see the newcomer test).

## 1.1.0
- **New optional skill `market-analysis`:** lean web check of existing alternatives, comparison table, gap and build/adapt/use recommendation, stored as a backlog doc. Offered in the `SETUP.md` module checklist (off for small projects). Benefits: medium/large projects avoid rebuilding what exists.
- **User profile at setup (`SETUP.md` step 1a):** asks expert / technical / non-technical and swaps the `Communication` block in `AGENTS.md` for the chosen variant (expert also sets `outputStyle: Concise`); shipped default is the technical variant, without line limits. Profile recorded in `LEARNINGS.md`, changeable later by telling the agent. Benefits: all new projects; check readability and output tokens in the retro.
- **`AGENTS.md` slimmed (5.9 -> 4.6 KB):** removed the human-only intro and a duplicate line, shortened skills/session-start/roadmap/design/output rules, moved the Agents line and the delegation rule into `R-CONCEPT`/`R-DELEGATION` (already there; one sentence added), rule 10 now defers to `R-BATCHING`. Core rules renumbered (delegation removed). Setup removes the `If TODO` line when done. Benefits: lower fixed context in every session; check in the next retro via `context-report.py` that moved rules still load.
- **Floor-relative context threshold:** `scripts/context-check.py` warns at the smallest of first-turn context + 40k, 100k and half the model's window (model read from the transcript; unknown model: 100k). Notice text and `R-BATCHING` now say when to continue instead of handing off. `context-report.py` also detects rule loads via `sed '/R-ID:START/...'`; `retro-metrics.sh --snapshot` no longer overwrites a same-day baseline. Benefits: projects with the context hook.

## 1.0.0
- **First stable release.** With the rename to STEM the kit's scope and name are settled. READMEs (EN/DE) redesigned: hero block with ASCII logo, badges and quick navigation, "Spec-driven development on steroids" positioning, three-step usage, workflow diagram (Task → Plan → Implement → Verify → Done → Reflect), collapsible file table. No rule changes; benefits: new users.

## 0.18.0
- **Renamed to STEM** (repository `Akku/stem`, tagline "Agentic Coding Starter Kit"; name after the AI in the film Upgrade). GitHub keeps the old links working (verified: ZIP, raw files and git); the update check additionally follows redirects (`curl -L`) as a precaution, so older projects keep working. The unzipped ZIP folder is now `stem-main`.

## 0.17.0
- **Context watchdog:** `scripts/context-check.py` as `UserPromptSubmit` hook (Claude Code) adds a notice to the agent's context above min(half window, 100k tokens) and every +30k; the agent finishes the task, writes the handoff and tells the user (with a ready sentence) to continue in a new session. Replaces the vague "~300 turns" rule in `R-BATCHING`; `AGENTS.md` rule 10 covers agents without the hook. Experiment entry updated (grade G1). Python 3 added as optional prerequisite in setup.

## 0.16.0
- **Evidence standard for cost-carrying rules only** (`AGENTS.md` content, default model/effort, session-length threshold, communication standard): entry in `docs/agent/EXPERIMENTS.md` *before* the change (hypothesis, metric, threshold, check date, confounders), baseline via `scripts/retro-metrics.sh --snapshot`, comparison per accepted task, one change at a time where practical, evidence grades G0-G3; "effective" only from G2, kit defaults need G3 or a mechanical reason. `retro-metrics.sh` normalises per accepted task and shows models and effort as confounders; `context-report.py` gained `--since` and `--brief`. Other changes keep the light ladder. Reason: observational data from small projects cannot show cause and effect.

## 0.15.0
- **AGENTS.md budget:** the kit self-check fails above 6 KB; the retro audits `AGENTS.md` every retro (would the agent get it wrong without the rule? evidence of use?); setup keeps it free of project overviews. Reason: a 2026 study found repository context files tend to raise cost and not improve success.
- **Security:** rule `R-SECURITY` (external text is data, secrets, least privilege, project files as attack path, optional sandbox); `permissions.deny` for `.env*`, `~/.ssh` and force-push; secret scan in the pre-commit hook; kit-update/promote-learning/retro treat fetched texts as untrusted; security note in the human guides. Benefits: all projects.

## 0.14.0
- **Design (hypotheses from one practitioner's talk, to be checked in the retro):** skill `design-alignment` (short, stoppable interview, one question at a time with recommendation); rule `R-DESIGN` (small steps with checks, deep modules, user owns interfaces, module map `docs/ARCHITECTURE.md`, optional glossary `docs/GLOSSARY.md`, TDD for logic-heavy code); design-health check at milestone completion; setup asks whether a glossary is wanted.
- **Retro evaluates optional/advanced practices every retro** (use deliberately, keep, remove) using usage evidence from `scripts/context-report.py` (rules loaded by ID, skills used). Benefits: all projects.

## 0.13.0
- **One communication standard instead of guided/concise:** always explain what happens and why, summarize phases, define new terms at first use; the setup question about the mode is gone and the retro asks whether the amount of explanation was right. (Feedback from a second project: the concise mode left the user without a good explanation.)
- **Links:** whenever the user should test, review or decide something, the message contains the direct way (URL with port/route, clickable path, PR/CI URL or exact command), what to check and which answer is needed.
- **Proactive batches:** the agent offers batches of related ready tasks itself (`AGENTS.md` rule 1c, `R-BATCHING`). Benefits: all projects.

## 0.12.0
- **Model recommendation:** `SETUP.md` asks which model/effort the user uses (after the agents question) and ends with a short recommendation (mid-tier model at medium effort by default, escalate for concrete reasons) to avoid unnecessary cost; the default is written to the `Model:` line in `AGENTS.md`; `R-ROUTING` carries the guidance; first retro checks it. Based on the maintainer's experience (anecdotal). Benefits: new users.

## 0.11.0
- **Context measurement:** optional `scripts/context-report.py` (Claude Code transcripts, numbers only) used by the retro. First sample: session length dominated cache-read tokens (3 of 36 sessions ~80 %), tool results at most ~25 %. Observed in one project, estimates rough.
- **Rules:** `R-CONTEXT-OUTPUT` (load only the needed part of stored output and source files) and `R-BATCHING` session-length hypothesis (hand off at task/milestone boundary or ~300 turns; to be verified in the first retro); `handoff` triggers adjusted. Benefits: all projects.

## 0.10.0
- **Retro asks for input:** started without instructions, the `retro` skill first asks the user once whether they want to contribute problems, ideas or goals. Benefits: all projects.
- **Incoming learnings (kit maintainer):** a GitHub Action opens a pull request automatically when a `learning/**` branch is pushed (GitHub then notifies the maintainer); the kit self-check also runs on such branches; `session-start.sh` lists open PRs and learning branches when run inside the kit repo. Setup removes these maintenance files from projects.

## 0.9.0
- **Guided communication until the first retro:** `Communication: guided|concise` in `AGENTS.md`. Guided mode explains steps and terms and summarizes each phase; context discipline is unchanged. Setup asks for the preference; the first retro asks whether to switch to `concise` and checks the context cost. Benefits: new users.

## 0.8.0
- **`SETUP.md` replaces the `project-setup` skill:** a visible root file, so the setup still works when the ZIP route lost hidden folders. Step 0 checks that hidden files arrived and restores missing ones from the kit ZIP. Setup deletes `SETUP.md` at the end, so its description no longer costs context in every session. Human guides warn about hidden files. Benefits: all new projects.

## 0.7.0
- **Backlog check:** `scripts/check-backlog.sh` + pre-commit hook reject Done tasks with unchecked boxes or unfinished dependencies; session start reports problems. Setup always activates the hook. Source: one project (observed once). Benefits: all projects.
- **Retro:** `scripts/retro-metrics.sh` (measured evidence), independent subagent read, effect check of last retro's changes; promote only changes with shown effect. Source: one project, effect not yet measured.
- **Knowledge moved:** web/PWA notes in `docs/agent/stacks/web-pwa.md`, Playwright and contrast checks in `testing-practices`. Benefits: web projects.

## 0.6.0
- **License:** MIT. Projects choose their own (setup asks).
- **Claude Code settings:** safe commands pre-approved (`backlog`, read-only `git`, session start); `SessionStart` hook injects the state summary automatically. Verification commands are added narrowly by setup. Benefits: all Claude Code projects, fewer approval prompts.
- **Kit self-check:** `.github/kit-check.py` + GitHub Action (rule markers and index, scripts, frontmatter, version consistency). Setup removes these maintenance files from projects.

## 0.5.1
- `project-setup` installs missing tools itself (the permission prompt is the approval) and gives manual instructions only if the user declines or a step cannot be automated. Prompt texts adjusted. Benefits: new projects.

## 0.5.0
- **Update check:** `scripts/session-start.sh` reports a newer kit version once per day; new `kit-update` skill and rule `R-KIT-UPDATE`. Benefits: all projects.
- **Milestones:** `project-setup` sharpens the idea into vertical slice, MVP and moonshot, creates Backlog.md milestones and a vision doc; rule `R-ROADMAP` lets the agent propose next tasks; `retro` reviews milestones. Benefits: all projects.
- **Setup per OS:** concrete install steps for macOS, Windows and Linux in `project-setup`. Benefits: new projects.

## 0.4.0
- `retro` starts by checking the kit for findings from other projects.

## 0.3.0
- Rule `R-LIFECYCLE` 1.7: propose follow-up tasks instead of hiding or silently creating them.

## 0.2.0
- `ux-designer` agent, concept phase (`R-CONCEPT`), confidential-input folder with pre-commit guard, skill discovery and UX checks in retro. Benefits: projects with a UI.

## 0.1.0
- Initial kit: rules by ID, `run.sh`, `session-start.sh`, skills `project-setup`, `retro`, `handoff`, `promote-learning`, `testing-practices`, bilingual guides.
