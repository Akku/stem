#!/usr/bin/env python3
"""Context watchdog for Claude Code and Codex (UserPromptSubmit hook). Prints a short notice into the agent's context when the
current context exceeds a threshold: one notice, and one urgent notice at max(200k, 1.5x the threshold), each once per session (TASK-203, TASK-413).
Threshold = larger of 130k (env CONTEXT_WARN_TOKENS) and first-turn context of the session + 50k (the fixed floor of system prompt,
tools and instructions is not session growth); with a known window (Claude: model from the transcript; Codex: model_context_window
from the session log) at most 90 % of it.
Reads the hook JSON from stdin through hooklib.py (transcript_path, session_id); manual use: --transcript FILE; task-end check: --auto finds the current
session log itself (Codex: CODEX_THREAD_ID; Claude: newest transcript of this directory) and also prints one line below the threshold;
--auto --notice-only (used by scripts/run.sh, so agents without a prompt hook get the notice too) stays silent below it.
Switched off per project with "context_warning": false in docs/agent/stem-config.json (the hook entry stays).
Silent and exit 0 on any problem or below the threshold (hook mode). Numbers only, no transcript content is printed."""
import glob, json, os, re, sys
import hooklib, transcripts

BASE = int(os.environ.get("CONTEXT_WARN_TOKENS", "130000"))  # first notice: fixed floor (TASK-413)
URGENT = 200000  # second notice no earlier than this (TASK-413)
GROWTH = 50000
WINDOW = 200000  # older claude-* models without a "[1m]" marker; other models: unknown

def claude_window(model):
    """1M for Claude 5.x and Opus 4.7+ (1M by default, no [1m] marker; TASK-418) or a "[1m]" marker, else 200k."""
    if "[1m]" in model: return 1000000
    m = re.match(r"claude-(opus|sonnet|haiku)-(\d+)-(\d+)", model)
    if m and (int(m.group(2)) >= 5 or (m.group(1) == "opus" and (int(m.group(2)), int(m.group(3))) >= (4, 7))): return 1000000
    return WINDOW

def usage_of(r):
    """(context tokens, model or window marker) of a Claude assistant record or a Codex token_count event, else None."""
    p = r.get("payload") if isinstance(r.get("payload"), dict) else {}
    if p.get("type") == "token_count":  # Codex: input_tokens includes cached ones; desktop logs only fill total_tokens
        info = p.get("info") if isinstance(p.get("info"), dict) else {}
        u = info.get("last_token_usage") or {}
        n = u.get("input_tokens") or u.get("total_tokens")
        return (n, "codex:%s" % (info.get("model_context_window") or "")) if n else None
    u = (r.get("message") or {}).get("usage") if r.get("type") == "assistant" and not r.get("isSidechain") else None
    return (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0), str(r["message"].get("model", ""))) if u else None

def read_lines(path, tail):
    with open(path, "rb") as f:
        if tail: f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 400000))
        else: return f.read(400000).decode("utf-8", "replace").splitlines()
        return f.read().decode("utf-8", "replace").splitlines()

def scan(path):
    """(current context = last usage record, first-turn context = first usage record, model of the last one)."""
    last, model = None, ""
    for line in reversed(read_lines(path, True)):
        try: u = usage_of(json.loads(line))
        except (ValueError, AttributeError): continue
        if u: last, model = u; break
    first = None
    for line in read_lines(path, False):
        try: u = usage_of(json.loads(line))
        except (ValueError, AttributeError): continue
        if u: first = u[0]; break
    return last or 0, first, model

def threshold(first, model):
    """max(130k, first-turn + 50k) (TASK-413); with a known window at most 90 % of it."""
    t = max(BASE, (first or 0) + GROWTH)
    if model.startswith("codex:"): window = int(model[6:]) if model[6:].isdigit() else 0
    elif "[1m]" in model or model.startswith("claude-"): window = claude_window(model)
    else: window = 0  # unknown model: window unknown, no cap
    return min(t, window * 9 // 10) if window else t

def current_log():
    """Session log of the running agent: Codex by CODEX_THREAD_ID, else the newest Claude transcript of this directory."""
    tid = os.environ.get("CODEX_THREAD_ID", "")
    if tid:
        home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
        hits = glob.glob(os.path.join(home, "sessions", "**", "*%s*.jsonl" % tid), recursive=True)
        if hits: return max(hits, key=os.path.getmtime)
    slug = transcripts.slug(os.getcwd())
    hits = glob.glob(os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects", slug, "*.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else ""

def main():
    args = sys.argv[1:]
    quiet = "--notice-only" in args  # scripts/run.sh: like the hook (silent below the threshold, one notice and one urgent per session), log found like --auto
    manual = ("--transcript" in args or "--auto" in args) and not quiet
    if "--transcript" not in args and hooklib.config("context_warning", True) is False: return 0  # module switched off at setup
    try:
        if "--transcript" in args:
            path, sid = args[args.index("--transcript") + 1], "manual"
        elif "--auto" in args:
            path = current_log(); sid = os.path.splitext(os.path.basename(path))[0] if quiet else "manual"
        else:
            f = hooklib.fields(hooklib.read_input()); path, sid = f["transcript"], f["session"] or "x"
        tokens, first, model = scan(path)
        THRESHOLD = threshold(first, model)
    except Exception:
        return 0
    if tokens < THRESHOLD:
        if "--auto" in args and tokens and not quiet: print("context check: about %dk tokens, threshold %dk: continue." % (tokens // 1000, THRESHOLD // 1000))
        return 0
    state = os.path.join(os.environ.get("TMPDIR", "/tmp"), "agent-logs", "ctx-" + "".join(c for c in sid if c.isalnum())[:40])
    level = 2 if tokens >= max(URGENT, THRESHOLD * 3 // 2) else 1
    last = 0  # highest level already printed in this session (state file holds 1 or 2; anything else counts as none)
    try: last = int(open(state).read().strip() or 0)
    except Exception: pass
    if last not in (1, 2): last = 0
    if not manual and level <= last: return 0
    try:
        os.makedirs(os.path.dirname(state), exist_ok=True); open(state, "w").write(str(level))
    except Exception: pass
    urgent = level == 2
    print("CONTEXT NOTICE (%s): the context holds about %dk tokens (threshold %dk, session started at %dk). %s" % ("run.sh" if quiet else "hook", tokens // 1000, THRESHOLD // 1000, (first or 0) // 1000,
          "Do not wait for the task end: interrupt your work at the next sensible point and hand off the rest to a new session, even inside a related batch. Finish first only if very little is left." if urgent else
          "If at least ~5 turns of the current task remain, interrupt it at a sensible point and hand off the rest to a new session. Otherwise finish it, then hand off only if at least ~5 turns of unrelated work are ahead. Continue in this session if the rest is short, closely related (batch) or needs hard-won context."),
          "Hand-off (R-BATCHING, which defines a sensible point): run the handoff skill; it always ends by starting a fresh session yourself, detached (no fork of this conversation) and stopping. Inside an approved batch do it without asking; otherwise tell the user (in their language) the context is large and that they may say Handoff.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
