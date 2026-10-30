#!/usr/bin/env python3
"""Proposes extra retro topics (TASK-91 harness design). Called at the start of a retro (skill `retro`).
Usage: scripts/retro-topics.py [--retro LABEL] [--dry-run] [--fill N] [--root DIR] [--now YYYY-MM-DD]
Catalog: docs/agent/retro-topics.json (STEM-owned) + docs/agent/retro-topics.local.json (project-owned; same id replaces,
"disabled": true removes). State: docs/agent/retro-topics-state.json (commit it with the retro notes).
Selection: (1) due triggers, (2) topics whose signal fired (strongest first), both without cap; then fill up to N (default 2) with
(3) never-given `once` topics and, only when no such topic is left, (4) `repeatable` topics, longest ago first.
A topic given in the previous retro is skipped for signals (`cooldown_retros`). Re-running with the same --retro label repeats
the earlier answer (resumable). --dry-run records nothing. Exit 2: unusable catalog or state."""
import argparse, datetime as dt, json, pathlib, re, subprocess, sys

CATALOG, LOCAL, STATE = "docs/agent/retro-topics.json", "docs/agent/retro-topics.local.json", "docs/agent/retro-topics-state.json"
KINDS = {"once", "repeatable"}


def die(msg):
    print(f"retro-topics: {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path, what, default=None):
    if not path.exists():
        if default is not None:
            return default
        die(f"{what} missing: {path}")
    try:
        return json.loads(path.read_text())
    except ValueError as e:
        die(f"{what} is not valid JSON ({path}): {e}")


def load_catalog(root):
    topics = {}
    for rel, required in ((CATALOG, True), (LOCAL, False)):
        p = root / rel
        if not p.exists() and not required:
            continue
        data = load_json(p, "catalog")
        for t in data.get("topics", []) if isinstance(data, dict) else []:
            if not isinstance(t, dict) or not t.get("id"):
                die(f"{rel}: every topic needs an id")
            if t.get("disabled"):
                topics.pop(t["id"], None)
                continue
            if t.get("kind") not in KINDS:
                die(f"{rel}: topic {t['id']}: kind must be one of {sorted(KINDS)}")
            if not t.get("title") or not t.get("ask"):
                die(f"{rel}: topic {t['id']}: title and ask are required")
            topics[t["id"]] = t
    if not topics:
        die("catalog has no topics")
    return list(topics.values())


def front(path):
    m = re.match(r"---\n(.*?)\n---", path.read_text(), re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        k, _, v = line.partition(":")
        if v.strip() and not line.startswith(" "):
            out[k.strip()] = v.strip().strip("'\"")
    return out


def tasks(root):
    return [dict(front(p), _path=p) for p in sorted((root / "backlog/tasks").glob("task-*.md"))]


def sh(root, *cmd):
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def day(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


class Ctx:
    def __init__(self, root, state, now):
        self.root, self.state, self.now = root, state, now
        self.tasks = tasks(root)

    def last_run(self, tid):
        for run in reversed(self.state["runs"]):
            if tid in run["topics"]:
                return day(run["date"])
        return None

    def done_since(self, since):
        return sum(1 for t in self.tasks if t.get("status") == "Done" and (since is None or (day(t.get("updated_date") or t.get("created_date")) or dt.date.min) > since))

    def count(self, status):
        return sum(1 for t in self.tasks if t.get("status") == status)


def sig_done_since_topic(c, t, p):
    n = c.done_since(c.last_run(t["id"]))
    return n, p["min"], f"{n} Done tasks since this topic last ran (threshold {p['min']})"


def sig_days_since_topic(c, t, p):
    last = c.last_run(t["id"])
    n = p["min"] if last is None else (c.now - last).days  # never discussed counts as exactly due
    return n, p["min"], ("never discussed" if last is None else f"{n} days since this topic last ran") + f" (threshold {p['min']})"


def sig_status_count(c, t, p):
    n = c.count(p["status"])
    return n, p["min"], f"{n} tasks '{p['status']}' (threshold more than {p['min']})", n > p["min"]


def sig_file_pct(c, t, p):
    f = c.root / p["path"]
    n = round(100 * f.stat().st_size / p["limit_bytes"]) if f.exists() else 0
    return n, p["min_pct"], f"{p['path']} is {n} % of its {p['limit_bytes']} byte limit (threshold {p['min_pct']} %)"


def sig_file_over(c, t, p):
    f = c.root / p["path"]
    n = f.stat().st_size if f.exists() else 0
    return n, p["bytes"], f"{p['path']} is {n} bytes (threshold more than {p['bytes']})", n > p["bytes"]


def sig_files_growth(c, t, p):
    """Growth against the sizes recorded when the topic last ran; no earlier record means no signal."""
    base = c.state["sizes"].get(t["id"], {})
    worst, why = 0, "no earlier size recorded"
    for rel in p["paths"]:
        f = c.root / rel
        if f.exists() and base.get(rel):
            g = round(100 * (f.stat().st_size - base[rel]) / base[rel])
            if g >= worst:
                worst, why = g, f"{rel} grew {g} % since this topic last ran (threshold {p['min_pct']} %)"
    return worst, p["min_pct"], why


def sig_git_state(c, t, p):
    changes = sh(c.root, "git", "status", "--porcelain")
    unpushed = sh(c.root, "git", "rev-list", "--count", "@{u}..HEAD")
    nc = len(changes.splitlines()) if changes else 0
    nu = int(unpushed) if unpushed and unpushed.isdigit() else 0
    n = nc + nu
    return n, p["min"], f"{nc} uncommitted file(s) + {nu} unpushed commit(s) (threshold more than {p['min']})", n > p["min"]


def sig_vision(c, t, p):
    docs = [d for d in (c.root / "backlog/docs").glob("*") if "vision" in d.name.lower()] if (c.root / "backlog/docs").is_dir() else []
    if not docs:
        return 1, 1, "no vision document in backlog/docs"
    ts = sh(c.root, "git", "log", "-1", "--format=%cs", "--", str(docs[0].relative_to(c.root)))
    age = (c.now - (day(ts) or c.now)).days
    if age > p["max_age_days"]:
        return age, p["max_age_days"], f"vision {docs[0].name} unchanged for {age} days (threshold {p['max_age_days']})", True
    todo = {t.get("milestone") for t in c.tasks if t.get("status") == "To Do"}
    ms = [m for m in sorted((c.root / "backlog/milestones").glob("*.md"))] if (c.root / "backlog/milestones").is_dir() else []
    empty = [front(m).get("id") for m in ms if front(m).get("id") not in todo]
    if empty:
        return len(empty), 1, f"milestone(s) without To Do tasks: {', '.join(empty)}", True
    return 0, 1, "vision recent, every milestone has To Do tasks", False


def sig_cmd_version(c, t, p):
    """New version of an installed CLI since the topic last ran. A missing command or no earlier record means no signal."""
    base = c.state["sizes"].get(t["id"], {})
    changed = []
    for cmd in p["cmds"]:
        v = sh(c.root, cmd, "--version")
        if v and base.get(cmd) and base[cmd] != v:
            changed.append(f"{cmd} {base[cmd]} -> {v}")
    return len(changed), 1, "; ".join(changed) or "no CLI version change recorded", bool(changed)


def sig_learning_words(c, t, p):
    since, n = c.last_run(t["id"]), 0
    for tk in c.tasks:
        if since and (day(tk.get("updated_date") or tk.get("created_date")) or dt.date.min) <= since:
            continue
        for line in tk["_path"].read_text().splitlines():
            if "Learning:" in line and re.search(p["words"], line, re.I):
                n += 1
    return n, p["min"], f"{n} Learning notes mention a skipped or ignored rule (threshold {p['min']})"


def sig_done_total(c, t, p):
    n = c.done_since(None)
    return n, p["min"], f"{n} Done tasks in total (fixed trigger at {p['min']})"


def sig_done_since_commit(c, t, p):
    ts = sh(c.root, "git", "log", "-1", "--format=%cs", p["commit"])
    n = c.done_since(day(ts)) if ts else 0
    return n, p["min"], f"{n} Done tasks since commit {p['commit']} (fixed trigger at {p['min']})"


SIGNALS = {k[4:]: v for k, v in globals().items() if k.startswith("sig_")}


def evaluate(c, t):
    """Returns (kind, fired, ratio, reason) for the trigger or signal of topic t, or None when it has neither.
    A list of signals fires when any one does (strongest wins)."""
    for key in ("trigger", "signal"):
        specs = t.get(key)
        if specs is None:
            continue
        results = []
        for spec in specs if isinstance(specs, list) else [specs]:
            fn = SIGNALS.get(spec.get("type"))
            if fn is None:
                die(f"topic {t['id']}: unknown {key} type {spec.get('type')!r}")
            try:
                res = fn(c, t, spec)
            except KeyError as e:
                die(f"topic {t['id']}: {key} misses parameter {e}")
            value, limit, reason = res[:3]
            results.append((res[3] if len(res) > 3 else value >= limit, value / limit if limit else 1.0, reason))
        fired, ratio, reason = max(results, key=lambda r: (r[0], r[1]))
        return key, fired, ratio, reason
    return None


def select(c, topics, fill):
    cooldown_hit = lambda t: any(t["id"] in r["topics"] for r in c.state["runs"][-t.get("cooldown_retros", 1):])
    due, signal, once, rep = [], [], [], []
    for t in topics:
        ev = evaluate(c, t)
        last = c.last_run(t["id"])
        if ev and ev[1] and ev[0] == "trigger" and (last is None or t["kind"] == "repeatable") and not cooldown_hit(t):
            due.append((ev[2], t, "due", ev[3]))
        elif ev and ev[1] and ev[0] == "signal" and not cooldown_hit(t) and (t["kind"] == "repeatable" or last is None):
            signal.append((ev[2], t, "signal", ev[3]))
        elif t["kind"] == "once" and last is None and not (ev and ev[0] == "trigger"):
            once.append((0, t, "once", "not given yet" + (f"; {ev[3]}" if ev else "")))
        elif t["kind"] == "repeatable" and not cooldown_hit(t) and not (ev and ev[0] == "trigger"):
            rep.append((last or dt.date.min, t, "rotation", "rotation: " + ("never given" if last is None else f"last given {last}")))
    picked = sorted(due, key=lambda x: -x[0]) + sorted(signal, key=lambda x: -x[0])
    for pool in (once, [] if once else sorted(rep, key=lambda x: x[0])):  # repeatable topics return only after every once topic was given
        for item in pool:
            if len(picked) >= fill:
                break
            picked.append(item)
    return [(t, why, reason) for _, t, why, reason in picked]


def sizes_for(c, topics):
    out = {}
    for t in topics:
        s = t.get("signal") or []
        for spec in s if isinstance(s, list) else [s]:
            if spec.get("type") == "files_growth":
                out.setdefault(t["id"], {}).update({r: (c.root / r).stat().st_size for r in spec["paths"] if (c.root / r).exists()})
            if spec.get("type") == "cmd_version":
                out.setdefault(t["id"], {}).update({cmd: v for cmd in spec["cmds"] if (v := sh(c.root, cmd, "--version"))})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--retro"), ap.add_argument("--dry-run", action="store_true"), ap.add_argument("--fill", type=int, default=2)
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent)), ap.add_argument("--now")
    a = ap.parse_args()
    root = pathlib.Path(a.root)
    now = day(a.now) if a.now else dt.date.today()
    if now is None:
        die("--now must be YYYY-MM-DD")
    label = a.retro or now.isoformat()
    state_path = root / STATE
    state = load_json(state_path, "state", {"runs": [], "sizes": {}})
    if not isinstance(state.get("runs"), list) or not isinstance(state.get("sizes", {}), dict):
        die(f"state has an unexpected shape: {state_path}")
    state.setdefault("sizes", {})
    topics = load_catalog(root)
    by_id = {t["id"]: t for t in topics}
    c = Ctx(root, state, now)
    earlier = next((r for r in state["runs"] if r["retro"] == label), None)
    if earlier:
        chosen = [(by_id[i], "given-before", earlier["reasons"].get(i, "")) for i in earlier["topics"] if i in by_id]
        note = f"retro {label}: topics were already given, repeated unchanged"
    else:
        chosen = select(c, topics, a.fill)
        note = f"retro {label}: {len(chosen)} topic(s)" + (" (dry run, nothing recorded)" if a.dry_run else "")
        if not a.dry_run:
            state["runs"].append({"retro": label, "date": now.isoformat(), "topics": [t["id"] for t, _, _ in chosen], "reasons": {t["id"]: r for t, _, r in chosen}})
            state["sizes"].update(sizes_for(c, [t for t, _, _ in chosen]))
            state_path.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    print(f"## retro topics\n{note}")
    for t, why, reason in chosen:
        print(f"\nTOPIC {t['id']} [{why}] {t['title']}\n  reason: {reason}\n  ask: {t['ask']}")
    if not chosen:
        print("no topic is due or has a signal; nothing to add")


if __name__ == "__main__":
    main()
