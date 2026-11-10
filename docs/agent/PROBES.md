# Usage probes (design)

Read when an acceptance criterion (AC) can only be proven by real use of the finished work in a later session, or when session start reports `probes:`. Rule text: `R-LIFECYCLE` 1.5, `R-VERIFY`. Status: design (TASK-221); the script `scripts/probe.py` and the reports follow.

## Idea
Some ACs wait for usage ("the hook fires in a real session", "retro step X ran"). Today they stay open until the user checks by hand. A **probe** is one call in the built feature that appends a line to a log when the feature really runs. The task may go Done; the AC stays open with a marker; a later session finds the log line, adds the evidence and closes the AC.

## Marker
In the AC text of the task file, once at the end of the line:

```
- [ ] #3 Session start prints the report line in a real session [probe: TASK-221#3]
```

- Id = `<task id>#<ac number>` and must name the task and AC it stands on (checked).
- Only usage-like ACs may carry a marker: observable by a script, hook, skill step or command that runs in a real session. Wording, design, decision and look-and-feel approvals stay with the user; no marker there.
- Only the `Acceptance Criteria` section; never Definition of Done boxes.

## Probe call
One call in the feature code, at the place that proves the usage:

```
python3 scripts/probe.py fire TASK-221#3 --at scripts/session-start.sh:61
```

- `--at` is the source location of the call (file, optional `:line` or a name). One call per id.
- `fire` never fails the caller: any error is swallowed, exit 0.
- `fire` writes nothing when `STEM_TEST=1` or `CI` is set, so test runs never confirm. Nobody fires by hand.

## Log: `docs/agent/probes.jsonl`
Git-versioned, one JSON object per firing, append-only:

```
{"id":"TASK-221#3","ts":"2026-11-12T09:41:07Z","at":"scripts/session-start.sh:61"}
```

Exactly these three keys: no content, paths of user data, user or machine names (privacy). Several firings of one id are fine.

## States and who does what
- **open**: unchecked AC with marker, no log line for the id.
- **fired**: unchecked AC with marker and at least one log line = **confirmed** (a line exists, written by a run outside tests).
- **closed**: the agent checks the AC, writes `AC#n: E2 docs/agent/probes.jsonl <ts> <at>` as evidence, and in the same commit removes the marker and the probe call. Log lines stay until a retro prunes lines of ids that no longer exist.
- **orphan**: open for 10 sessions without a firing (session proxy: distinct commit dates after the commit that added the marker). The retro removes the probe call and marker, reports it to the user as dead or unreachable and leaves the AC open or rewrites it.

## Commands (scripts/probe.py)
- `fire <id> --at <loc>`: append a line (see above).
- `report`: one line for session start, `probes: N open, M fired (<ids>)`, nothing when there are none. A fired probe is the agent's cue to close it.
- `orphans`: the list the retro uses.

## Pre-commit allowance
`scripts/check-backlog.sh` does not count an unchecked AC as open when the task is Done and the AC line carries `[probe: <id>]` with the id matching that task and AC number **and** exactly one `probe.py fire <id>` call exists in tracked files (otherwise the AC could never close). A checked box that still has a marker is reported as a stale marker (notice). Every other unchecked box still blocks Done.

## Default profile
The light AC profile (`AC_PROFILES.md`) becomes a setup default only after evidence: harness-only opt-in first; a retro checks that at least 80 % of probes fired and none was confirmed falsely; a separate task then offers it.
