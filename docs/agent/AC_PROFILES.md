# Acceptance-criteria (AC) profiles

Read only when the retro topic `ac-profile` is given, or to check what the project's `**AC profile:**` line in `AGENTS.md` means. A profile sets the level of detail and proof, never a fixed number of ACs: the count follows the task. It applies to **new** tasks; existing tasks are not rewritten.

| Profile | How many ACs | What an AC covers | Evidence | Typical project |
| --- | --- | --- | --- | --- |
| light | as few as the task allows; only what the user needs to see | the result the user can see or use; no edge cases | E1 is enough, the user may check by hand | private, hobby, prototype, learning |
| standard | enough to cover the result and the main error or boundary case; depends on the task | result plus the main error or boundary case; each AC checkable by a command or a short look | E2 where code runs, E1 for docs and design | team or product work, default |
| strict | as many as the requirements need: every required behaviour traceable to an AC | each behaviour, error and edge case, relevant non-functional limits (performance, data, security) | E2 for every code AC with a reproducible pointer; open if not proven | scientific, regulated, safety-relevant, libraries others depend on |

## Retro procedure
1. Recommend a profile from what you know (vision doc, user statements, kind of project) and say why in one sentence. Private or exploratory: light. Scientific or regulated: strict. Unsure: standard.
2. Take the next real To Do task and show its ACs written in all three profiles (short, side by side). Do not create or change tasks for this.
3. Ask the user as plain text (a/b/c, recommendation first); "other" is allowed (the user may describe their own).
4. Record: set the `**AC profile:**` line in `AGENTS.md` to `light|standard|strict` (drop the comment), note the choice and reason in the retro notes. From then on new tasks follow it (`R-LIFECYCLE`: ACs are written at task creation). A later change of mind is a normal edit of that line.
