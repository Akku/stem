#!/usr/bin/env python3
"""PostToolUse hook for the Claude desktop app's start_session tool (R-BATCHING hand-off).
Reads the hook JSON on stdin; if a new session was started (its id looks like local_<uuid>), adds one line to the
starter's context naming the exact detach_session call. A hook cannot call app tools itself, so this only removes the
chance to forget the id. Silent on anything else; never fails the tool call."""
import json, re, sys
import hooklib

try:
    data = hooklib.read_input()
    if "start_session" not in str(data.get("tool_name", "")): sys.exit(0)
    if hooklib.session_class(str(data.get("session_id") or "")) == "lean": sys.exit(0)  # R-ROUTING, Model classes: no reminder for class lean
    text = json.dumps(data.get("tool_response", ""))
    m = re.search(r"local_[0-9a-f]{8}-[0-9a-f-]{27}", text)
    if not m or "started" not in text.lower(): sys.exit(0)
    brief = json.dumps(data.get("tool_input", "")).lower()
    sid = m.group(0)
    if "do not report back" in brief or "never message or answer the starting session" in brief:
        msg = f"Hand-off: session {sid} was started and must not report back. Call detach_session with session_id \"{sid}\" now (R-BATCHING)."
    elif re.search(r"report(s|ing)? (back )?to the starter|batch subsession|report back", brief):
        msg = f"Subsession {sid} was started and must report back: keep it linked, do not call detach_session (R-BATCHING, Batch execution)."
    else:
        msg = (f"Hand-off: session {sid} was started. If it is a fresh independent session (a handoff, not one that must report back), "
               f"call detach_session with session_id \"{sid}\" now; a batch subsession or other session that must report back stays linked (R-BATCHING).")
    hooklib.emit_context("PostToolUse", msg)
except Exception:
    pass
