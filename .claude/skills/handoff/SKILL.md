---
name: handoff
description: Rewrite docs/agent/HANDOFF.md from scratch so the next session can continue without replaying history, then run the end-of-session checklist. Use when ending a session, at a task or milestone boundary, when a context notice reports a large context (threshold in `R-BATCHING`), or before switching agents.
---

# Handoff / session end

Rules: `R-STATE`, `R-BOOTSTRAP`, `R-STATE-COHERENCE`. The handoff holds only what git and the backlog cannot tell the next session; the session-start script already prints branch, commits, active and ready tasks.

## 0. Skip check (`R-BATCHING` "Skip the handoff")
Determine yourself what is not yet in git or the backlog: `git status --porcelain`, unpushed commits (`git log @{u}..` if an upstream exists), open approvals or proposals from this session, evidence only in chat, notes written nowhere else. Turn every pending decision into a draft task and every uncommitted change into a commit first. If nothing is left: do not write the handoff; delete a stale `docs/agent/HANDOFF.md` and commit that, skip to step 4 and give only the ready prompt. Otherwise tell the user in one line what forces the handoff.

## 1. Write `docs/agent/HANDOFF.md`
Always rewrite the whole file, never append or "refresh" (`Earlier:` sections are how it bloats). Max 2 KB / 40 lines; the session-start script warns above that. Use these headings, drop empty ones:

```
# Handoff
**State:** <date>, stem <version from STEM_VERSION>, <branch> @ <commit SHA>; <what is true in one or two sentences>
**Approvals:** <what the user allowed, date>; <scope, batch, release>
**Next step:** <one concrete action, with the file/command to start>
**Evidence open:** <what was verified at which SHA; what is still missing, e.g. manual check>
**Blockers / decisions:** <what waits for the user; point to the task notes holding the options>
**Notes:** <max 3 lines: facts the next run needs that are written nowhere else; re-justify each one at every rewrite, else drop>
```

Per line test: does git or the backlog already show it (finished tasks, active task, commit messages)? Then delete it. Durable knowledge goes to `docs/` or `PITFALLS.md`, not into Notes, history stays in tasks and commits.

## 2. Check before saving
Sections agree with each other, approvals are still valid, evidence names the SHA it verified (`R-STATE-COHERENCE`).

## 3. Session-end checklist
1. `git status`: nothing unrelated, nothing forgotten. Commit code together with its task changes and the handoff, or state why not.
2. Unfinished tasks: each has a concrete continuation point in its notes (open criterion, next action), not "still to check".
3. Pending user decision: write the question and every option (a/b/c) verbatim into the task notes, and point to the task from `Blockers / decisions`. "User decides X" alone is not enough; the next session must not search the transcript for the wording.
4. Notable detours or high context cost: add `Learning:` to the task (only if it happened).

## 4. Suggest the next prompt
End your final message with one ready-to-paste prompt for the next session (the concrete next task or action). A session you start yourself gets the brief of `R-BATCHING` "Hand-off inside an approved batch" including its leading detach-self sentence. Do not mention the handoff or ask to read it: session start loads it automatically. Inside an approved batch above the context threshold, start the fresh session yourself instead (`R-BATCHING` "Hand-off inside an approved batch").

If a step did not fit or you deviated from it: `Learning: skill handoff: <what> -> <change>` in the task notes (`R-LEARNING`).
