#!/usr/bin/env python3
"""PostToolUse hook for the Claude desktop app's start_session tool (R-BATCHING hand-off).
Reads the hook JSON on stdin; if a new session was started (its id looks like local_<uuid>), adds one line to the
starter's context naming the exact detach_session call. A hook cannot call app tools itself, so this only removes the
chance to forget the id. Silent on anything else; never fails the tool call."""
import json, re, sys

try:
    data = json.load(sys.stdin)
    if "start_session" not in str(data.get("tool_name", "")): sys.exit(0)
    text = json.dumps(data.get("tool_response", ""))
    m = re.search(r"local_[0-9a-f]{8}-[0-9a-f-]{27}", text)
    if not m or "started" not in text.lower(): sys.exit(0)
    msg = (f"Hand-off: session {m.group(0)} was started. If it is a fresh independent session (not one that must report back), "
           f"call detach_session with session_id \"{m.group(0)}\" now (R-BATCHING).")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}))
except Exception:
    pass
