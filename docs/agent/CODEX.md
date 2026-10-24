# Codex mechanics

Read `AGENTS.md` first; shared rules remain in `OPERATING_MODEL.md` under their rule IDs. These notes describe Codex-specific mechanics, not another set of project rules. Claude Code keeps its existing settings, hooks and skill sources.

## Prerequisites and session start

Provide Git, Bash and the project's Backlog.md CLI on the command PATH; Node.js and npm are needed to install Backlog.md. Python 3 is needed for STEM maintenance checks and optional Python scripts. Availability in a setup shell does not prove availability in a fresh task. Start the Codex task in the project checkout so its instructions and `.agents/skills` can be discovered there.

For a new project, use the guided start in `START_HERE.md`. When maintaining the STEM template itself, leave its `Setup status: TODO` and `SETUP.md` intact; they are shipped project-setup instructions.

Claude's `.claude/settings.json` hooks and permissions are not imported into Codex. When no session-start output was injected, run once from the project root:

```bash
STEM_OFFLINE=1 scripts/session-start.sh
backlog instructions overview
```

`STEM_OFFLINE=1` suppresses the optional session-start network queries; omit it when those queries are wanted. It does not restrict other commands. Session start reports state; it does not install missing tools or repair the environment.

## Skills and context

`.agents/skills` links to the same sources in `.claude/skills`. A readable `SKILL.md` proves file access only. To claim native skill discovery, observe the project's skill in Codex's native skill listing and, where supported, invoke it by name. Fresh-project setup and native discovery are not established by the existing-project workflow probe. A later shell `cd` does not prove the task's startup skill catalog was refreshed.

No Claude `UserPromptSubmit` context-warning hook is assumed to run in Codex. Follow `R-BATCHING` and its proxy fallback when no native context-size signal is available. Do not invent a token count or treat the session-start handoff-size warning as a context-window warning. Long-context behavior remains a separate test.

## Sandbox access and external checks

Check which directories the current task can write. Product checkouts outside that boundary, their Git metadata and commits may need scoped approval; a sibling checkout inside the writable workspace may already be authorized. Request only the filesystem/network access needed for the operation, using the runtime's approval mechanism. Claude's allow-list does not authorize Codex actions. Preserve the sandbox; follow `R-AUTONOMY` for missing decisions or repeated failures and `R-STATE-COHERENCE` for commits.

From a writable working project, a maintainer can check an external STEM checkout with:

```bash
scripts/run.sh stem-check python3 /absolute/path/to/stem/.github/stem-check.py
```

Replace the example path with the actual readable checkout. `run.sh` defaults Python bytecode caches to its own writable log directory, including explicit `py_compile` calls. An existing `PYTHONPYCACHEPREFIX` override is preserved; ensure it is writable. This avoids requiring product write access solely for checker bytecode. Other tools or application files may still require write access; the wrapper does not grant it. See `R-CONTEXT-OUTPUT` and `R-VERIFY` for output and proof boundaries.

## Evidence boundary

The Codex probe exercised a task lifecycle in an existing project with documented workarounds. It does not prove fresh-project setup, native project-skill invocation, long-context recovery or every stop condition. Cloud tool activation and saved-environment persistence also need a fresh-task check. Copilot remains an untested adapter. Do not infer these capabilities from a green product checker.
