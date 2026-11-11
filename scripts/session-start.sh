#!/usr/bin/env bash
# Session bootstrap: compact current-state summary. Changes no project files; writes a version-check cache
# under ${TMPDIR:-/tmp}/agent-logs and contacts GitHub at most daily. Offline: STEM_OFFLINE=1 skips all network calls.
set -u
# model class (R-ROUTING, Model classes): read the hook input before anything else can consume stdin; empty without python3 or input
mc=$(python3 "$(dirname "$0")/hooklib.py" class --root "$PWD" 2>/dev/null)
echo "## git"
if git rev-parse --git-dir >/dev/null 2>&1; then
  echo "branch: $(git branch --show-current)"
  [ "$(git config core.hooksPath)" = "scripts/githooks" ] || echo "WARNING: pre-commit guard inactive -> git config core.hooksPath scripts/githooks"
  echo "changes: $(git status --porcelain | wc -l | tr -d ' ') file(s)"
  git status --porcelain | head -10
  echo "recent commits:"; git log --oneline -3
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
    echo "STEM UPDATE AVAILABLE: $lv -> $rv (offer the stem-update skill, `R-STEM-UPDATE`; do not update unasked)"
    # distance in minor versions (patch releases do not count; another major always warns)
    lmaj=${lv%%.*}; rmaj=${rv%%.*}; lmin=$(echo "$lv" | cut -d. -f2); rmin=$(echo "$rv" | cut -d. -f2)
    if [ "$lmaj" != "$rmaj" ]; then lag=99; else lag=$((${rmin:-0} - ${lmin:-0})); fi
    [ "$lag" -gt 2 ] && echo "WARNING: this project is far behind STEM ($lv vs $rv, $([ "$lag" = 99 ] && echo 'another major version' || echo "$lag minor versions")): updates get harder with every release; recommend the stem-update skill soon"
  fi
else
  echo "no STEM_VERSION file"
fi
# port check (docs/agent/PORT_CHECK.md): reference environment from STEM_VERSION; offer only after SETUP is done, never again once PORT.md exists
if [ -f docs/agent/PORT.md ]; then
  echo "port overlay: read docs/agent/PORT.md and docs/agent/port/ before working (adapted scripts take precedence over scripts/)"
elif grep -q '^\*\*Setup status:\*\* DONE' AGENTS.md 2>/dev/null && [ -f STEM_VERSION ]; then
  ros=$(sed -n 's/^reference-os: *//p' STEM_VERSION | head -1); rag=$(sed -n 's/^reference-agent: *//p' STEM_VERSION | head -1)
  cos="${STEM_PORT_OS:-$(uname -s 2>/dev/null)}"
  if [ -n "${STEM_PORT_AGENT:-}" ]; then cag="$STEM_PORT_AGENT"
  elif [ -n "${CLAUDECODE:-}" ]; then cag=claude-code
  elif env | grep -q '^CODEX_'; then cag=codex
  else cag=unknown; fi
  if { [ -n "$ros" ] && [ "$cos" != "$ros" ]; } || { [ -n "$rag" ] && [ "$cag" != "$rag" ]; }; then
    echo "PORT CHECK AVAILABLE: this environment (os $cos, agent $cag) differs from the reference ($ros, $rag, $(sed -n 's/^reference-model: *//p' STEM_VERSION | head -1)); offer the port-check skill once, do not start unasked"
  fi
fi
if [ -z "${STEM_OFFLINE:-}" ] && [ -f .github/stem-check.py ] && command -v gh >/dev/null 2>&1; then
  # STEM maintainer only (this file is removed from projects): incoming learnings
  prs=$(gh pr list --state open --limit 5 --json number,title,headRefName -q '.[]|"#\(.number) \(.headRefName): \(.title)"' 2>/dev/null)
  [ -n "$prs" ] && { echo "STEM MAINTAINER: open pull requests (review, merge or close):"; echo "$prs"; }
  lb=$(git ls-remote --heads origin 'learning/*' 2>/dev/null | sed 's#.*refs/heads/##' | head -5)
  [ -n "$lb" ] && { echo "learning branches on origin:"; echo "$lb"; }
fi
# switched off for start context (TASK-166/168, start-context.py): the agent must know what exists so it can suggest switching it on again
so=$(python3 - 2>/dev/null <<'PY'
import json
mcp, sk = [], []
for p in (".claude/settings.json", ".claude/settings.local.json"):
    try: d = json.load(open(p))
    except Exception: continue
    mcp += [e.get("serverName") if isinstance(e, dict) else e for e in d.get("deniedMcpServers", [])]
    sk += [n for n, v in d.get("skillOverrides", {}).items() if v == "off"]
if mcp or sk: print("switched off to save start context: MCP " + (", ".join(m for m in mcp if m) or "-") + " | skills " + (", ".join(sk) or "-"))
PY
)
[ -n "$so" ] && { echo; echo "$so"; echo "(if a task could use one of them, suggest switching it on: scripts/start-context.py undo-mcp|skills-on NAME; takes effect next session)"; }
nl=$(python3 "$(dirname "$0")/start-context.py" new --line 2>/dev/null); [ -n "$nl" ] && { echo; echo "$nl"; }  # TASK-175: new skills/MCP above 250 B
echo; echo "## backlog"
if command -v backlog >/dev/null 2>&1 && { [ -d backlog ] || [ -d .backlog ]; }; then
  echo "milestones:"; backlog milestone list --plain 2>/dev/null | sed -n '/^Active/,/^Completed/p' | grep -v '^Completed' | head -8
  echo "in progress:"; backlog task list -s "In Progress" --plain 2>/dev/null | head -15
  # counts plus top 3 keep the start context small (TASK-164); the full list: backlog task list -s "To Do" --ready --plain
  rd=$(backlog task list -s "To Do" --ready --plain 2>/dev/null | grep -E '^ *\[?.*TASK-[0-9]+ ')
  echo "ready (unblocked, to do): $(printf '%s\n' "$rd" | grep -c TASK-) total, top 3 (full list: backlog task list -s \"To Do\" --ready --plain):"; printf '%s\n' "$rd" | head -3
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
  # threshold: 8, doubled to 16 when the newest retro run recorded 0 adopted changes and 0 open signals (R-RETRO)
  thr="${RETRO_DUE_AFTER:-}"
  if [ -z "$thr" ]; then
    thr=8; lj=$(ls docs/agent/retro-runs/*.json 2>/dev/null | sort | tail -1)
    [ -n "$lj" ] && [ "$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])).get("result") or {}; print(int(r.get("adopted", 1) == 0 and r.get("open_signals", 1) == 0))' "$lj" 2>/dev/null)" = 1 ] && thr=16
  fi
  if [ "$n" -ge "$thr" ]; then
    echo "RETRO DUE: $n tasks done since ${lrd:-the start} (threshold $thr); offer the retro skill, do not start unasked"
  fi
fi
# waiting tasks whose outside event happened (fixed condition kinds only, see the script)
[ -d backlog/tasks ] && [ -f scripts/wait-check.py ] && python3 scripts/wait-check.py 2>/dev/null
# usage probes (docs/agent/PROBES.md): open and fired ones
[ -d backlog/tasks ] && [ -f scripts/probe.py ] && python3 scripts/probe.py report 2>/dev/null
echo; echo "## backlog check"; scripts/check-backlog.sh 2>/dev/null | head -10; [ "${PIPESTATUS[0]:-0}" -eq 0 ] && echo "ok"
# open user questions: drafts whose description starts with "Question to the user" (recorded when a question stays open, see the handoff skill)
oq=""
for f in backlog/drafts/*.md; do
  [ -f "$f" ] || continue
  awk '/DESCRIPTION:BEGIN/{getline; ok=($0 ~ /^Question to the user/); exit} END{exit !ok}' "$f" 2>/dev/null \
    && oq="$oq$(sed -n 's/^id: //p' "$f" | head -1): $(sed -n 's/^title: //p' "$f" | head -1 | tr -d "'")"$'\n'
done
[ -n "$oq" ] && { echo; echo "## open questions for the user (answer or ask first; the draft holds the options)"; printf '%s' "$oq"; }
echo; echo "## handoff"
if [ -f docs/agent/HANDOFF.md ]; then
  # consumed: a handoff is written for exactly the next session; any commit after the one that last touched it means that session ran
  hc=$(git log -1 --format=%H -- docs/agent/HANDOFF.md 2>/dev/null); n=0
  [ -n "$hc" ] && n=$(git rev-list --count "$hc..HEAD" 2>/dev/null || echo 0)
  if [ "$n" -ge "${HANDOFF_STALE_COMMITS:-1}" ]; then
    echo "HANDOFF.md is consumed ($n commits since it was written): content not shown, ignore it. State is in git and the backlog. If the last session skipped the handoff, delete the file (committed)."
  else
    sed -n '1,40p' docs/agent/HANDOFF.md
    [ "$(wc -c < docs/agent/HANDOFF.md)" -gt 2048 ] && echo "WARNING: HANDOFF.md is over 2 KB: rewrite it from scratch (handoff skill); it is loaded every session"
    # staleness: the first "stem [version] X.Y.Z" named in the handoff must match STEM_VERSION
    hv=$(grep -oiE '(^|[^a-z])stem( version)?:? v?[0-9]+\.[0-9]+\.[0-9]+' docs/agent/HANDOFF.md | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+$')
    [ -n "$hv" ] && [ -n "${lv:-}" ] && [ "$hv" != "$lv" ] && echo "WARNING: HANDOFF.md names stem $hv but STEM_VERSION is $lv: the handoff may be stale; check it against the current state"
  fi
else echo "no HANDOFF.md (clean boundary: state is in git and the backlog)"; fi
mn=$(echo "$mc" | awk '{print $2}')  # named by the agent's hook input; setup then skips its model question
[ -n "$mn" ] && [ "$mn" != "-" ] && { echo; echo "MODEL IN USE: $mn${CLAUDE_EFFORT:+, effort $CLAUDE_EFFORT} (from the agent, not asked)"; }
case "$mc" in lean\ *)
  mm=${mc#lean }; echo; echo "MODEL CLASS lean (${mm% *}; \`R-ROUTING\`, Model classes): the size-S fast path (core rule 1a) also covers size-M tasks; core rule 3 applies only when instruction files are edited; core rule 5 and the tool-proposal sentence of rule 4 need no reminder. Everything else applies unchanged, including security, stop conditions and evidence." ;;
esac
echo; echo "Rules: see AGENTS.md; further rules by ID via docs/agent/OPERATING_MODEL.md"
