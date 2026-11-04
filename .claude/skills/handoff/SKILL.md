---
name: handoff
description: End-of-session command ("Handoff" instead of "commit"): put notes into the tasks, commit what is not work in progress, record open user questions as drafts and leave only a pointer in docs/agent/HANDOFF.md, or write no handoff when nothing is open. Use when ending a session, at a task or milestone boundary, when a context notice reports a large context (threshold in `R-BATCHING`), or before switching agents.
---

# Handoff / session end

Rules: `R-STATE`, `R-BOOTSTRAP`, `R-STATE-COHERENCE`. The handoff holds only what git and the backlog cannot tell the next session: what waits for the user. Branch, commits, active and ready tasks, `RETRO DUE` and versions come from the session-start script and never go into it.

## 1. Notes into the tasks
Each unfinished task gets a concrete continuation point in its notes (open criterion, next action as `Next:`), hard-won context (ruled-out hypotheses), evidence with the SHA it verified (`R-STATE-COHERENCE`), and `Learning:` only if a detour happened (`R-LEARNING`).

## 2. Commit what is not work in progress
Explicit paths, code together with its task changes (`R-STATE-COHERENCE`). Half-finished work stays out of `main`: a task note, or a WIP branch.

## 3. Check
`git status --porcelain` clean (WIP named), unpushed commits (with an upstream: push if the user allowed pushing, else it is an open approval), no open user question or approval from this session.
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
**Open for the user:** <DRAFT-n: one-line question>; <pending approval, e.g. push or release>
**After the answer:** <one concrete action, with file or command>
```
Commit the handoff last (a later commit marks it consumed), push when an upstream exists and pushing is allowed. The session that settles the question deletes the handoff, and the draft (or promotes it to a task), in the same commit.

## 5. Suggest the next prompt
End your final message with one ready-to-paste prompt for the next session (the concrete next task or action). A session you start yourself gets the brief of `R-BATCHING` "Hand-off inside an approved batch" including its leading detach-self sentence. Do not mention the handoff or ask to read it: session start loads it automatically. Inside an approved batch above the context threshold, start the fresh session yourself instead (`R-BATCHING` "Hand-off inside an approved batch").

If a step did not fit or you deviated from it: `Learning: skill handoff: <what> -> <change>` in the task notes (`R-LEARNING`).
