#!/usr/bin/env python3
"""Waiting tasks: report when the outside event a task waits for has happened (called by session-start.sh).
A task that is not Done declares one condition per line in its file (notes), optionally followed by ' -- <what to do>':
  Wait: reboot-since <YYYY-MM-DDTHH:MMZ> file-exists <relative path>
      met when the machine booted after that UTC time; says whether the file survived
  Wait: done-count-since <commit> <n> [labels=a,b]
      met when <n> Done tasks (with one of the labels, if given) were updated after that commit's time
Only these kinds exist; nothing from task text is executed. Unknown or malformed lines are reported, never run.
Output: 'READY: TASK-x ...' per met condition, 'WAIT PROBLEM: ...' per unusable line, nothing otherwise.
Test hook: STEM_BOOT_TIME=<epoch seconds> replaces the system boot time."""
import datetime, os, pathlib, re, subprocess, sys

UTC = datetime.timezone.utc


def front(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def field(head, name):
    m = re.search(rf"^{name}: *'?([^'\n]*)'?", head, re.M)
    return m.group(1).strip() if m else ""


def labels(head):
    m = re.search(r"^labels: *\[(.*?)\]", head, re.M)
    if m: return {x.strip(" '\"") for x in m.group(1).split(",") if x.strip()}
    m = re.search(r"^labels:\n((?: *- .*\n?)*)", head, re.M)
    return {x.strip()[2:].strip(" '\"") for x in m.group(1).splitlines()} if m else set()


def boot_time():
    if os.environ.get("STEM_BOOT_TIME"): return int(os.environ["STEM_BOOT_TIME"])
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r"sec = (\d+)", out)
        if m: return int(m.group(1))
    except (OSError, subprocess.SubprocessError): pass
    try:
        for line in pathlib.Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "): return int(line.split()[1])
    except OSError: pass
    return None


def commit_time(rev):
    out = subprocess.run(["git", "log", "-1", "--format=%ct", rev, "--"], capture_output=True, text=True)
    return int(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def utc(ts):
    return datetime.datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M")


def check(tid, args, tasks):
    """Returns (ready message or None, problem or None)."""
    kind = args[0] if args else ""
    if kind == "reboot-since":
        if len(args) != 4 or args[2] != "file-exists" or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\dZ", args[1]):
            return None, "expected 'reboot-since <YYYY-MM-DDTHH:MMZ> file-exists <path>'"
        path = pathlib.PurePosixPath(args[3])
        if path.is_absolute() or ".." in path.parts: return None, "file-exists needs a relative path inside the project"
        since = datetime.datetime.strptime(args[1], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC).timestamp()
        boot = boot_time()
        if boot is None: return None, "boot time unknown on this machine"
        if boot <= since: return None, None
        state = "exists" if pathlib.Path(args[3]).exists() else "is MISSING"
        return f"rebooted {utc(boot)} UTC (after {args[1]}); {args[3]} {state}", None
    if kind == "done-count-since":
        if len(args) not in (3, 4) or not re.fullmatch(r"[0-9a-f]{7,40}", args[1]) or not args[2].isdigit() \
                or (len(args) == 4 and not args[3].startswith("labels=")):
            return None, "expected 'done-count-since <commit> <n> [labels=a,b]'"
        ct = commit_time(args[1])
        if ct is None: return None, f"commit {args[1]} not found"
        want = set(args[3][7:].split(",")) if len(args) == 4 else None
        since = utc(ct)
        done = [t for t, (st, upd, lab) in tasks.items()
                if t != tid and st == "Done" and upd > since and (want is None or want & lab)]
        if len(done) < int(args[2]): return None, None
        return f"{len(done)} of {args[2]} Done tasks{' (' + args[3] + ')' if want else ''} since {args[1]}", None
    return None, f"unknown kind '{kind}' (not run)"


def main():
    files = sorted(pathlib.Path("backlog/tasks").glob("task-*.md"))
    tasks, waits = {}, []
    for f in files:
        text = f.read_text(errors="replace"); head = front(text)
        tid = field(head, "id") or f.name
        tasks[tid] = (field(head, "status"), field(head, "updated_date") or field(head, "created_date"), labels(head))
        if tasks[tid][0] == "Done": continue
        for line in text.splitlines():
            m = re.match(r"\s*Wait:\s*(.*)$", line)
            if m:
                cond, _, todo = m.group(1).partition(" -- ")
                waits.append((tid, cond.split(), todo.strip()))
    for tid, args, todo in waits:
        msg, problem = check(tid, args, tasks)
        if problem: print(f"WAIT PROBLEM: {tid}: {problem}")
        elif msg: print(f"READY: {tid} {msg}" + (f" -> {todo}" if todo else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
