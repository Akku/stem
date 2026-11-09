---
name: handoff
description: End-of-session command ("Handoff" instead of "commit"): put notes into the tasks, commit what is not work in progress, record open user questions as drafts and leave only a pointer in docs/agent/HANDOFF.md, or write no handoff when nothing is open. Use when ending a session, at a task or milestone boundary, when a context notice reports a large context (threshold in `R-BATCHING`), or before switching agents.
---

# Handoff / session end

Rules: `R-STATE`, `R-STATE-COHERENCE`. The handoff holds only what git and the backlog cannot tell the next session: what waits for the user. Branch, commits, active and ready tasks, `RETRO DUE` and versions come from the session-start script and never go into it.

## 1. Notes into the tasks
Each unfinished task gets a concrete continuation point in its notes (open criterion, next action as `Next:`), hard-won context (ruled-out hypotheses), evidence with the SHA it verified (`R-STATE-COHERENCE`), and `Learning:` only if a detour happened (`R-LEARNING`).

## 2. Commit what is not work in progress
Explicit paths, code together with its task changes (`R-STATE-COHERENCE`). Half-finished work stays out of `main`: a task note, or a WIP branch. Task work keeps `TASK-<n>: <summary>`; a commit of only notes, drafts or the handoff is titled `Handoff <YYYY-MM-DD>: <content>` (the `commit-msg` hook accepts it).

## 3. Check
`git status --porcelain` clean (WIP named), no open user question or approval from this session. Unpushed commits are not open: they are in git; step 5 pushes them.
- **Something open → step 4.**
- **Nothing open → write no handoff.** Delete an existing `docs/agent/HANDOFF.md`, commit that, go to step 5. (Session start hides a handoff once a later commit exists, but the file stays until deleted.)

## 4. Open question: draft plus pointer
Record each open question or decision in a draft task with the options verbatim; it carries no overhead (no DoD, label, milestone or acceptance criteria):
```
backlog task create "Decide: <topic>" --draft --no-dod-defaults -d "Question to the user (<date>): <question>. Options: a) ... (recommended) b) ... c) ..."
```
The description must start with `Question to the user`: session start lists such drafts under "open questions". A question asked in chat is recorded the same way at once, not only at session end.
Then rewrite `docs/agent/HANDOFF.md` from scratch (max 1 KB, drop empty lines):
```
# Handoff
**Open for the user:** <DRAFT-n: one-line question>; <pending approval, e.g. a release>
**After the answer:** <one concrete action, with file or command>
```
Commit the handoff last (a later commit marks it consumed). The session that settles the question deletes the handoff, and the draft (or promotes it to a task), in the same commit.

## 5. Push, then start the fresh session
**Push** (`git push`, normal fast-forward only) finished commits automatically, without asking. Skip the push silently, and propose it with the reason in the final message, if you judge the unpushed commits may be unwanted (WIP, experimental, unreviewed, sensitive content, a branch the user did not intend to publish). Never force push; tags and releases stay a separate decision. Never put the push into the handoff file.

**Start the fresh session** per `R-BATCHING` "A handoff always opens a fresh session": `start_session` with context `fresh`, then `detach_session` on it; the brief says not to report back, then continues the approved batch or unfinished task (per `docs/agent/HANDOFF.md` / task notes), or tells the new session to run session start and propose the next steps. Do not mention the handoff or ask to read it: session start loads it automatically. Then end with one line (handed off to <link>, open: ...) and stop. If no tool can start a session, end with one ready-to-paste prompt instead.

## 6. Optional: hand over to a larger model (an offer, never automatic)
Offer it instead of the plain fresh session of step 5 when the next unit of work (the task, batch or milestone the user names) is complex: always when the user asks for it; on your own when a guardrail hits (label `size-L`; a change over about 10 files or at an interface or module boundary; repeated failure in this session, `R-AUTONOMY`; the goal is a whole milestone) or you can name another concrete reason. Name the reason. Larger only: smaller models for mechanical pieces are subagents (`R-ROUTING`), a new session would reload the whole start context.

Ask once, as plain text with options and a recommendation: (a) larger model, autonomy profile, permission mode `auto`; (b) the same with `bypassPermissions` (no tool prompts, the risk is the user's); (c) the normal handoff of step 5. Name the model and effort you propose (effort `high` unless the task warrants more); take the model id from the app's model list, never from this file. The "autonomy profile" is the second bullet of the mission brief below.

On (a) or (b): `start_session` with context `fresh`, `use_worktree: true` (own branch in the project where the work happens; another repo the task touches gets its own branch too), then `detach_session` as in step 5. The starter cannot start a higher model or mode, so the brief is exactly: "Run session start, answer 'ready' and do nothing else until the next message. Never message the starting session."; then raise with `set_session_model`, `set_session_effort`, `set_session_permission_mode` (each shows the user an approval card; if one is declined or unavailable, say so and fall back to (c)), then send the mission with `SendMessage`. Mission brief:
- Goal: <task, batch or milestone as the user phrased it>; continue per the task notes (and `docs/agent/HANDOFF.md` if it exists); name where earlier attempts and ruled-out ideas are recorded.
- Autonomy profile for this session only (write it nowhere else, not into `AGENTS.md`, rules or memory): decide yourself instead of asking; record each assumption in the task notes as `Assumption: ...`; stop and ask only on an `R-AUTONOMY` condition (repeated failure, missing product decision, ambiguous destructive action).
- Work and commit only on the session's own branch; never push, merge into `main`, tag or release.
- Finish: results and evidence into the task notes, no further sessions, never report back; then ask the user ONE question in this session: merge, open a pull request or discard the branch, with a three-line summary.

If a step did not fit or you deviated from it: `Learning: skill handoff: <what> -> <change>` in the task notes (`R-LEARNING`).
