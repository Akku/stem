# Project setup (one-time, agent procedure)

This file is the one-time setup procedure. Delete it as the last step (see step 8); STEM keeps it for the next project.

Talk to the user in their language. Follow the `Communication` standard in `AGENTS.md` (explain what you do and why, define new terms at first use, summarize each step, give links for anything the user should test or decide). Ask before anything with side effects outside this folder (global installs, creating remote repositories, pushing); the tool-permission prompt counts as asking.

## 0. Check that STEM arrived complete
The ZIP route sometimes loses hidden folders (names starting with a dot are hidden on macOS Finder). Check that these exist: `.claude/skills/`, `.agents/skills` (a link to `../.claude/skills` so Codex finds the skills; the ZIP route and Windows clones without symlink support turn it into a one-line text file: delete that file and recreate the link with `ln -s ../.claude/skills .agents/skills` on macOS/Linux or `mklink /J .agents\skills .claude\skills` on Windows (a junction, no admin rights needed), then run `git update-index --skip-worktree .agents/skills` so git ignores the changed type; Claude Code and Copilot read `.claude/skills` and work without it), `.claude/settings.json`, `.github/`, `.gitignore`, `scripts/githooks/pre-commit`. If something is missing: tell the user in one sentence, then restore it yourself: download `<repo>/archive/refs/heads/main.zip` (`repo` from `STEM_VERSION`) into a temp folder outside the project, unzip it there, and copy only the missing files/folders (never overwrite existing ones). If the download is not possible, ask the user to copy the extracted folder as a whole (macOS: Cmd+Shift+. shows hidden files).

## 1. Understand STEM (≈2 min, do not read everything)
Read only `AGENTS.md`. Other files are loaded on demand by rule ID. Skills live in `.claude/skills/*/SKILL.md`; Copilot reads that folder, Codex via the symlink `.agents/skills`, others read the file directly.

## 1a. User profile (ask first, before step 1b)
Ask in one short message how the agent should write to the user: "**1** Expert (compact: results, decisions, problems only), **2** Technical (programmer: technical explanations), **3** Non-technical (plain language: what happened, why it matters, terms explained). **Recommend 2 (Technical) as the default** and say so in the message; never recommend 1 or 3 on your own judgment, the user chooses. If unsure or unanswered: 2." Then replace the whole `Communication` block in `AGENTS.md` (the three bullets after `**Communication**`) with the chosen variant below, nothing else added. Keep the last bullet (direct way to test, review or decide) in every variant.

1. Expert: `- Be brief: results, state, decisions the user must make, problems. No reasoning per step unless asked; one sentence per interim update. The user's own instructions override this.` Also set `"outputStyle": "Concise"` in `.claude/settings.json` (Claude Code only; the text covers other tools).
2. Technical: `- Explain technically what changed, why and what comes next; name files, commands and trade-offs; not every tool call. After each phase (setup step, finished task, session end) summarize it. Ask questions with options and a recommendation. The user's own instructions override this.`
3. Non-technical: `- Explain in plain language what happened, why it matters and what comes next; no jargon, not every tool call. After each phase (setup step, finished task, session end) summarize it. Explain a new term (backlog, task, milestone, retro) in one sentence at first use. Ask questions with options and a recommendation. The user may ask for less detail at any time; the user's own instructions override this.`

Record the profile under `Project setup` in `docs/agent/NEXT_RETRO.md`. Later change: the user tells the agent, which rewrites the block (and the `outputStyle` entry). Step 3 keeps assuming a non-technical user for installs, whatever the profile.

## 1b. Project size and modules (ask first, before step 2)
Ask in one short message: "Is the project **small** (a script, a small tool, a few days), **medium** (an app or service with several features, weeks) or **large** (many parts, several people or long-running)? If unsure: medium." Then show the checklist below with the size's preselection, each line with its effect in plain words, and let the user toggle any item. The core is always on and is not offered as a choice: tasks (Backlog.md), commit guard, handoff and session start, `scripts/run.sh`, `AGENTS.md`.

| Module | What it gives you / what it costs | Small | Medium | Large |
| --- | --- | --- | --- | --- |
| Vision and milestones (see `R-ROADMAP`) | Written goal and a thin first slice, so work does not drift. Costs ~10 min up front. Small: one-sentence vision and M1 only. | short | on | on |
| Design interview (`alignment`) | The agent asks one question at a time before building, which avoids rework from misunderstandings. Costs your time: 2-4 questions small, 5-12 medium, 10-20 in rounds large. | on | on | on |
| UX designer and concept phase | Mockups and screen reviews before UI code. Only useful with a user interface. | off | if UI | if UI |
| Context warning hook (needs Python) | Warns when a session gets long and costly and suggests a fresh one. Costs a few lines of context only when it fires. | off | on | on |
| Testing practices skill | Test-quality hints (realistic data, what green really proves). Useful once tests exist. | off | on | on |
| Market analysis skill (`market-analysis`) | Web search for existing alternatives and a one-page build-adapt-use recommendation, so you do not rebuild what exists. Costs a few searches. | off | on | on |
| Glossary (`docs/GLOSSARY.md`) | One list of domain terms and their code and UI names; worth it with many terms or several languages. | off | many terms only | on |
| Architecture map (`docs/ARCHITECTURE.md`) | Short module overview that the agent reads instead of the code. Must be kept current. | off | off | on |
| Shell sandbox (macOS/Linux/WSL2) | Limits what commands can touch, which protects your files from agent mistakes; may block installs or network. Recommended for every project; enabled only on your yes. | recommend | recommend | recommend |

What to do with the answers: delete the files of modules that are off (agent file `ux-designer.md`, skill folders `testing-practices`, `market-analysis`, hook entry and `scripts/context-check.py`; glossary and architecture are only created when on) and drop their names from the `Skills` and `Agents` lines in `AGENTS.md` (an empty `Agents` line goes away), so they cost no context and nothing points at missing files. Record the chosen size and modules under `Project setup` in `docs/agent/NEXT_RETRO.md` (retro checks which were used).

## 2. Ask the user (one message, all questions together)
Scale to the size from step 1b: small = goal in 1-2 sentences, stack, confidential inputs, GitHub; skip horizons beyond the vertical slice, agents and model questions (use defaults); medium/large = all questions.
- Project goal in 3–5 sentences (what, for whom, what "done" looks like).
- Agree the four horizons in `R-ROADMAP`: **vertical slice**, **MVP**, **1.0**, then **Moonshot**. Ask for the scope and observable completion boundary of each; propose answers from the goal if needed. Keep distant horizons brief and revisable. Small projects defer horizons beyond the slice.
- Stack/language preferences, or "decide for me".
- Which agents will be used (Claude Code / Codex / Copilot)? Keep all adapters regardless (including the `.agents/skills` symlink); note the answer under `Project setup` in `docs/agent/NEXT_RETRO.md`.
- Which model and effort level do you use today (e.g. the largest available one)? Note the answer for the recommendation at the end.
- Confidential inputs (customer documents, scripts, exports)? Which folder holds them? Default: `inputs/`.
- Optional glossary of domain terms (term, definition, code name, UI text)? Recommend it only for apps with many domain terms or several languages (e.g. German UI, English code); for small apps say it is not worth it. If yes, create `docs/GLOSSARY.md` from the interview.
- Create a GitHub repository now? Default: private, none yet.

## 3. Check and install prerequisites (assume a non-technical user)
Detect the OS (`uname -s`, or `$OS`/`ver` on Windows). Check: `git --version`, `node --version`, `npm --version`, `backlog --version`, `python3 --version` (optional); optionally `gh --version`.
**Do it yourself.** For each missing tool: say in one plain sentence what it is for, then run the install command (the tool-permission prompt is the user's approval) and verify with the version command. Give the user step-by-step instructions only if they decline the approval, the app denies the command, or a step cannot be automated (e.g. a password or admin prompt: the user types it themselves, never in chat; a GUI installer). After manual steps, re-check with the version command and continue. After an install the terminal/app may need a restart to find the tool; say so.

| Tool | macOS | Windows | Linux |
| --- | --- | --- | --- |
| Git | `xcode-select --install` (also installs Command Line Tools) or `brew install git` | `winget install --id Git.Git -e` (includes Git Bash) | `sudo apt install git` / distro equivalent |
| Node.js (LTS) | `brew install node`, or the installer from nodejs.org | `winget install --id OpenJS.NodeJS.LTS -e` | `sudo apt install nodejs npm`, or nodejs.org |
| Backlog.md | `brew install backlog-md` or `npm i -g backlog.md` | `npm i -g backlog.md` (no Windows-specific steps in its README; fallback `npx backlog.md`) | `npm i -g backlog.md` |
| Python 3 (optional: context warning hook and reports in `scripts/*.py`) | usually present with Command Line Tools; else `brew install python` | `winget install --id Python.Python.3.12 -e` | `sudo apt install python3` |
| GitHub CLI (optional) | `brew install gh` | `winget install --id GitHub.cli -e` | see cli.github.com |

Homebrew missing on macOS: offer the installer from brew.sh (needs the user's password, typed by the user in the terminal) or use the npm route. `winget` missing on Windows: use the installers from git-scm.com and nodejs.org.
Known pitfalls: Apple Silicon with Rosetta-installed Node/Homebrew gives "illegal hardware instruction" / "Binary package not installed" for backlog, so reinstall natively (`arch -arm64 npm i -g backlog.md`). Windows PowerShell may block npm scripts ("running scripts is disabled"); use `npm.cmd`, or after explaining it, `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` with the user's approval. Windows: the scripts in `scripts/` are bash and need **Git for Windows (Git Bash)**; run them with `bash scripts/<name>.sh` (WSL/PowerShell-only setups are untested). Python on Windows is `python` or `py -3`, `python3` is often a Microsoft Store stub; the hook and `retro-metrics.sh` try all three, but when you run `python3 scripts/...` by hand, use the name that works.
If something cannot be installed, explain what is lost and continue where possible. Windows steps are not yet field-tested: record friction under `Observations` in `docs/agent/NEXT_RETRO.md`.

## 4. Git
If this folder is not a git repository (typical for the ZIP route): `git init -b main`; set `user.name`/`user.email` only if missing (ask the user). Add a `.gitignore` for the chosen stack (include `.env*`, logs, build output). **Never commit secrets** because the repository may become public (the pre-commit hook blocks `.env` files and common token patterns).
Always activate the pre-commit hook with `git config core.hooksPath scripts/githooks`: it blocks office/PDF/database files and rejects Done tasks with open boxes (`scripts/check-backlog.sh`). Confidential inputs: create the agreed folder and add it to `.gitignore`; stage explicit paths, not `git add -A`, while untracked inputs exist.

## 5. Initialise Backlog.md
```sh
backlog init "<project name>" --defaults --integration-mode cli --agent-instructions none
backlog config get autoCommit   # must be false: code and task changes are committed together
```
`--agent-instructions none` keeps STEM's `AGENTS.md`/`CLAUDE.md` intact. Afterwards confirm both files are unchanged. Run `backlog instructions overview` once and `backlog config --help` to see how to set a Definition of Done; add a short DoD (if code changed: verification run via `scripts/run.sh`; every acceptance criterion has evidence, or the missing evidence is recorded in the notes with a continuation point; code and task changes committed together). Done tasks with unchecked boxes are rejected by the pre-commit hook (`scripts/check-backlog.sh`); chore tasks use `--no-dod-defaults`. Design, decision and documentation tasks have no code to verify, so the first item must be conditional.

## 6. Adapt the harness to the project goal
- Fill the "Project specifics" block in `AGENTS.md` (goal, stack, verification commands). Keep it under ~15 lines.
- Make sure there is one obvious final verification command and fast targeted ones; document them in `AGENTS.md`. Always via `scripts/run.sh <label> <command>`.
- Claude Code: add the project's verification commands to `permissions.allow` in `.claude/settings.json` as narrow patterns (e.g. `Bash(scripts/run.sh test npm test)`); never a wildcard on `scripts/run.sh` (it runs arbitrary commands).
- `AGENTS.md` stays minimal: no project overview or architecture prose, only requirements the agent cannot infer from the code (`R-SECURITY`, retro budget check).
- Recommend (every project size), enable only on the user's yes: the tool's shell sandbox for macOS/Linux/WSL2 (Claude Code `sandbox.enabled`, see its docs; it can block installs or network access; not available on native Windows).
- Adapt the summary `grep` in `scripts/run.sh` to the test runner's output format, if needed.
- Establish the independent project version per `R-LIFECYCLE` 1.8: preserve an existing version/source, otherwise initialize 0.1.0 in the native manifest or root `VERSION` fallback, and document that source in the project README. Keep `STEM_VERSION` for the adopted harness version. Do not create a release or tag during initialization.
- Create `docs/agent/HANDOFF.md` (max 2 KB, format in the `handoff` skill: state with SHA, approvals, next step, open evidence, blockers). `scripts/session-start.sh` prints it.
- Add stack-specific pitfalls to `docs/agent/PITFALLS.md` only if already known.
- Do not add further agents, skills, hooks or telemetry now (`R-DECISION`); the modules chosen in step 1b are the only optional pieces. Remove what is off.

## 7. First backlog
If the goal is still vague, run the `alignment` skill (stoppable) with the depth from step 1b (small 2-4, medium 5-12, large 10-20 questions in rounds) before writing the vision.
If the direction is unclear or the project has a user interface, follow `R-CONCEPT` first (concept phase); the `ux-designer` agent prepares the mockup rounds. Also check whether existing skill collections offer skills that fit the stack.
Follow `R-ROADMAP`: write the vision (audience, core value, non-goals, moonshot ideas) as a Backlog.md doc (`backlog doc create "Vision"`, check `--help`), then create the milestones `backlog milestone add "M1 Vertical slice" -d "<goal + exit criterion>"`, `M2 MVP`, `M3 1.0`, and `M4 Moonshot` (later horizons: descriptions only). For small projects create only M1 initially. Existing projects adopt the model through the user-reviewed migration in `R-ROADMAP`, without automatic renumbering.
Create 3–7 tasks for M1 with `backlog task create ... -m <milestone>` (check `--help`): small, each with checkable acceptance criteria. The first task is a walking skeleton that already runs the verification command end to end. Tasks for M2 are created later (`R-ROADMAP`).

## 8. Project README, commit and report
Replace STEM's `README.md`/`README.de.md` with a short project README (goal, how to run, verification command); keep `START_HERE.md`/`STARTE_HIER.md`/`STEM_VERSION`/`CHANGELOG.md` unless the user wants them removed.
Remove STEM maintenance files that do not belong in a project: `.github/workflows/stem-check.yml`, `.github/workflows/learning-pr.yml`, `.github/stem-check.py`, `.github/bump-version.sh`, `.github/ISSUE_TEMPLATE/` (field reports go to STEM's repository), `CONTRIBUTING.md` (about contributing to STEM), and the STEM logo `docs/assets/` (only used by the STEM README). Replace STEM's `LICENSE` (MIT, STEM's license) with the project's own choice: ask the user; if unsure, delete it and say that no license means all rights reserved.


Finish all project files first, then commit once, so the setup commit is the complete starting state:
1. Give a short **model recommendation** (load `R-ROUTING` from `docs/agent/ADVANCED.md`): for small and medium projects a mid-tier model at medium effort is usually enough for routine implementation; bigger models or higher effort only for specific cases (unclear concept or architecture, hard debugging, security-relevant review), because the largest models cost much more for little gain on routine work. If the user named the largest model, say gently that switching is their choice and where to do it in their app (model/effort selector). Write the agreed default into the `Model:` line in `AGENTS.md`. Never switch the model yourself.
2. Set `Setup status:` in `AGENTS.md` to `DONE` and delete the line `If TODO: follow ...` and the HTML comment after it; delete `SETUP.md` (its description would otherwise cost context in every session).
3. Commit "Set up agentic harness"; `git status` must be clean afterwards. Optionally push if the user agreed to a remote.
4. Tell the user what exists, the milestones, which commands to use and which task comes first (~12 lines with a one-line explanation per item). Mention that the first retro (after the first milestone) revisits the way of working, including how much the agent explains and whether links and explanations were helpful.

## Later
- First retro: run `R-RETRO`; it works through the `First retro` section of `docs/agent/NEXT_RETRO.md`.
- Valuable, validated learnings can go back into the STEM repository via pull request (`docs/agent/PROCESS_IMPROVEMENTS.md`, "Cross-project promotion").
