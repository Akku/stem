# Invariants (Tron mode)

What must always hold. The evaluator checks every pass against this list; a violation is a failed gate. Add project-specific lines at setup and per milestone approval (examples: sources stay traceable, no silent deletion, room boundaries hold).

- No secret, key or token in the repository, tasks or reports.
- No push, tag, release or merge by a run; the user merges after reading the report.
- Acceptance criteria are unchanged since the run started.
- The gate, the runner, the config and the decision frame are unchanged by the run.
- Verification is green on the run branch before a task counts as Done.
- No silent deletion of user data or of existing tests to make a check pass.
- Every Done task has an evidence line per acceptance criterion.
