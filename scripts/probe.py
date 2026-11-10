#!/usr/bin/env python3
"""Usage probes (docs/agent/PROBES.md): prove by a log line that a feature ran in a real session.
  probe.py fire <TASK-n#k> --at <location>   append a line to docs/agent/probes.jsonl; never fails the caller;
                                             writes nothing when STEM_TEST=1 or CI is set (test runs never confirm)
  probe.py report                            one line for session start: 'probes: N open, M fired (ids)'; silent without probes
  probe.py orphans [--sessions N]            open probes older than N sessions (default 10; session = distinct commit date after the marker was added)
Log line keys: id, ts, at (no content). Probes are unchecked ACs with '[probe: <task>#<ac>]' in the Acceptance Criteria section."""
import datetime, json, os, pathlib, re, subprocess, sys

LOG = "docs/agent/probes.jsonl"
ID = r"(TASK-\d+)#(\d+)"
AC_LINE = re.compile(rf"^- \[( |x)\] #(\d+) .*\[probe: {ID}\]\s*$")


def root():
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return pathlib.Path(r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else ".")


def fire(args):
    try:
        if os.environ.get("STEM_TEST") == "1" or os.environ.get("CI"): return 0
        if not args or not re.fullmatch(ID, args[0]) or "--at" not in args or args.index("--at") + 1 >= len(args): return 0
        at = args[args.index("--at") + 1][:200]
        line = json.dumps({"id": args[0], "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "at": at},
                          separators=(",", ":"))
        p = root() / LOG
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f: f.write(line + "\n")
    except Exception:
        pass
    return 0


def fired_ids(base):
    ids = set()
    try:
        for ln in (base / LOG).read_text().splitlines():
            try: ids.add(json.loads(ln)["id"])
            except (ValueError, KeyError, TypeError): pass
    except OSError: pass
    return ids


def open_probes(base):
    """[(probe id, task file)] for unchecked ACs with a valid marker (id names its own task and AC number)."""
    out = []
    for f in sorted((base / "backlog/tasks").glob("*.md")):
        text = f.read_text(errors="replace")
        m = re.search(r"<!-- AC:BEGIN -->(.*?)<!-- AC:END -->", text, re.S)
        tid = re.search(r"^id: *(\S+)", text, re.M)
        if not m or not tid: continue
        for ln in m.group(1).splitlines():
            a = AC_LINE.match(ln)
            if a and a.group(1) == " " and a.group(4) == a.group(2) and a.group(3).upper() == tid.group(1).upper():
                out.append((f"{a.group(3)}#{a.group(4)}", f))
    return out


def report(base):
    probes = open_probes(base)
    if not probes: return 0
    done = fired_ids(base)
    fired = [i for i, _ in probes if i in done]
    msg = f"probes: {len(probes) - len(fired)} open, {len(fired)} fired"
    if fired: msg += f" ({', '.join(fired)}): check the log line, add the evidence line, close the AC, remove marker and probe call (docs/agent/PROBES.md)"
    print(msg)
    return 0


def orphans(base, sessions):
    done = fired_ids(base)
    for pid, f in open_probes(base):
        if pid in done: continue
        r = subprocess.run(["git", "log", "--reverse", "--format=%H", "-S", f"[probe: {pid}]", "--", str(f)], capture_output=True, text=True, cwd=base)
        first = r.stdout.split()[:1]
        if not first: continue
        d = subprocess.run(["git", "log", "--format=%cs", f"{first[0]}..HEAD"], capture_output=True, text=True, cwd=base).stdout.split()
        n = len(set(d))
        if n >= sessions: print(f"{pid}: {n} sessions without firing ({f.name})")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "fire": return fire(argv[2:])
    if cmd == "report": return report(root())
    if cmd == "orphans":
        n = int(argv[argv.index("--sessions") + 1]) if "--sessions" in argv else 10
        return orphans(root(), n)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
