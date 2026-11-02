#!/usr/bin/env python3
"""Whole-file read warning for Claude Code (PreToolUse hook on Read and Bash). Warns, never blocks: when Read has no offset/limit, or a
Bash command is a plain `cat FILE`, and the text file is larger than 8 KB (env LARGE_READ_BYTES), it adds one line to the agent's context
suggesting a partial read (offset/limit, grep, sed -n). Reads the hook JSON from stdin. Silent and exit 0 on any problem or small file."""
import json, os, re, shlex, sys

LIMIT = int(os.environ.get("LARGE_READ_BYTES", "8192"))
SKIP = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb")


def target(data):
    tool, inp = data.get("tool_name"), data.get("tool_input") or {}
    if tool == "Read":
        return None if inp.get("offset") or inp.get("limit") or inp.get("pages") else inp.get("file_path")
    if tool == "Bash":
        try: parts = shlex.split(inp.get("command", ""))
        except ValueError: return None
        if len(parts) == 2 and parts[0] == "cat" and not parts[1].startswith("-") and not re.search(r"[|;&<>$`]", inp.get("command", "")): return parts[1]
    return None


def main():
    try:
        path = target(json.load(sys.stdin))
        if not path or path.lower().endswith(SKIP): return
        size = os.path.getsize(os.path.expanduser(path))
    except (ValueError, OSError, TypeError):
        return
    if size > LIMIT:
        msg = f"Large read: {os.path.basename(path)} is {size // 1024} KB. A whole-file read is carried in every later turn; prefer grep, sed -n or Read with offset/limit unless you need all of it."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}))


if __name__ == "__main__":
    main()
