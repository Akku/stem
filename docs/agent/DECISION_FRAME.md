# Decision frame (Tron mode)

Default list; setup and each milestone approval adjust it. The runner and the agent never edit this file during a run.

## May decide alone (record `Assumption: ...` in the task notes)
- Naming, file layout and small refactors inside the task's files.
- Choice between equal options when either is easy to reverse.
- Wording of text, messages and comments.
- Test data and fixtures; helper code the task needs.
- Order of independent tasks, and an order that follows a dependency between tasks.
- Reuse of existing code instead of a second version.
- Splitting a task that is too large into smaller tasks inside the milestone (the ACs stay).
- Skipping tasks labelled `waiting` and tasks that wait for one.
- Additive data changes that delete and rewrite nothing (a new field, the old one kept).
- Additive, internal, backward-compatible interfaces (record `Decision: ...`, `R-DESIGN`).

## Must come back (draft question, task Blocked)
- Scope change: a task needs more or other than its acceptance criteria say.
- New running cost, paid service or new dependency with a licence or network need.
- New external recipient of data (upload, API, analytics, email).
- Data loss: deletion, overwrite or migration that cannot be undone.
- Architecture change; a breaking or public interface (contract others call); an ownership or permission model.
- Anything that touches an invariant (`INVARIANTS.md`).
- Release, tag, push, merge, publishing.
