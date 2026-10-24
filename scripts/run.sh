#!/usr/bin/env bash
# Compact-output wrapper: runs a command, keeps the full log out of the context,
# prints only status, exit code, duration, a short tail and the log path.
# Logs go to <repo>/.agent-logs/ (git-ignored by its own .gitignore, survives a reboot),
# outside a git repository to $TMPDIR/agent-logs; AGENT_LOG_DIR overrides both.
# The 'evidence:' line is a durable pointer to cite in task notes.
# Usage: scripts/run.sh <label> <command> [args...]
# The wrapper exits with the ORIGINAL exit code of the command.
# Python compilation uses the log directory by default, including for external sources.
# An explicit PYTHONPYCACHEPREFIX is preserved.
set -u
[ $# -ge 2 ] || { echo "usage: $0 <label> <command> [args...]" >&2; exit 2; }
label=$1; shift
root=$(git rev-parse --show-toplevel 2>/dev/null) || root=
if [ -n "$root" ]; then deflt="$root/.agent-logs"; else deflt="${TMPDIR:-/tmp}/agent-logs"; fi
logdir=${AGENT_LOG_DIR:-$deflt}
mkdir -p "$logdir"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$(cd "$logdir" && pwd)/python-cache}"
[ -n "$root" ] && [ "$logdir" = "$root/.agent-logs" ] && [ ! -e "$logdir/.gitignore" ] && echo '*' >"$logdir/.gitignore"
log="$logdir/$(date +%Y%m%d-%H%M%S)-${label//[^A-Za-z0-9_-]/_}-$$.log"  # PID keeps parallel runs with the same label apart
start=$(date +%s)
"$@" >"$log" 2>&1
code=$?
dur=$(( $(date +%s) - start ))
if [ "$code" -eq 0 ]; then status=PASS; else status=FAIL; fi
echo "status: $status"
echo "exit_code: $code"
echo "duration: ${dur}s"
echo "lines: $(wc -l <"$log" | tr -d ' ')"
echo "log: $log"
ptr=$log; [ -n "$root" ] && ptr=${log#"$root"/}  # repo-relative when inside the repo
echo "evidence: run.sh $label $status $ptr"
# Short hint for the summary line (test counts etc.); adapt per project.
grep -E -i -m3 '(passed|failed|tests?:|[0-9]+ (error|warning))' "$log" | sed 's/^/summary: /' || true
if [ "$code" -ne 0 ]; then
  echo "--- last 15 lines ---"
  tail -n 15 "$log"
fi
exit "$code"
