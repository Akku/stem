<div align="center">

<img src="docs/assets/stem-header.jpg" alt="STEM" width="960">

**An Agile Agentic Coding Harness**

**Version 1.14.0** · ![License](https://img.shields.io/badge/license-MIT-green) ![Claude Code](https://img.shields.io/badge/Claude%20Code-tested-green) ![Codex](https://img.shields.io/badge/Codex-tested-green)

[🇩🇪 Deutsch](README.de.md) · [Why STEM](#why-stem) · [Is STEM for you?](#is-stem-for-you) · [Get started](#get-started) · [Contents](#contents)

</div>

STEM is a template harness to kickstart your project. It sits on top of the coding agent you already use (preferably Claude Code).

## Why STEM

**Humor-warning:** The name STEM is derived from the AI in the movie 'Upgrade (2018)'.

| Assumption | What STEM provides |
| --- | --- |
| People are bad at specifying requirements, and an agent fills the gaps with guesses. All too human. | **Alignment:** [Backlog.md](https://github.com/MrLesk/Backlog.md) holds vision, milestones and tasks. The SETUP helps install it, and the `alignment` skill interviews you to not efficiently creates the wrong result. |
| Automation is more reliable than an agent interpreting prose rules. | **Determinism first:** scripts and hooks do what can be automated (session start, large-read minimization, logs only read punctually, etc.). Each rule lives in one place, so less interpretation by the LLM. |
| You know what you want to do now, but when you see the results, requirements always change. Right? | **Thin slices:** milestones (vertical slice, MVP, 1.0, ...); small tasks with acceptance criteria actually checked; batches of work get suggested to you. |
| Quality drops, mood drops, mistakes eat more tokens when the context grows. | **Small sessions:** rules load only on demand, long logs/files are only grepped / peeked and stay out of the context. When context hits hard, the `handoff` skill is automatically recommended. Like any good AI would. |
| Small sessions need to carry state over. Session compacting is lossy, makes full re-reads necessary. | **Continuity:** state only lives in files: backlog tasks, decisions, and short handoff notes. New sessions auto-generate after `handoff` and read state from well-organized files. |
| Agents do suggestions, but direction-decisions are still the human's. So the human needs all support it can get. | **Human work matters:** plain-language reports after each phase, questions with options and a recommendation, a direct link or command for everything you should check or decide. You stay in control. |
| An agent reports "done". But it's not. Better safe than sorry. | **Traceability:** every change is a task with a plan, acceptance criteria and recorded evidence; unproven criteria stay open. |
| The agent hates reflection if not prompted to. Do you? | **Continuous learning:** the harness evolves by suggesting the `retro` skill regularly, to reflect on stored questions using an indepentent reviewer and logged measures, problems and your input. You can even use `promote-learning` to improve this harness for everyone else. |

Docs for humans are English/German, agent instructions are English, and the agent talks to you in your language.

## Is STEM for you?

STEM is built for one person working with Claude Code on a project that spans many sessions, from medium size upwards. For small tasks and one-off scripts the workflow costs more than it brings: use the plain agent ([STEM or the plain agent?](#stem-or-the-plain-agent)). Teams with their own process, CI and review are not a fit.

<p align="center"><code>[ You ]──▶[ STEM ]──▶[ More YOU ]</code></p>

## Get started

1. [Download the ZIP](https://github.com/Akku/stem/archive/refs/heads/main.zip) and unzip it. Keep the whole folder, including hidden files.
2. Open that folder in your coding agent (for example the Claude desktop app, Code tab).
3. Paste this prompt, replacing the placeholder with your idea:

```text
Set up this project: follow SETUP.md. Work in my language and install anything that is missing yourself (I will approve the steps).

What I want to build is the following:
<your idea: what, for whom, what "done" looks like – a few sentences>
```

Answer the agent's questions and approve installation steps as needed. It sets up the tools, vision, milestones and first tasks with you. Never type passwords / secrets into a chat.

**Technical users:** click **Use this template** on GitHub, or clone the repository, then use the same prompt. [Detailed setup guide](START_HERE.md) for more help.

<details>
<summary>Agent and platform test status</summary>

Claude Code is tested in real use. Codex is tested by an automated probe run (fresh setup, native skill listing, alignment interview, one task to Done) and in an existing project with documented workarounds; project hooks, the Codex UI, Codex Cloud and long-context behaviour are not covered. See [Codex mechanics](docs/agent/CODEX.md) for prerequisites, session start, sandbox access and the context-warning fallback.

macOS is tested; Windows is prepared but not yet tested.

</details>

See the [results page](docs/RESULTS.md) for three curves from using STEM on itself (dogfooding data, not a benchmark).

## Staying up to date

At the start of each session the agent checks (once per day) whether a newer STEM version exists and tells you. With your approval the `stem-update` skill reads the [changelog](CHANGELOG.md), picks what helps your project and merges it without overwriting your project-specific content. The `retro` skill checks STEM as well.

STEM releases use `MAJOR.MINOR.PATCH` version numbers; renames and removals come with migration notes in the changelog. Your project gets its own version, starting at 0.1.0, independent of the STEM version in `STEM_VERSION`: after a finished work package the agent proposes a patch, minor or major bump and applies it only with your approval.

## STEM or the plain agent?

Coding agents such as Claude Code or Codex work well on their own. STEM adds a workflow around them, and that workflow costs extra steps. A rough guide:

| Your situation | Plain agent | With STEM |
| --- | --- | --- |
| One-off script or quick prototype | Usually enough | Setup and task steps cost more than they bring |
| A project over many sessions | You re-explain the state or keep your own notes | Handoff note and state summary, read automatically in the next session |
| You have no technical background | You install and configure the tools yourself | The agent installs and explains the tools; one approval per installation step |
| You want to see what the agent did and whether it is done | You read the chat and the changes | A task with acceptance criteria and evidence; one check per task |
| You want your setup to improve over time | Changes happen ad hoc | Retros turn friction into rule changes; a retro every few tasks |
| A team with its own process, CI and review | The agent fits into your process | STEM's process would duplicate yours; not a fit |

Tested agents and platforms: see *Agent and platform test status* under [Get started](#get-started).

**Other approaches.** Several open-source projects add structure to coding agents too; strengths overlap.

- **Spec-first toolkits** (for example [Spec Kit](https://github.com/github/spec-kit), [OpenSpec](https://github.com/Fission-AI/OpenSpec)): strong at turning each change into an agreed spec, plan and tasks before code is written. STEM sharpens the idea once at setup and focuses on the project-wide loop of backlog, handoff and retro.
- **Skill libraries** (for example [Superpowers](https://github.com/obra/superpowers)): strong at engineering discipline per piece of work, such as design, test-driven development, review and verification. STEM does not prescribe these engineering steps; its focus is continuity across sessions.
- **Role-based agile methods** (for example [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD)): strong at structured planning with role agents, a backlog and retrospectives; the closest to STEM. STEM is smaller and aims its guided setup at people without a technical background.

Based on each project's own documentation as of November 2026; these projects change quickly.

## Contents

<details>
<summary>Show all files</summary>

| File | Purpose |
| --- | --- |
| `START_HERE.md` / `STARTE_HIER.md` | Human guide (EN/DE) |
| `SETUP.md` | One-time setup procedure for the agent (deleted after setup) |
| `AGENTS.md` | Shared core rules (Codex and compatible tools) |
| `CLAUDE.md` | Thin adapter pointing to `AGENTS.md` |
| `.claude/skills/` | Skills: `retro`, `alignment`, `handoff`, `promote-learning`, `stem-update`; optional module (chosen in setup): `market-analysis` |
| `.agents/skills` | Link to `.claude/skills/` for shared Codex skill sources; Codex lists these skills natively (automated probe) |
| `.claude/agents/` | Agents: `ux-designer` (optional module, for projects with a UI) |
| `scripts/githooks/pre-commit` | Guard against committing confidential source documents and common secrets (activated during setup) |
| `STEM_VERSION`, `CHANGELOG.md` | STEM version this project is based on; what changed per version |
| `.claude/settings.json` | Claude Code: safe commands pre-approved, session-start hook |
| `LICENSE` | MIT (STEM); `.github/stem-check.py` + workflow check STEM itself |
| `scripts/check-backlog.sh`, `scripts/retro-metrics.sh`, `scripts/promote-check.sh` | Backlog consistency check (also in the pre-commit hook); measured evidence for retros; learnings ready to share with STEM |
| `docs/agent/stacks/` | Stack-specific notes, loaded only when the stack applies |
| `scripts/context-report.py` | Optional retro tool (Claude Code): where the context went, longest sessions; numbers only |
| `scripts/context-check.py` | Claude Code hook: warns when the context is large and a new session is due |
| `scripts/run.sh` | Compact output for tests/CI/CLI (exit code preserved, full log in git-ignored `.agent-logs/`, `evidence:` pointer for task notes; uncited logs older than 30 days are pruned) |
| `scripts/session-start.sh` | Session start summary (branch, changes, tasks, handoff); changes no project files, `STEM_OFFLINE=1` for no network |
| `docs/agent/OPERATING_MODEL.md` | Rules with stable IDs (`R-*`), loaded selectively |
| `docs/agent/ADVANCED.md` | Rarely needed rules (parallelism, measurement, routing, local models) |
| `docs/agent/EXPERIMENTS.md` | Hypotheses, metrics, baselines and evidence grades for cost-carrying rules |
| `docs/agent/NEXT_RETRO.md` | Everything the next retro needs in one place: due checks, observations, first-retro items |
| `docs/agent/PITFALLS.md` | Growing list of technical pitfalls |
| `docs/agent/PROCESS_IMPROVEMENTS.md` | Retro handling and feeding learnings back into STEM |

</details>

## Contributing

Please contribute proven learnings via pull request (pattern: problem, pattern, applicability, evidence – see `docs/agent/PROCESS_IMPROVEMENTS.md` or the `promote-learning` skill). No project or company internals, no credentials – this repository is public. Details and checklist: [CONTRIBUTING.md](CONTRIBUTING.md).
