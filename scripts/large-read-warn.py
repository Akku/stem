#!/usr/bin/env python3
"""Whole-file read warning for Claude Code (PreToolUse hook on Read and Bash). Warns, never blocks: when Read has no offset/limit, or a
Bash command runs `cat FILE...` (alone or as a step of a compound command with &&, ||, ;, | or newlines; `cd DIR` steps are followed),
and the text file is larger than 8 KB (env LARGE_READ_BYTES), it adds one line to the agent's context suggesting a partial read
(offset/limit, grep, sed -n). A cat piped into another command, redirected, or with options or $/` in a path is left alone. Reads the hook JSON from stdin. Silent and exit 0 on any problem or small file."""
import json, os, re, shlex, sys

LIMIT = int(os.environ.get("LARGE_READ_BYTES", "8192"))
SKIP = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb")


def strip_heredocs(command):
    """Drop heredoc bodies and the << operator so commands after the terminator are still seen. A heredoc without terminator is left alone."""
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r"<<-?\s*(['\"]?)(\w+)\1", line)
        end = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == m.group(2)), None) if m else None
        if end is None:
            out.append(line); i += 1
        else:
            out.append(line[:m.start()] + line[m.end():]); i = end + 1
    return "\n".join(out)


def cat_targets(command, cwd):
    """Files a Bash command prints whole with cat. Heredoc bodies are skipped; ignores cat whose output goes into a pipe or redirect."""
    command = strip_heredocs(command)
    lex = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace, lex.whitespace_split = " \t\r", True
    try: tokens = list(lex)
    except ValueError: return []
    steps, step = [], []
    for tok in tokens:
        if tok == "<<": break  # unterminated heredoc (terminated ones are stripped above)
        if tok in ("&&", "||", ";", "\n", "|", "&", "(", ")"):
            steps.append((step, tok)); step = []
        else: step.append(tok)
    steps.append((step, ""))
    found = []
    for words, sep in steps:
        if words[:1] == ["cd"] and len(words) == 2 and not re.search(r"[$`]", words[1]):
            cwd = os.path.join(cwd, os.path.expanduser(words[1]))
        elif words[:1] == ["cat"] and len(words) > 1 and sep != "|":
            args = words[1:]
            if any(a.startswith("-") or re.search(r"[<>$`*?]", a) or a.isdigit() for a in args): continue
            found += [os.path.join(cwd, os.path.expanduser(a)) for a in args]
    return found


def targets(data):
    tool, inp = data.get("tool_name"), data.get("tool_input") or {}
    if tool == "Read":
        return [] if inp.get("offset") or inp.get("limit") or inp.get("pages") else [inp.get("file_path")]
    if tool == "Bash":
        return cat_targets(inp.get("command", ""), data.get("cwd") or os.getcwd())
    return []


def main():
    try: paths = targets(json.load(sys.stdin))
    except (ValueError, AttributeError): return
    big = []
    for path in paths:
        if not isinstance(path, str) or path.lower().endswith(SKIP): continue
        try: size = os.path.getsize(os.path.expanduser(path))
        except OSError: continue
        if size > LIMIT: big.append(f"{os.path.basename(path)} is {size // 1024} KB")
    if big:
        msg = f"Large read: {'; '.join(big)}. A whole-file read is carried in every later turn; prefer grep, sed -n or Read with offset/limit unless you need all of it."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}))


if __name__ == "__main__":
    main()
