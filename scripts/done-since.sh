#!/usr/bin/env bash
# Sourced helper (TASK-333): done_since FILE SINCE_UTC ("YYYY-MM-DD HH:MM") succeeds when the task reached Done in the window.
# Uses the newest commit that touched the 'status: Done' line (a relabel or edit of an old Done task does not count).
# Falls back to updated_date for files without git history or with uncommitted changes.
done_since() {
  local f=$1 since=$2 u c
  grep -q '^status: Done' "$f" || return 1
  u=$(awk -F"'" '/^updated_date:/{print substr($2,1,16); exit}' "$f")
  [ -n "$u" ] || u=$(awk -F"'" '/^created_date:/{print substr($2,1,16); exit}' "$f")
  [ -z "$since" ] && return 0
  [[ "$u" < "$since" ]] && return 1   # cheap prefilter: a Done transition always bumps updated_date
  if [ -n "$(git log -1 --format=%H -- "$f" 2>/dev/null)" ] && git diff --quiet HEAD -- "$f" 2>/dev/null; then
    c=$(TZ=UTC git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M' -G'^status: Done' -- "$f" 2>/dev/null)
    [ -n "$c" ] || return 0
    [[ "$c" > "$since" || "$c" = "$since" ]]
  else
    return 0
  fi
}
