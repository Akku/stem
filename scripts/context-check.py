#!/usr/bin/env python3
"""Context watchdog for Claude Code and Codex (UserPromptSubmit hook). Prints a short notice into the agent's context when the
current context exceeds a threshold, then again every +30k. Threshold = smallest of: first-turn context of the session + 40k (the
fixed floor of system prompt, tools and instructions is not session growth), a cap of 100k (env CONTEXT_WARN_TOKENS) and half the model's
window (Claude: model read from the transcript; Codex: model_context_window from the session log; unknown -> cap of 100k).
Reads the hook JSON from stdin (transcript_path, session_id); manual use: --transcript FILE; task-end check: --auto finds the current
session log itself (Codex: CODEX_THREAD_ID; Claude: newest transcript of this directory) and also prints one line below the threshold.
Silent and exit 0 on any problem or below the threshold (hook mode). Numbers only, no transcript content is printed."""
import glob, json, os, re, sys

CAP = int(os.environ.get("CONTEXT_WARN_TOKENS", "100000"))
GROWTH = 40000
STEP = 30000
WINDOW = 200000  # any claude-* model without a "[1m]" marker; other models: unknown

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
    if model.startswith("codex:"):
        if not model[6:].isdigit(): return min([CAP] + ([first + GROWTH] if first else []))
        window = int(model[6:])
    elif "[1m]" in model: window = 1000000
    elif model.startswith("claude-"): window = WINDOW
    else: return CAP  # unknown Claude-side model: window unknown, fixed cap
    return min([CAP, window // 2] + ([first + GROWTH] if first else []))

def current_log():
    """Session log of the running agent: Codex by CODEX_THREAD_ID, else the newest Claude transcript of this directory."""
    tid = os.environ.get("CODEX_THREAD_ID", "")
    if tid:
        home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
        hits = glob.glob(os.path.join(home, "sessions", "**", "*%s*.jsonl" % tid), recursive=True)
        if hits: return max(hits, key=os.path.getmtime)
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.getcwd())
    hits = glob.glob(os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects", slug, "*.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else ""

def main():
    args = sys.argv[1:]
    manual = "--transcript" in args or "--auto" in args
    try:
        if "--transcript" in args:
            path, sid = args[args.index("--transcript") + 1], "manual"
        elif "--auto" in args:
            path, sid = current_log(), "manual"
        else:
            data = json.load(sys.stdin); path, sid = data.get("transcript_path", ""), str(data.get("session_id", "x"))
        tokens, first, model = scan(path)
        THRESHOLD = threshold(first, model)
    except Exception:
        return 0
    if tokens < THRESHOLD:
        if "--auto" in args and tokens: print("context check: about %dk tokens, threshold %dk: continue." % (tokens // 1000, THRESHOLD // 1000))
        return 0
    state = os.path.join(os.environ.get("TMPDIR", "/tmp"), "agent-logs", "ctx-" + "".join(c for c in sid if c.isalnum())[:40])
    last = 0
    try: last = int(open(state).read().strip() or 0)
    except Exception: pass
    if not manual and last and tokens < last + STEP: return 0
    try:
        os.makedirs(os.path.dirname(state), exist_ok=True); open(state, "w").write(str(tokens))
    except Exception: pass
    urgent = tokens >= THRESHOLD * 1.5
    print("CONTEXT NOTICE (hook): the context holds about %dk tokens (threshold %dk, session started at %dk). %s" % (tokens // 1000, THRESHOLD // 1000, (first or 0) // 1000,
          "Hand off at the next task end, even inside a related batch (R-BATCHING)." if urgent else
          "Do not interrupt the current task. When it is finished, check: hand off only if at least ~5 turns of unrelated work are ahead; continue in this session if the rest is short, closely related (batch) or needs hard-won context."),
          "Hand-off (R-BATCHING): run the handoff skill; it always ends by starting a fresh session yourself, detached (no fork of this conversation) and stopping. Inside an approved batch do it without asking; otherwise tell the user (in their language) the context is large and that they may say Handoff.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
