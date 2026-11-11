#!/usr/bin/env python3
"""Deny guard (PreToolUse hook on shell commands) for agents without Claude Code's permission rules, wired for Codex in
scripts/hooks/manifest.json. Refuses the same things `.claude/settings.json` denies: destructive git commands, skipping the git
hooks, and reading `.env` files or SSH keys. Reads the hook JSON through hooklib.py. Anything it cannot parse passes: it is a
guard against slips, not a sandbox. The user can still run a refused command themselves."""
import os, re, sys
import hooklib

GIT_VALUE_OPTS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace")
ENV_OK = (".env.example", ".env.sample", ".env.template")


def git_reason(words):
    """Why this git call is refused, or None. words: one shell step."""
    i = 0
    while i < len(words) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[i]): i += 1  # VAR=value prefixes
    if words[i:i + 1] != ["git"]: return None
    i += 1
    while i < len(words) and words[i].startswith("-"): i += 2 if words[i] in GIT_VALUE_OPTS else 1
    sub, args = (words[i] if i < len(words) else ""), words[i + 1:]
    flags = [a for a in args if a.startswith("-")]
    short = "".join(a[1:] for a in flags if not a.startswith("--"))
    if sub == "push":
        if "--force" in flags or "f" in short or any(a.startswith("+") for a in args): return "git push --force overwrites commits on the remote"
        if "--delete" in flags or "d" in short or any(a.startswith(":") for a in args if not a.startswith("-")): return "git push --delete removes a remote branch"
    if sub in ("push", "commit") and ("--no-verify" in flags or (sub == "commit" and "n" in short)): return "--no-verify skips the project's git hooks"
    if sub == "reset" and "--hard" in flags: return "git reset --hard discards uncommitted work"
    if sub == "clean" and ("f" in short or "--force" in flags): return "git clean -f deletes untracked files"
    if sub in ("checkout", "restore") and "." in args and "--staged" not in flags: return "git %s . discards all uncommitted changes" % sub
    if sub == "branch" and ("D" in short or ("--delete" in flags and "--force" in flags)): return "git branch -D deletes a branch with unmerged work"
    return None


def secret_reason(words):
    if words[:1] in (["git"], ["echo"], ["printf"]): return None  # naming a file is not reading it
    for w in words[1:]:
        base = os.path.basename(w.rstrip("/"))
        if (base == ".env" or base.startswith(".env.")) and base not in ENV_OK: return "%s may hold secrets" % base
        if re.search(r"(^|/)\.ssh/", w): return "files under .ssh are private keys"
    return None


def reason(command):
    for words, _ in hooklib.steps(command):
        r = git_reason(words) or secret_reason(words)
        if r: return r
    return None


def main():
    try:
        f = hooklib.fields(hooklib.read_input())
        if f["tool"] != "Bash" or hooklib.config("deny_guard", True) is False: return
        r = reason(f["command"])
        if r: hooklib.emit_deny("STEM guard: %s. Not run. Ask the user; only they may decide to run it (R-AUTONOMY)." % r)
    except Exception:
        return


if __name__ == "__main__":
    main()
