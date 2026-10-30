#!/usr/bin/env bash
# Measured evidence for a retro (R-RETRO): cheap, repeatable numbers. Usage: scripts/retro-metrics.sh [since]  (YYYY-MM-DD or 'YYYY-MM-DD HH:MM' for a second retro on the same day; default: 14 days)
set -u
cd "$(dirname "$0")/.."
# --snapshot: also store the output as a dated baseline (docs/agent/baselines/) before changing a cost-carrying rule.
if [ "${1:-}" = "--snapshot" ]; then
  shift; mkdir -p docs/agent/baselines; out="docs/agent/baselines/$(date +%F).txt"
  n=2; while [ -e "$out" ]; do out="docs/agent/baselines/$(date +%F)-$n.txt"; n=$((n+1)); done  # never overwrite an earlier baseline
  "$0" "$@" | tee "$out"; echo "baseline saved: $out"; exit 0
fi
# --repo PATH (repeatable): also count commits of another repository (e.g. the product repo of a STEM project).
repos=()
while [ "${1:-}" = "--repo" ]; do repos+=("$2"); shift 2; done
since=${1:-$(date -v-14d +%Y-%m-%d 2>/dev/null || date -d '14 days ago' +%Y-%m-%d)}
case "$since" in *\ *) sincefull=$since ;; *) sincefull="$since 00:00" ;; esac   # all windows below use the same start time
echo "== retro metrics since $since =="
files=(backlog/tasks/*.md)
done_n=$(grep -l '^status: Done' "${files[@]}" | wc -l | tr -d ' ')
open_n=$(grep -L '^status: Done' "${files[@]}" | wc -l | tr -d ' ')
echo "tasks: $done_n done, $open_n open"
echo "backlog check (Done with unchecked boxes or open dependencies):"; scripts/check-backlog.sh | sed 's/^/  /'; [ "${PIPESTATUS[0]}" -eq 0 ] && echo "  none"
learn=$(grep -l 'Learning' "${files[@]}" | wc -l | tr -d ' ')
echo "tasks with a Learning note: $learn"
echo "retro-created tasks still open:"
for f in "${files[@]}"; do
  grep -q '^status: Done' "$f" && continue
  grep -qi 'retro' "$f" && echo "  $(awk -F': ' '/^id:/{print $2; exit}' "$f") $(awk '/^title:/{ if ($0 ~ />-$/) {getline; sub(/^ +/, ""); print; exit} sub(/^title: /, ""); print; exit}' "$f")"
done
commits=$(git log --since="$sincefull" --oneline | wc -l | tr -d ' ')
echo "commits: $commits"
read -r add del < <(git log --since="$sincefull" --numstat --format= | awk '{a+=$1; d+=$2} END{print a+0, d+0}')
share=0; [ "${add:-0}" -gt 0 ] && share=$(( 100*del/add ))
echo "lines added/deleted: ${add:-0} / ${del:-0} (deleted share $share %; high values right after features point to rework)"
echo "review/fix commits (message contains fix or review): $(git log --since="$sincefull" --oneline | grep -ciE 'fix|review')"
# Handoff overhead and untracked work: handoff commits and commits without a task ID (TASK-n / task n), per repository.
commit_stats() {  # $1 = repo path, $2 = label
  local all hand notask
  all=$(git -C "$1" log --since="$sincefull" --format=%s | wc -l | tr -d ' ')
  hand=$(git -C "$1" log --since="$sincefull" --format=%s | grep -ciE '^handoff|handoff update|; handoff' || true)
  notask=$(git -C "$1" log --since="$sincefull" --format=%s | grep -vciE 'task[- ]?[0-9]' || true)
  releases=$(git -C "$1" for-each-ref refs/tags --format='%(creatordate:format:%Y-%m-%d %H:%M)' | awk -v s="$sincefull" '$0 >= s' | wc -l | tr -d ' ')
  multi=0
  while IFS= read -r subj; do
    n=$(echo "$subj" | grep -oiE 'task[- ]?[0-9]+' | tr 'A-Z ' 'a-z-' | sort -u | wc -l)
    if [ "$n" -gt 1 ] || echo "$subj" | grep -qiE 'task[- ]?[0-9]+[/,+&][0-9]+'; then multi=$((multi+1)); fi
  done < <(git -C "$1" log --since="$sincefull" --format=%s)
  echo "$2: releases (tags) $releases, commits with several task IDs $multi"
  sync=$(git -C "$1" log --since="$sincefull" --format=%s | grep -ciE 'sync|update harness' || true)
  echo "$2: harness-product sync commits $sync ($([ "$all" -gt 0 ] && echo $((100*sync/all)) || echo 0) % of commits; high values mean changes exist twice)"
  echo "$2: $all commits, $hand handoff, $notask without task ID ($([ "$all" -gt 0 ] && echo $((100*notask/all)) || echo 0) %), fix/review $(git -C "$1" log --since="$sincefull" --format=%s | grep -ciE 'fix|review' || true)"
}
commit_stats . "this repo"
# Retro skill size (loaded when a retro runs) and growth since the start date.
rs=.claude/skills/retro/SKILL.md
if [ -f "$rs" ]; then
  now=$(wc -c < "$rs" | tr -d ' ')
  rev=$(git log --before="$sincefull" -1 --format=%H -- "$rs")
  if [ -n "$rev" ]; then old=$(git show "$rev:$rs" | wc -c | tr -d ' '); echo "retro skill size: $now bytes (growth since $since: $((now-old)) bytes)"
  else echo "retro skill size: $now bytes (no earlier version before $since)"; fi
fi
for r in "${repos[@]+"${repos[@]}"}"; do commit_stats "$r" "repo $r"; done
if command -v gh >/dev/null 2>&1; then
  echo "CI runs since $since (conclusions):"; gh run list --limit 100 --json conclusion,createdAt --jq "[.[]|select(.createdAt>=\"$since\")]|group_by(.conclusion)|map({(.[0].conclusion):length})|add" 2>/dev/null | sed 's/^/  /'
fi
# Normalise by accepted work (Done tasks updated since the start date); absolute sums mislead when the amount of work differs.
done_p=0
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  grep -q '^status: Done' "$f" || continue
  u=$(awk -F"'" '/^updated_date:/{print substr($2,1,16); exit}' "$f")
  [ -n "$u" ] && [ "$u" \> "$sincefull" -o "$u" = "$sincefull" ] && done_p=$((done_p+1))
done
echo "accepted tasks in period (Done, updated since $since): $done_p"
created_p=0
for f in "${files[@]}"; do
  c=$(awk -F"'" '/^created_date:/{print substr($2,1,16); exit}' "$f")
  [ -n "$c" ] && [ "$c" \> "$sincefull" -o "$c" = "$sincefull" ] && created_p=$((created_p+1))
done
echo "task intake in period: $created_p created, $done_p done"
waiting=""
for f in "${files[@]}"; do
  grep -q '^status: In Progress' "$f" && grep -q '^- \[ \] #' "$f" && waiting="$waiting $(awk -F': ' '/^id:/{print $2; exit}' "$f")"
done
echo "In Progress with unchecked criteria (possibly waiting on an outside event):${waiting:- none}"
py=""; for c in python3 python "py -3"; do $c -c "import sys; sys.exit(sys.version_info[0] < 3)" 2>/dev/null && { py=$c; break; }; done   # Windows: python3 is often a Store stub
q="'"   # bash 3.2 (macOS) mis-parses nested quotes inside $( ) loops
oldest=$(for f in "${files[@]}"; do
  grep -q '^status: Done' "$f" && continue
  d=$(awk -F"$q" '/^created_date:/{print substr($2,1,10); exit}' "$f"); i=$(awk -F': ' '/^id:/{print $2; exit}' "$f")
  echo "$d $i"
done | sort | head -1)
if [ -n "$oldest" ] && [ -n "$py" ]; then
  age=$($py -c "import datetime,sys; print((datetime.date.today()-datetime.date.fromisoformat(sys.argv[1])).days)" "${oldest%% *}" 2>/dev/null)
  echo "oldest open task: ${oldest#* }, created ${oldest%% *}${age:+ ($age days)}"
fi
if [ -f scripts/context-report.py ] && [ -n "$py" ]; then
  b=$($py scripts/context-report.py --since "$since" --brief 2>/dev/null | head -1)
  case "$b" in sessions=*)
    echo "usage: $b"
    t=$(echo "$b" | sed -n 's/.* turns=\([0-9]*\).*/\1/p'); c=$(echo "$b" | sed -n 's/.*cache_read=\([0-9]*\).*/\1/p')
    if [ "$done_p" -gt 0 ]; then echo "per accepted task: turns $((t/done_p)), cache_read $((c/done_p/1000))k tokens (small numbers of tasks: an indication, not proof)"; fi ;;
  *) echo "usage: not evaluable" ;;
  esac
fi
