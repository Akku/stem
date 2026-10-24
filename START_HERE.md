# Start here

*STEM – An Evolving Agentic Coding Harness*

**Version 1.5.1** · 🇩🇪 **Deutsche Version: [STARTE_HIER.md](STARTE_HIER.md)**

STEM is a starting point for agent-driven development with Git and Backlog.md. You give the agent your project goal; it installs what is missing, sets up the tooling, adapts the rules to your goal and then works task by task. On the standard path the agent installs and explains the tools for you.

## Standard path: download the ZIP

1. **Download** STEM: [stem.zip](https://github.com/Akku/stem/archive/refs/heads/main.zip) (also: green **Code** button → **Download ZIP** on the GitHub page).
2. **Unzip** it (macOS: double-click; Windows: right-click → *Extract All*). Rename the folder to your project name and put it where you keep your projects. **Use the whole folder; do not copy files out of it one by one**: it contains hidden items (names starting with a dot, e.g. `.claude`) that Finder hides by default (macOS: Cmd+Shift+. shows them). If something is missing anyway, the agent restores it.
3. **Open your agent** (e.g. the Claude desktop app, Code tab) and choose that folder as the working folder.
4. **Give the agent this prompt**, with your goal filled in:

   > Set up this project: follow `SETUP.md`. Work in my language and install anything that is missing yourself (I will approve the steps). What I want to build is the following: *<your idea: what, for whom, what "done" looks like – a few sentences>*

5. **Answer the questions** (technology, which agents you use, GitHub yes/no). The agent checks which tools are missing (Git, Node.js, Backlog.md) and installs them for you; you approve each step in the app (if you decline, it gives you manual instructions instead). The installer may ask for your computer password. If an installer asks for your computer password, type it yourself, never into the chat. On Windows the helper scripts need Git for Windows (includes *Git Bash*); the agent will guide you.
6. **At the end** the agent summarizes what exists and which task comes first. Tell it to start.

**Security note:** download STEM only from the official repository (link above). STEM contains a small start hook (`scripts/session-start.sh`, configured in `.claude/settings.json`); when your app asks whether to trust the folder, read that prompt. STEM blocks `.env` files and common API-token formats from being committed (no guarantee for other formats), but never paste passwords into the chat.

## For technical users: via GitHub

- Click **Use this template** on the GitHub page (creates your own repository), clone it, open it in your agent, then give the prompt from step 4. Or: `git clone` this repository and remove the `.git` folder to start with a fresh history.
- Already have `git`, `node` and `backlog` installed? The agent will detect that and skip the installation steps.
- Improvements and validated learnings are welcome as pull requests (see `promote-learning` skill).

## What you get

- Git, Backlog.md, a vision document, milestones (vertical slice → MVP → moonshot) and the first 3–7 tasks derived from your goal. The agent will ask you what you imagine for each of the three.
- Short agent rules (`AGENTS.md`) that load further rules only when needed – designed to keep the agent's context small.
- `scripts/run.sh` keeps long test/CI output out of the context; `scripts/session-start.sh` gives a compact status at session start.
- Skills for recurring work: `retro`, `handoff`, `promote-learning`, `testing-practices`, `stem-update`.

## Working day to day

- The agent explains what it does and why, summarizes each step and gives you a direct link whenever you should test or decide something. Say "answer more briefly" at any time; the first retro asks whether the amount was right.
- If several related tasks are ready, the agent offers to work through them as a batch; you approve once.
- Work is backlog-driven: every change is a task with acceptance criteria. View it with `backlog board` or `backlog browser`.
- When the agent reports a newer STEM version at session start, you can let the `stem-update` skill bring your project up to date (your approval is required).
- When a milestone has no tasks left, the agent proposes the next ones; you decide.
- When the agent says the context is large, it has written the handoff; open a new session and say "continue with the handoff" (the new session starts informed). Optional: a status line can show the context usage in Claude Code (see its docs).
- End a session with the `handoff` skill; the next session starts from `docs/agent/HANDOFF.md`.
- After the first milestone, run a retro (`retro` skill). It also reviews the harness itself, including everything collected for it in `docs/agent/NEXT_RETRO.md`.
- Never put secrets into the repository.

## Trying STEM on a real project: what to watch

- Did the agent read only `AGENTS.md` at the start instead of everything?
- Are `backlog/` and the first tasks there, and is `AGENTS.md` still intact?
- Does verification run through `scripts/run.sh`?
- Is `Setup status: DONE` set in `AGENTS.md` and everything committed?
- Does a second session continue via `scripts/session-start.sh` without re-asking?
- Note stumbling blocks or unclear points (or let the agent record them as `Learning:`). They are the input for the first retro.

## Language

These files are for humans (English and German). Instructions for agents are in English, but agents talk to you in your language.
