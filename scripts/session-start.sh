#!/usr/bin/env bash
# Session bootstrap: compact current-state summary. Changes no project files; writes a version-check cache
# under ${TMPDIR:-/tmp}/agent-logs and contacts GitHub at most daily. Offline: STEM_OFFLINE=1 skips all network calls.
set -u
echo "## git"
if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "branch: $(git branch --show-current)"
  [ "$(git config core.hooksPath)" = "scripts/githooks" ] || echo "WARNING: pre-commit guard inactive -> git config core.hooksPath scripts/githooks"
  echo "changes: $(git status --porcelain | wc -l | tr -d ' ') file(s)"
  git status --porcelain | head -10
  if command -v python3 >/dev/null 2>&1 && [ -f scripts/check-remote-state.py ]; then
    python3 scripts/check-remote-state.py
  fi
  echo "recent commits:"; git log --oneline -5
else
  echo "no git repository"
fi
echo; echo "## stem"
if [ -f STEM_VERSION ]; then
  lv=$(sed -n 's/^version: *//p' STEM_VERSION | head -1); repo=$(sed -n 's/^repo: *//p' STEM_VERSION | head -1)
  echo "stem version: ${lv:-unknown}"
  cache="${TMPDIR:-/tmp}/agent-logs/stem-check-$(printf %s "$PWD" | cksum | cut -d' ' -f1)"; mkdir -p "$(dirname "$cache")"
  if [ -z "${STEM_OFFLINE:-}" ] && [ -n "$repo" ] && command -v curl >/dev/null 2>&1 && { [ ! -f "$cache" ] || [ -n "$(find "$cache" -mtime +0 2>/dev/null)" ]; }; then
    raw="${repo/github.com/raw.githubusercontent.com}/main/STEM_VERSION"
    rv=$(curl -fsSL --max-time 3 "$raw" 2>/dev/null | sed -n 's/^version: *//p' | head -1)
    [ -n "$rv" ] && printf '%s\n' "$rv" >"$cache"
  fi
  rv=$(cat "$cache" 2>/dev/null)
  if [ -n "$rv" ] && [ -n "$lv" ] && [ "$rv" != "$lv" ] && [ "$(printf '%s\n%s\n' "$lv" "$rv" | sort -V | tail -1)" = "$rv" ]; then
    echo "STEM UPDATE AVAILABLE: $lv -> $rv (offer the stem-update skill; do not update unasked)"
  fi
else
  echo "no STEM_VERSION file"
fi
if [ -z "${STEM_OFFLINE:-}" ] && [ -f .github/stem-check.py ] && command -v gh >/dev/null 2>&1; then
  # STEM maintainer only (this file is removed from projects): incoming learnings
  prs=$(gh pr list --state open --limit 5 --json number,title,headRefName -q '.[]|"#\(.number) \(.headRefName): \(.title)"' 2>/dev/null)
  [ -n "$prs" ] && { echo "STEM MAINTAINER: open pull requests (review, merge or close):"; echo "$prs"; }
  lb=$(git ls-remote --heads origin 'learning/*' 2>/dev/null | sed 's#.*refs/heads/##' | head -5)
  [ -n "$lb" ] && { echo "learning branches on origin:"; echo "$lb"; }
fi
echo; echo "## backlog"
if command -v backlog >/dev/null 2>&1 && { [ -d backlog ] || [ -d .backlog ]; }; then
  echo "milestones:"; backlog milestone list --plain 2>/dev/null | sed -n '/^Active/,/^Completed/p' | grep -v '^Completed' | head -8
  echo "in progress:"; backlog task list -s "In Progress" --plain 2>/dev/null | head -15
  echo "ready (unblocked, to do):"; backlog task list -s "To Do" --ready --plain 2>/dev/null | head -10
else
  echo "backlog not initialised (follow SETUP.md)"
fi
# retro due hint: Done tasks changed since the last retro notes commit (docs/agent/retros/YYYY-MM-DD.md)
if [ -d backlog/tasks ]; then
  lr=$(ls docs/agent/retros 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}\.md$' | sort | tail -1)
  lrd="${lr%.md}"; since=""; [ -n "$lr" ] && since=$(TZ=UTC git log -1 --format=%cd --date=format-local:'%Y-%m-%d %H:%M' -- "docs/agent/retros/$lr" 2>/dev/null)
  [ -z "$since" ] && [ -n "$lr" ] && since="${lr%.md} 23:59"
  n=0
  for f in backlog/tasks/task-*.md; do
    [ -f "$f" ] || continue
    grep -q "^status: Done" "$f" || continue
    d=$(sed -n "s/^updated_date: '\([0-9: -]*\)'.*/\1/p;s/^created_date: '\([0-9: -]*\)'.*/\1/p" "$f" | tail -1)
    if [ -z "$since" ] || [[ "$d" > "$since" ]]; then n=$((n+1)); fi
  done
  if [ -n "$lr" ] && grep -q '^## First retro' docs/agent/NEXT_RETRO.md 2>/dev/null; then
    echo "RETRO OPEN ITEMS: retro notes exist but the 'First retro' section of docs/agent/NEXT_RETRO.md is still there; process it at the next retro (do not start unasked)"
  fi
  if [ "$n" -ge "${RETRO_DUE_AFTER:-8}" ]; then
    echo "RETRO DUE: $n tasks done since ${lrd:-the start} (threshold ${RETRO_DUE_AFTER:-8}); offer the retro skill, do not start unasked"
  fi
fi
echo; echo "## backlog check"; scripts/check-backlog.sh 2>/dev/null | head -10; [ "${PIPESTATUS[0]:-0}" -eq 0 ] && echo "ok"
echo; echo "## handoff"
if [ -f docs/agent/HANDOFF.md ]; then
  sed -n '1,40p' docs/agent/HANDOFF.md
  [ "$(wc -c < docs/agent/HANDOFF.md)" -gt 2048 ] && echo "WARNING: HANDOFF.md is over 2 KB: rewrite it from scratch (handoff skill); it is loaded every session"
  # staleness: the first "stem [version] X.Y.Z" named in the handoff must match STEM_VERSION
  hv=$(grep -oiE '(^|[^a-z])stem( version)?:? v?[0-9]+\.[0-9]+\.[0-9]+' docs/agent/HANDOFF.md | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+$')
  [ -n "$hv" ] && [ -n "${lv:-}" ] && [ "$hv" != "$lv" ] && echo "WARNING: HANDOFF.md names stem $hv but STEM_VERSION is $lv: the handoff may be stale; check it against the current state"
else echo "no HANDOFF.md"; fi
echo; echo "Rules: see AGENTS.md; further rules by ID via docs/agent/OPERATING_MODEL.md"
