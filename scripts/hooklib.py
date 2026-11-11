#!/usr/bin/env python3
"""Shared reader for STEM hook scripts: one place that knows how each agent delivers hook input and accepts hook output.
Used by context-check.py, large-read-warn.py, deny-guard.py, detach-reminder.py and session-start.sh, so a changed hook API is
fixed here once. Wiring per agent: scripts/hooks/manifest.json (generator: scripts/hooks-sync.py).

  read_input()            hook JSON from stdin as a dict ({} on a terminal, on bad input, or when nothing arrives in time)
  fields(data)            the same names for every agent: agent, event, model, session, transcript, cwd, tool, command, file, ranged
  emit_context(event, m)  print a note for the model in the form the event accepts (plain text or JSON)
  emit_deny(reason)       PreToolUse: refuse the tool call
  config(key, default)    project choices from docs/agent/stem-config.json (set at setup; hook files are never edited for them)
  model_class(...)        'standard' or 'lean' (docs/agent/model-classes.json); unknown models are 'standard'

CLI (for session-start.sh): hooklib.py class [--root DIR]  -> prints "<class> <model>" from the hook input on stdin.
Never raises towards the caller: a guard that cannot read its input stays silent."""
import json, os, re, select, shlex, sys

PLAIN_EVENTS = ("SessionStart", "UserPromptSubmit")  # plain stdout reaches the model in Claude Code and Codex; other events need JSON


def read_input(stream=None, timeout=0.5):
    stream = stream or sys.stdin
    try:
        if stream.isatty(): return {}
        try:  # an agent may run a script by hand with an open, silent stdin: never wait for it
            if not select.select([stream], [], [], timeout)[0]: return {}
        except (OSError, ValueError): pass  # not selectable (Windows pipes, test streams): read directly
        data = json.loads(stream.read() or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def agent_of(data=None, env=None):
    env = os.environ if env is None else env
    forced = env.get("STEM_PORT_AGENT")
    if forced: return forced
    path = str((data or {}).get("transcript_path") or "")
    if "/.codex/" in path or any(k.startswith("CODEX_") for k in env): return "codex"
    if "/.claude/" in path or env.get("CLAUDECODE") or env.get("CLAUDE_PROJECT_DIR"): return "claude-code"
    return "unknown"


def _command(inp):
    """Shell command of a tool call as one string. Codex may pass an argv list such as ["bash", "-lc", "cat x"]."""
    c = inp.get("command", inp.get("cmd", ""))
    if isinstance(c, list):
        c = [str(x) for x in c]
        return c[-1] if len(c) >= 3 and c[1] in ("-c", "-lc") else " ".join(c)
    return c if isinstance(c, str) else ""


def fields(data, env=None):
    data = data if isinstance(data, dict) else {}
    inp = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    tool = str(data.get("tool_name") or "")
    return {
        "agent": agent_of(data, env),
        "event": str(data.get("hook_event_name") or ""),
        "model": str(data.get("model") or data.get("to_model") or ""),
        "session": str(data.get("session_id") or ""),
        "transcript": str(data.get("transcript_path") or ""),
        "cwd": str(data.get("cwd") or ""),
        "tool": "Bash" if tool in ("Bash", "shell", "local_shell", "exec_command", "unified_exec") else tool,
        "command": _command(inp),
        "file": inp.get("file_path") if isinstance(inp.get("file_path"), str) else "",
        "ranged": bool(inp.get("offset") or inp.get("limit") or inp.get("pages")),
    }


def strip_heredocs(command):
    """Drop heredoc bodies and the << operators so commands after the terminators are still seen. Several heredocs on one line are
    read in order; here-strings (<<<) are not heredocs. A heredoc without terminator is left alone."""
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        ms = list(re.finditer(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1", line))
        end, j = None, i + 1
        for m in ms:
            end = next((k for k in range(j, len(lines)) if lines[k].strip() == m.group(2)), None)
            if end is None: break
            j = end + 1
        if not ms or end is None:
            out.append(line); i += 1
        else:
            out.append(re.sub(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1", "", line)); i = end + 1
    return "\n".join(out)


def steps(command):
    """A shell command as [(words, separator after it)], split at &&, ||, ;, |, &, parentheses and newlines. Heredoc bodies are
    skipped; quoted text stays one word, so a command named inside a commit message is not a step. [] when it cannot be parsed."""
    lex = shlex.shlex(strip_heredocs(command), posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace, lex.whitespace_split = " \t\r", True
    try: tokens = list(lex)
    except ValueError: return []
    out, step = [], []
    for tok in tokens:
        if tok == "<<": break  # unterminated heredoc (terminated ones are stripped above)
        if tok in ("&&", "||", ";", "\n", "|", "&", "(", ")"):
            out.append((step, tok)); step = []
        else: step.append(tok)
    out.append((step, ""))
    return out


def emit_context(event, message, out=None):
    out = out or sys.stdout
    if event in PLAIN_EVENTS: print(message, file=out)
    else: print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}), file=out)


def emit_deny(reason, out=None):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}), file=out or sys.stdout)


def project_root(start=None):
    """Nearest folder upwards that holds AGENTS.md (the scripts live in <root>/scripts)."""
    d = os.path.abspath(start or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    while True:
        if os.path.exists(os.path.join(d, "AGENTS.md")): return d
        up = os.path.dirname(d)
        if up == d: return os.path.abspath(start or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        d = up


def _json(path):
    try:
        with open(path, encoding="utf-8") as f: d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def config(key, default=None, root=None):
    return _json(os.path.join(root or project_root(), "docs", "agent", "stem-config.json")).get(key, default)


def model_class(model="", root=None, env=None):
    """(class, source). Order: 'Model class:' line in AGENTS.md, then the model name against model-classes.json, else standard.
    Low effort is always standard (CLAUDE_EFFORT; unknown elsewhere)."""
    root, env = root or project_root(), os.environ if env is None else env
    try:
        with open(os.path.join(root, "AGENTS.md"), encoding="utf-8") as f:
            m = re.search(r"^[-* ]*\**Model class:?\**:?\s*`?(standard|lean)\b", f.read(), re.M | re.I)
        if m: return m.group(1).lower(), "AGENTS.md"
    except OSError: pass
    if not model or env.get("CLAUDE_EFFORT", "").lower() == "low": return "standard", "default"
    for pat in _json(os.path.join(root, "docs", "agent", "model-classes.json")).get("lean", []):
        try:
            if re.search(pat, model, re.I): return "lean", "model"
        except re.error: continue
    return "standard", "default"


def _state(session):
    sid = "".join(c for c in session if c.isalnum())[:40]
    return os.path.join(os.environ.get("TMPDIR", "/tmp"), "agent-logs", "class-" + sid) if sid else ""


def remember_class(session, cls):
    """Hooks later in the session get no model field (Claude Code): session start leaves the class for them."""
    p = _state(session)
    if not p: return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f: f.write(cls)
    except OSError: pass


def session_class(session):
    try:
        with open(_state(session)) as f: return f.read().strip() or "standard"
    except (OSError, TypeError): return "standard"


def main(argv):
    if argv[:1] == ["class"]:
        root = argv[argv.index("--root") + 1] if "--root" in argv else None
        f = fields(read_input())
        cls, src = model_class(f["model"], root)
        remember_class(f["session"], cls)
        print(cls, f["model"] or "-", src)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
