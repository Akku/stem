# Project setup (one-time, agent procedure)

This file is the one-time setup procedure. Delete it as the last step (see step 8); STEM keeps it for the next project.

Talk to the user in their language. Follow the `Communication` standard in `AGENTS.md` (explain what you do and why, define new terms at first use, summarize each step, give links for anything the user should test or decide). Ask before anything with side effects outside this folder (global installs, creating remote repositories, pushing); the tool-permission prompt counts as asking.

**Questions: one per message.** Every step that asks the user something asks exactly one question per message, with options and a recommendation where they make sense, then waits for the answer before the next question. Never bundle several questions into one message, even when a step lists several topics.

## 0. Check that STEM arrived complete
The ZIP route sometimes loses hidden folders (names starting with a dot are hidden on macOS Finder). Check that these exist: `.claude/skills/`, `.agents/skills` (a link to `../.claude/skills` so Codex finds the skills; the ZIP route and Windows clones without symlink support turn it into a one-line text file: delete that file and recreate the link with `ln -s ../.claude/skills .agents/skills` on macOS/Linux or `mklink /J .agents\skills .claude\skills` on Windows (a junction, no admin rights needed), then run `git update-index --skip-worktree .agents/skills` so git ignores the changed type; Claude Code reads `.claude/skills` and works without it), `.deutschlandgpt/skills` (the same kind of link for DeutschlandGPT Code; repair it the same way with `.deutschlandgpt/skills` as the path, only when that app is used), `.claude/settings.json`, `.github/`, `.gitignore`, `scripts/githooks/pre-commit`. If something is missing: tell the user in one sentence, then restore it yourself: download `<repo>/archive/refs/heads/main.zip` (`repo` from `STEM_VERSION`) into a temp folder outside the project, unzip it there, and copy only the missing files/folders (never overwrite existing ones). If the download is not possible, ask the user to copy the extracted folder as a whole (macOS: Cmd+Shift+. shows hidden files).

## 1. Understand STEM (≈2 min, do not read everything)
Read only `AGENTS.md`. Other files are loaded on demand by rule ID. Skills live in `.claude/skills/*/SKILL.md`; Claude Code reads that folder, Codex via the symlink `.agents/skills`, DeutschlandGPT Code via `.deutschlandgpt/skills` (its instruction file `dgpt.md` points to `AGENTS.md`), others read the file directly.

## 1a. Core questions (ask first; one message, only these three)
Setup asks only three things, together in one short message, each with a recommended default; unanswered or unsure means the default:
1. **Project goal** in 3-5 sentences (what, for whom, what "done" looks like). Technical or expert profile: add "name technical constraints if you have any (language, framework, hosting)"; non-technical: do not mention technology.
2. **How the agent writes to you:** **1** Expert (compact), **2** Technical (default, recommended), **3** Non-technical (plain language). Never recommend 1 or 3 on your own judgment.
3. **Backlog language:** read the backlog yourself in a web page in your language? Default: no (English). Recommend yes only if the user wants to follow progress.

Everything else gets a default and is changed only when the user asks (tell the user in one sentence at the end of step 8): size **medium**, **Tron off** (and with it no sandbox offer), all agent adapters kept, no GitHub repository, confidential inputs folder `inputs/` (only if the user mentions confidential files), **no glossary**, model asked only if unknown (never guess from a product name), stack chosen by you from the goal (one sentence with the reason; a constraint the user named wins). **Size large** (user says so or the goal clearly needs it): offer the glossary and architecture map in one question; large also turns the design interview and vision on in full depth.

Apply the profile: replace the whole `Communication` block in `AGENTS.md` (the three bullets after `**Communication**`) with the chosen variant below, nothing else added. Keep the last bullet (direct way to test, review or decide) in every variant.

1. Expert: `- Be brief: results, state, decisions the user must make, problems. No reasoning per step unless asked; one sentence per interim update. The user's own instructions override this.` Also set `"outputStyle": "Concise"` in `.claude/settings.json` (Claude Code only; the text covers other tools).
2. Technical: `- Explain technically what changed, why and what comes next; name files, commands and trade-offs; not every tool call. After each phase (setup step, finished task, session end) summarize it. Ask questions with options and a recommendation. The user's own instructions override this.`
3. Non-technical: `- Explain in plain language what happened, why it matters and what comes next; no jargon, not every tool call. After each phase (setup step, finished task, session end) summarize it. Explain a new term (backlog, task, milestone, retro) in one sentence at first use. Ask questions with options and a recommendation. The user may ask for less detail at any time; the user's own instructions override this.`

Record the profile under `Project setup` in `docs/agent/NEXT_RETRO.md`. Later change: the user tells the agent, which rewrites the block (and the `outputStyle` entry). Step 3 keeps assuming a non-technical user for installs, whatever the profile.


Apply the language: Then replace the `**Language:**` line in `AGENTS.md`:

1. No: leave the line as it is.
2. Yes: `**Language:** talk to the user in the user's language; write task and doc titles, descriptions and acceptance criteria in the user's language too (the user reads the backlog). Keep instruction files, rule text, implementation notes and evidence lines in English.`

Record the answer under `Project setup` in `docs/agent/NEXT_RETRO.md`. If yes, remember step 8 item 5 (web view and optional autostart). Later change: the user tells the agent, which rewrites the line.


## 1b. Modules (defaults, no questions)
Do not show a module checklist. Use the medium preselection; the user may ask for any module later ("turn on Tron", "add a glossary"). Core (always on): tasks (Backlog.md), commit guard, handoff and session start, `scripts/run.sh`, `AGENTS.md`.
- On by default: vision and milestones (`R-ROADMAP`), design interview (`alignment`, used at the first feature, see step 7), context warning hook (needs Python), market analysis skill (offer at the first feature, not now).
- Off by default: `tron` (`python3 scripts/module.py disable tron`, files archived under `docs/agent/modules/tron/files/`), `ux-designer` (on only if the goal has a user interface: then leave it on), glossary, architecture map (large: offered, see 1a).
- Context warning off: write `{"context_warning": false}` to `docs/agent/stem-config.json`; **never edit hook files** (`.claude/settings.json` hook entries, `.codex/hooks.json`): Codex binds its trust to them and the host blocks the edit.
- **Tron and sandbox:** when the user turns Tron on later (the `tron` skill), offer the shell sandbox with it (Claude Code `sandbox.enabled`, macOS/Linux/WSL2; may block installs or network; enabled only on the user's yes). Without Tron setup makes no sandbox recommendation. Tron on: fill `DECISION_FRAME.md` and `INVARIANTS.md` with the user (skill `tron`, step 1).
- Record the answers and defaults under `Project setup` in `docs/agent/NEXT_RETRO.md` (profile, language, size, modules, agents, model).

## 2. Derive the rest yourself
No further questions. From the goal propose the four horizons in `R-ROADMAP` (**vertical slice**, **MVP**, **1.0**, **Moonshot**; distant ones brief) and confirm them in one sentence ("I plan it like this; say if you want it different"). Create the confidential folder and the glossary only when step 1a says so.

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
Always activate the pre-commit hook with `git config core.hooksPath scripts/githooks`: it blocks office/PDF/database files and rejects Done tasks with open boxes (`scripts/check-backlog.sh`); the `pre-push` hook there refuses force pushes and the deletion of remote branches; the `commit-msg` hook there enforces the commit message convention (`R-STATE-COHERENCE`: first line `TASK-<n>: <summary>`; the setup commits use `Initial commit` or `Set up ...`). Confidential inputs: create the agreed folder and add it to `.gitignore`; stage explicit paths, not `git add -A`, while untracked inputs exist.

## 5. Initialise Backlog.md
```sh
backlog init "<project name>" --defaults --integration-mode cli --agent-instructions none
backlog config get autoCommit   # must be false: code and task changes are committed together
```
`--agent-instructions none` keeps STEM's `AGENTS.md`/`CLAUDE.md` intact. Afterwards confirm both files are unchanged. Run `backlog instructions overview` once and `backlog config --help` to see how to set a Definition of Done; add a short DoD (if code changed: verification run via `scripts/run.sh`, where a text-only change (docs, rules, skill files) counts as verified by a green run of the project's check within the last 24 hours; every acceptance criterion has evidence, or the missing evidence is recorded in the notes with a continuation point; code and task changes committed together; for `size-L`, more than about 500 changed lines, or new command execution, data access or authentication: independent review ran or the waiver is justified, `R-REVIEW`). Done tasks with unchecked boxes are rejected by the pre-commit hook (`scripts/check-backlog.sh`); chore tasks use `--no-dod-defaults`. Design, decision and documentation tasks have no code to verify, so the first item must be conditional.

## 6. Adapt the harness to the project goal
- Fill the "Project specifics" block in `AGENTS.md` (goal, stack, verification commands) and delete the HTML comment above it. Keep it under ~15 lines.
- Make sure there is one obvious final verification command and fast targeted ones; document them in `AGENTS.md`. Always via `scripts/run.sh <label> <command>`.
- Claude Code: add the project's verification commands to `permissions.allow` in `.claude/settings.json` as narrow patterns (e.g. `Bash(scripts/run.sh test npm test)`); never a wildcard on `scripts/run.sh` (it runs arbitrary commands).
- `AGENTS.md` stays minimal: no project overview or architecture prose, only requirements the agent cannot infer from the code (`R-SECURITY`, retro budget check).
- Do not edit hook files (see 1b). The sandbox is offered only with Tron (see 1b).
- Adapt the summary `grep` in `scripts/run.sh` to the test runner's output format, if needed.
- Establish the independent project version per `R-LIFECYCLE` 1.8: preserve an existing version/source, otherwise initialize 0.1.0 in the native manifest or root `VERSION` fallback, and document that source in the project README. Keep `STEM_VERSION` for the adopted harness version. Do not create a release or tag during initialization.
- Create `docs/agent/HANDOFF.md` (max 2 KB, format in the `handoff` skill: state with SHA, approvals, next step, open evidence, blockers). `scripts/session-start.sh` prints it.
- Add stack-specific pitfalls to `docs/agent/PITFALLS.md` only if already known.
- Do not add further agents, skills, hooks or telemetry now (`R-DECISION`); the modules kept in step 1b are the only optional pieces. Remove what is off.

## 7. First backlog
Setup itself runs no design interview. The `alignment` skill (stoppable; 2-4 questions small, 5-12 medium, 10-20 in rounds large) belongs to the first feature or task: tell the user once that it runs there if something is unclear. Only if the goal is too vague to write a vision, ask the minimum questions needed.
If the direction is unclear or the project has a user interface, follow `R-CONCEPT` first (concept phase); the `ux-designer` agent prepares the mockup rounds. Also check whether existing skill collections offer skills that fit the stack.
Follow `R-ROADMAP`: write the vision (audience, core value, non-goals, moonshot ideas) as a Backlog.md doc (`backlog doc create "Vision"`, check `--help`), then create the milestones `backlog milestone add "M1 Vertical slice" -d "<goal + exit criterion>"`, `M2 MVP`, `M3 1.0`, and `M4 Moonshot` (later horizons: descriptions only). For small projects create only M1 initially. Existing projects adopt the model through the user-reviewed migration in `R-ROADMAP`, without automatic renumbering.
**Optional technical analysis** (after the milestones, before the M1 tasks): offer it in one question; for medium and large projects recommend doing it, for small ones recommend skipping it; skipping is a fine answer. If accepted, analyse the technical side of the goal yourself from the vision, milestones and stack (for example stack fit, architecture and modules, technical risks, tests and CI, data and security; pick what matters for this project) and ask the user only what you cannot decide, one question per message with options and a recommendation. Stop when no open technical question would change the M1 tasks, or when the user says stop; then list your assumptions. Record each technical decision as a decision record (`backlog decision create`, `R-DECISION`). Propose the resulting work as one list (title, size label `size-S|M|L`, milestone) and create the tasks only after the user agrees; the M1 tasks below include them.
Create 3–7 tasks for M1 with `backlog task create ... -m <milestone>` (check `--help`): small, each with checkable acceptance criteria. The first task is a walking skeleton that already runs the verification command end to end. Tasks for M2 are created later (`R-ROADMAP`).

## 8. Project README, commit and report
Replace STEM's `README.md`/`README.de.md` with a short project README (goal, how to run, verification command); keep `START_HERE.md`/`STARTE_HIER.md`/`STEM_VERSION`/`CHANGELOG.md` unless the user wants them removed.
Remove STEM maintenance files that do not belong in a project: `.github/workflows/stem-check.yml`, `.github/workflows/learning-pr.yml`, `.github/stem-check.py`, `.github/check_select.py`, `.github/rule-reach.py`, `.github/retired-names.py`, `.github/tests/`, `.github/bump-version.sh`, `.github/ISSUE_TEMPLATE/` (field reports go to STEM's repository), `CONTRIBUTING.md` (about contributing to STEM), and the STEM logo `docs/assets/` (only used by the STEM README). Leave the scripts in `scripts/` as they are: a branch marked "STEM maintainer only" is inactive once these files are gone, and an edited STEM script shows up as a conflict in every later `stem-update`. Replace STEM's `LICENSE` (MIT, STEM's license) with the project's own choice: ask the user; if unsure, delete it and say that no license means all rights reserved.


Finish all project files first, then commit once, so the setup commit is the complete starting state:
1. Give a short **model recommendation** (load `R-ROUTING` from `docs/agent/ADVANCED.md`): for small and medium projects a mid-tier model at medium effort is usually enough for routine implementation; bigger models or higher effort only for specific cases (unclear concept or architecture, hard debugging, security-relevant review), because the largest models cost much more for little gain on routine work. If the user named the largest model, say gently that switching is their choice and where to do it in their app (model/effort selector). Write the agreed default into the `Model:` line in `AGENTS.md`. Never switch the model yourself.
2. Set `Setup status:` in `AGENTS.md` to `DONE` and delete the line `If TODO: follow ...` and the HTML comment after it; delete `SETUP.md` (its description would otherwise cost context in every session).
3. Commit "Set up agentic harness"; `git status` must be clean afterwards. Optionally push if the user agreed to a remote.
4. Tell the user what exists, the milestones, which commands to use and which task comes first (~12 lines with a one-line explanation per item). Mention that the first retro (after the first milestone) revisits the way of working, including how much the agent explains and whether links and explanations were helpful.
5. Only if the user wants to read the backlog (step 1a): pick a free port (default 6420), add the start command `backlog browser -p <port>` (opens `http://127.0.0.1:<port>`, this computer only; stop with Ctrl+C) to the project README before the commit, then open the web view with the user and show where tasks are. Then offer autostart (ask, change nothing before the yes, say how to undo it, record the result in the README):
   - macOS: a launchd user agent `~/Library/LaunchAgents/<project>.backlog.plist` (outside the project folder) that runs `backlog browser --no-open --non-interactive -p <port>` in the project folder at login. Undo: `launchctl bootout gui/$(id -u) <plist>`, delete the file.
   - Windows: a `SessionStart` hook in the project `.claude/settings.json` that starts the same command in the background unless the port already answers (Claude Code only; untested). Undo: delete the hook entry.
   - Other systems or "no": README start command only.

## Later
- First retro: run `R-RETRO`; it works through the `First retro` section of `docs/agent/NEXT_RETRO.md`.
- Valuable, validated learnings can go back into the STEM repository via pull request (`promote-learning` skill).
