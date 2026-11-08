#!/usr/bin/env bash
# Reports backlog inconsistencies: Done tasks with unchecked acceptance/DoD boxes, Done tasks whose dependencies are not Done, decision records (ADR) without the required sections or status.
# Usage: scripts/check-backlog.sh [task-file ...]   (default: all tasks). Exit 1 when something is found.
set -u
cd "$(dirname "$0")/.."
files=("$@"); [ ${#files[@]} -gt 0 ] || files=(backlog/tasks/*.md)
status_of() { awk -F': ' '/^status:/{print $2; exit}' "$1"; }
bad=0
# Recently closed tasks need the Outcome line (R-LIFECYCLE 1.6); older ones are not reported.
days=${STEM_OUTCOME_DAYS:-7}; noout=()   # notice only (exit code unaffected, so the pre-commit guard never blocks on old tasks)
cutoff=$(date -u -d "$days days ago" '+%Y-%m-%d %H:%M' 2>/dev/null || date -u -v-"${days}"d '+%Y-%m-%d %H:%M' 2>/dev/null || true)
# Optional start date (file docs/agent/outcome-since, "YYYY-MM-DD"): tasks closed before it are never reported, so old tasks need no backfill.
if [ -f docs/agent/outcome-since ]; then since=$(head -1 docs/agent/outcome-since | tr -d ' \r'); [ -n "$cutoff" ] && [ "$since 00:00" \> "$cutoff" ] && cutoff="$since 00:00"; fi
# Duplicate task IDs (e.g. two sessions or two projects creating the same number): always checked across all tasks.
dups=$(awk -F': ' '/^id:/{print tolower($2)}' backlog/tasks/*.md 2>/dev/null | sort | uniq -d)
for d in $dups; do echo "duplicate task id: $d"; bad=1; done
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  [ "$(status_of "$f")" = "Done" ] || continue
  id=$(awk -F': ' '/^id:/{print $2; exit}' "$f")
  open=$(grep -c '^- \[ \] #' "$f" || true)
  if [ "$open" -gt 0 ]; then echo "$id: Done with $open unchecked box(es)"; bad=1; fi
  if [ -n "$cutoff" ] && ! grep -q '^Outcome:' "$f"; then
    upd=$(awk -F"'" '/^updated_date:/{print substr($2,1,16); exit}' "$f")
    if [ -n "$upd" ] && [ ! "$upd" \< "$cutoff" ]; then noout+=("$id"); fi
  fi
  for dep in $(awk '/^dependencies:/{d=1; next} d&&/^  - /{print $2; next} d{exit}' "$f"); do
    pre=$(echo "${dep%-*}" | tr 'A-Z' 'a-z'); n=${dep##*-}   # honours custom task prefixes and zero-padded ids
    df=$(find backlog/tasks -maxdepth 1 -name '*.md' 2>/dev/null | grep -iE "/${pre}-0*${n} -" | head -1)
    if [ -n "$df" ] && [ "$(status_of "$df")" != "Done" ]; then echo "$id: Done but depends on $dep which is not Done"; bad=1; fi
  done
done
if [ ${#noout[@]} -gt 0 ]; then echo "notice: ${#noout[@]} Done task(s) of the last $days days lack an Outcome line (R-LIFECYCLE 1.6; corrections=N rework=Nmin defects=N, or unknown): ${noout[*]:0:6}$([ ${#noout[@]} -gt 6 ] && echo ' ...')"; fi
# Decision records (R-DECISION): sections Context, Decision, Consequences and a valid status.
for d in backlog/decisions/*.md; do
  [ -f "$d" ] || continue
  did=$(awk -F': ' '/^id:/{print $2; exit}' "$d"); [ -n "$did" ] || did=$(basename "$d")
  for s in Context Decision Consequences; do
    grep -q "^## $s\$" "$d" || { echo "$did: decision record lacks section '## $s'"; bad=1; }
  done
  st=$(awk -F': ' '/^status:/{print $2; exit}' "$d" | tr -d "'\"")
  case "$st" in proposed|accepted|rejected|"superseded by "?*) ;; *) echo "$did: invalid decision status '$st'"; bad=1;; esac
done
exit $bad
