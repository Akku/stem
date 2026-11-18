# Retro questions (extra topics)

Besides measured data, task learnings and your own input, each retro gets a few **reflection questions** from a prepared catalog. They make sure that questions nobody would think of in the moment (rules, skills, context cost, new agent features) come up regularly.

- **Catalog:** `docs/agent/retro-topics.json` (owned by STEM, replaced on update).
- **Your own questions or changes:** `docs/agent/retro-topics.local.json`. Same `id` replaces a STEM topic, `"disabled": true` removes it.
- **State:** `docs/agent/retro-topics-state.json` (which topic was asked when; commit it with the retro notes).
- **Picker:** `python3 scripts/retro-topics.py` (called by the `retro` skill; `--dry-run` shows the result without recording it).

## How topics are picked

1. Topics whose **trigger** is due or whose **signal** fired come first, strongest first (at most 2).
2. Remaining slots (up to 2) are filled with `once` topics never asked, then `repeatable` topics asked longest ago.
3. A topic asked in the previous retro is skipped for signals for 3 retros, so one lasting signal does not repeat every time.
4. Each picked topic ends as a decision, a task, or a dropped item with a reason.

## The questions

| Id | Question the retro asks | Signal (when it is pushed) |
|---|---|---|
| `process` | Which process steps cost more than they return? Name one to simplify, automate or drop. | 15 Done tasks since last asked |
| `skills` | Which skills were used, which never? Which step was skipped or too long? Does a known skill collection offer a better one? | 30 days |
| `duplicates` | Which facts are stored in more than one file? Pick one authoritative place; remove or point the others. | `AGENTS.md` above 90 % of its size limit |
| `git-state` | What is uncommitted or unpushed and why? What should change in the git workflow? | 3 or more uncommitted files plus unpushed commits |
| `open-tasks` | Which To Do tasks are obsolete, duplicate or too vague? Keep only what can start soon. | 20 or more To Do tasks |
| `in-progress` | Why does each In Progress task stay open? Finish, split, park or drop it. | 5 or more In Progress tasks |
| `ac-profile` | Which acceptance-criteria profile (light / standard / strict) fits this project? See `docs/agent/AC_PROFILES.md`. | once per project |
| `vision` | Is there a current vision? Do the milestones still describe the next steps and have ready tasks? | vision older than 60 days, or a milestone without To Do tasks |
| `llm-structure` | Where did an agent load too much, miss a rule or search too long? Which file should be split, indexed or shortened? | key instruction files grew 20 % |
| `harness-features` | Which new hooks, settings or skill features of Claude Code or Codex could replace a written rule with a machine check? | CLI version changed, or 30 days |
| `determinism` | Which rules were skipped or depend on judgment although a script, hook or test could enforce them? | 2 Learning notes about skipped rules, or 45 days |

The authoritative wording and thresholds are in the catalog; each topic also carries a `why` explaining its threshold. If this table and the catalog disagree, the catalog wins.
