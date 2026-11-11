#!/usr/bin/env python3
"""Whole-file read warning (PreToolUse hook on Read and Bash; input and output form per agent: hooklib.py). Warns, never blocks: when Read has no offset/limit, or a
Bash command runs `cat FILE...` (alone or as a step of a compound command with &&, ||, ;, | or newlines; `cd DIR` steps are followed),
and the text file is larger than 8 KB (env LARGE_READ_BYTES), it adds one line to the agent's context suggesting a partial read
(offset/limit, grep, sed -n). A cat piped into another command, redirected, or with options or $/` in a path is left alone. Reads the hook JSON from stdin. Silent and exit 0 on any problem or small file."""
import os, re, sys
import hooklib

LIMIT = int(os.environ.get("LARGE_READ_BYTES", "8192"))
SKIP = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb")


def cat_targets(command, cwd):
    """Files a Bash command prints whole with cat. Heredoc bodies are skipped; ignores cat whose output goes into a pipe or redirect."""
    found = []
    for words, sep in hooklib.steps(command):
        if words[:1] == ["cd"] and len(words) == 2 and not re.search(r"[$`]", words[1]):
            cwd = os.path.join(cwd, os.path.expanduser(words[1]))
        elif words[:1] == ["cat"] and len(words) > 1 and sep != "|":
            args = words[1:]
            if any(a.startswith("-") or re.search(r"[<>$`*?]", a) or a.isdigit() for a in args): continue
            found += [os.path.join(cwd, os.path.expanduser(a)) for a in args]
    return found


def targets(data):
    f = hooklib.fields(data)
    if f["tool"] == "Read":
        return [] if f["ranged"] else [f["file"]]
    if f["tool"] == "Bash":
        return cat_targets(f["command"], f["cwd"] or os.getcwd())
    return []


def main():
    if hooklib.config("large_read_warning", True) is False: return
    try: paths = targets(hooklib.read_input())
    except (ValueError, AttributeError): return
    big = []
    for path in paths:
        if not isinstance(path, str) or path.lower().endswith(SKIP): continue
        try: size = os.path.getsize(os.path.expanduser(path))
        except OSError: continue
        if size > LIMIT: big.append(f"{os.path.basename(path)} is {size // 1024} KB")
    if big:
        msg = f"Large read: {'; '.join(big)}. A whole-file read is carried in every later turn; prefer grep, sed -n or Read with offset/limit unless you need all of it."
        hooklib.emit_context("PreToolUse", msg)


if __name__ == "__main__":
    main()
