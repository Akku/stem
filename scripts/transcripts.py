"""Shared transcript helpers for the context tools (TASK-345): where Claude Code keeps this project's transcripts and how to read a time argument.
Imported by context-report.py, start-context.py, context-check.py, metrics-explorer.py (through context-report) and tron.py."""
import datetime as dt, glob, os, re, sys


def slug(cwd):
    """Claude Code names a project's transcript folder after its directory, every non-alphanumeric character as '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def project_dirs(cwd=None, base=None):
    """This project's transcript folders: the main checkout's plus its worktrees' (<main>--claude-worktrees-*); also when run from a worktree. TASK-220."""
    base = base or os.path.expanduser("~/.claude/projects/")
    main = slug(cwd or os.getcwd()).split("--claude-worktrees-")[0]
    return [base + main] + sorted(glob.glob(glob.escape(base + main) + "--claude-worktrees-*"))


def utc_since(since, who="transcripts"):
    """--since/--until: ISO time; without offset it is local time (date only = local midnight), Z or +HH:MM marks the zone.
    Returns "YYYY-MM-DDTHH:MM:SS" UTC to compare with transcript timestamps; unparsable input stops the run."""
    try: t = dt.datetime.fromisoformat(re.sub(r"Z$", "+00:00", since.strip()))  # Z: Python < 3.11
    except ValueError: sys.exit("%s: cannot parse time %r (use YYYY-MM-DD[ HH:MM] local or ISO with Z/offset)" % (who, since))
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
