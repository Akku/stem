#!/usr/bin/env python3
"""Guided retro run (TASK-90 pilot): applicable steps, stored progress, resume, completion check.
Usage: scripts/retro-run.py [--root DIR] [--now ISO] <command>
  start [--stage light|full] [--first|--not-first] [--flag NAME]... [--label L]   new run (or show the existing one)
  status [--label L]                      steps, next open step, stale evidence, overall state
  version-check [--label L]               query STEM_VERSION of the repo in STEM_VERSION; records source, time, result
  decide --choice update|keep [--note T]  author's choice for a newer STEM version (never updates anything itself)
  run STEP [--arg X]...                   run the step's command (+ extra args, e.g. a since-time or --repo); stores command, exit code, log path;
                                          a step with "since": "last-retro" gets the newest committed retro notes' time unless a since-time is given
  done STEP --evidence TEXT --ref R...    analysis/decision steps: concrete result plus at least one reference
  waive STEP --reason TEXT --author-said QUOTE   only on the author's explicit word: their own chat words are stored with the reason
  revalidate [STEP...] --note T --author-said Q   author keeps stale evidence after a changed skill/step definition (stored)
  finish [--adopted N --signals N]        exit 1 while an applicable step is open, blocked, stale or undecided; when complete: stores the finish time,
                                          the retro result (adopted changes, open signals: session-start doubles the due threshold after 0/0) and one
                                          cost line for [created, finished] (stage, turns, tool calls, cache_read, output; main thread of this project's
                                          transcripts, dir override RETRO_TRANSCRIPT_DIR) for the Series line of the retro notes
Step definitions: docs/agent/retro-steps.json (only source). Run file: docs/agent/retro-runs/<label>.json (commit with the retro notes).
Offline (STEM_OFFLINE=1 or no access) is "blocked", never "current". Evidence identifies and checks completeness; it does not judge quality
and cannot stop an assistant that invents a quote or edits the run file. Exit 2: unusable input, 1: incomplete or failed step."""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, subprocess, sys, tempfile, urllib.request

STEPS, RUNS, RETROS = "docs/agent/retro-steps.json", "docs/agent/retro-runs", "docs/agent/retros"
SKILLS = ".claude/skills"
KINDS = {"version", "tech", "analysis", "decision"}
STAGES = {"base", "full", "first"}
WEAK = re.compile(r"^\W*(ja|yes|ok|okay|done|erledigt|fertig|checked|geprüft|n/?a|none|keine?)\W*$", re.I)
GOOD = {"done", "waived"}


def die(msg, code=2):
    print(f"retro-run: {msg}", file=sys.stderr)
    sys.exit(code)


def sha(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def load_json(path, what):
    try:
        return json.loads(path.read_text())
    except OSError:
        die(f"{what} missing: {path}")
    except ValueError as e:
        die(f"{what} is not valid JSON ({path}): {e}")


def load_steps(root):
    data = load_json(root / STEPS, "step definitions")
    steps = data.get("steps") if isinstance(data, dict) else None
    if not steps:
        die(f"{STEPS}: no steps")
    seen = set()
    for s in steps:
        if not isinstance(s, dict) or not s.get("id") or s["id"] in seen:
            die(f"{STEPS}: every step needs a unique id")
        seen.add(s["id"])
        if s.get("kind") not in KINDS or s.get("stage") not in STAGES or not s.get("title"):
            die(f"{STEPS}: step {s['id']}: kind, stage and title are required and must be valid")
        if s["kind"] == "tech" and not s.get("command"):
            die(f"{STEPS}: step {s['id']}: tech steps need a command")
    return steps


def slug(heading):
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", heading.strip().lower()))


def section_sha(path, anchor):
    """Hash of the `## heading` section whose slug is `anchor` (up to the next `## `); 'nosection' if absent."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return "missing"
    body, inside = [], False
    for ln in lines:
        if ln.startswith("## "):
            if inside:
                break
            inside = slug(ln[3:]) == anchor
        if inside:
            body.append(ln)
    return hashlib.sha256("\n".join(body).encode()).hexdigest()[:16] if body else "nosection"


def ref_file(step):
    """Skill file named by the step's `ref` (`retro#x` -> retro/SKILL.md, `full-stage#x` -> retro/full-stage.md), or None."""
    name, _, anchor = (step.get("ref") or "").partition("#")
    for rel in step.get("skill", []):
        r = pathlib.PurePosixPath(rel)
        if anchor and name == (r.parent.name if r.name == "SKILL.md" else r.stem):
            return rel, anchor
    return None


def fingerprint(root, step):
    """Hash of the step definition, the referenced skill section and the other skill files it names (whole): a change invalidates stored evidence."""
    h = hashlib.sha256(json.dumps(step, sort_keys=True).encode())
    files, target = {}, ref_file(step)
    for rel in step.get("skill", []):
        path = root / SKILLS / rel
        files[rel] = section_sha(path, target[1]) if target and rel == target[0] else sha(path)
        h.update(f"{rel}={files[rel]}".encode())
    return h.hexdigest()[:16], files


def applicable(step, stage, first, flags):
    if step["stage"] == "full" and stage != "full":
        return False, "light stage"
    if step["stage"] == "first" and not first:
        return False, "not the first retro"
    if step.get("when") and step["when"] not in flags:
        return False, f"flag {step['when']} not given"
    return True, ""


def now(args):
    return args.now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_path(root, label):
    return root / RUNS / f"{label}.json"


def pick_label(root, args):
    if args.label:
        return args.label
    d = root / RUNS
    runs = sorted(d.glob("*.json")) if d.exists() else []
    open_runs = [p for p in runs if json.loads(p.read_text()).get("outcome") in (None, "incomplete")]
    if open_runs:
        return open_runs[-1].stem
    return (args.now or dt.date.today().isoformat())[:10]


def load_run(root, args):
    label = pick_label(root, args)
    p = run_path(root, label)
    if not p.exists():
        die(f"no run '{label}': start one with 'start'")
    return label, p, json.loads(p.read_text())


def save(p, run):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n")


def refresh(root, run):
    """Detect changed requirements on resume: evidence of a step whose fingerprint changed becomes stale (kept as 'previous')."""
    defs = {s["id"]: s for s in load_steps(root)}
    changed = []
    for sid, st in run["steps"].items():
        if not st["applies"]:
            continue
        step = defs.get(sid)
        if step is None:
            continue
        fp, files = fingerprint(root, step)
        if fp != st["fingerprint"]:
            if st["status"] in GOOD or st["status"] in ("blocked", "needs-decision"):
                st["previous"] = {k: st.get(k) for k in ("status", "evidence", "refs", "command", "exit", "log", "waiver", "fingerprint", "files")}
                st["status"] = "stale"
            st["fingerprint"], st["files"] = fp, files
            changed.append(sid)
    return changed


def state_of(run):
    sts = [s for s in run["steps"].values() if s["applies"]]
    bad = [k for k, s in run["steps"].items() if s["applies"] and s["status"] not in GOOD]
    if run.get("outcome") in ("complete", "complete-with-exceptions") and not bad:
        return run["outcome"]
    if not bad:
        return "ready-to-finish"
    return "incomplete" if any(s["status"] != "open" for s in sts) else "not-started"


def cmd_start(root, args):
    steps = load_steps(root)
    label = pick_label(root, args) if args.label else (args.now or dt.date.today().isoformat())[:10]
    p = run_path(root, label)
    if p.exists():
        print(f"run '{label}' exists: resuming"); return cmd_status(root, argparse.Namespace(**{**vars(args), "label": label}))
    retros = root / RETROS
    first = args.first or (not args.not_first and not (retros.exists() and any(retros.glob("*.md"))))
    flags = set(args.flag or [])
    run = {"label": label, "created": now(args), "stage": args.stage, "first": first, "flags": sorted(flags),
           "stem": {"version": None, "repo": None}, "version_check": None, "outcome": None, "steps": {}}
    sv = root / "STEM_VERSION"
    if sv.exists():
        txt = sv.read_text()
        run["stem"] = {k: (re.search(rf"^{k}: *(.+)$", txt, re.M) or [None, None])[1] for k in ("version", "repo")}
    for s in steps:
        ok, why = applicable(s, args.stage, first, flags)
        fp, files = fingerprint(root, s)
        run["steps"][s["id"]] = {"applies": ok, "status": "open" if ok else "not-applicable", "reason": why,
                                 "kind": s["kind"], "title": s["title"], "ref": s.get("ref"), "fingerprint": fp, "files": files}
    save(p, run)
    print(f"run '{label}' started: stage={args.stage} first={first}")
    return cmd_status(root, argparse.Namespace(**{**vars(args), "label": label}))


def cmd_status(root, args):
    label, p, run = load_run(root, args)
    changed = refresh(root, run)
    save(p, run)
    print(f"retro run {label}: stage={run['stage']} first={run['first']} state={state_of(run)}")
    for sid, s in run["steps"].items():
        mark = {"done": "x", "waived": "~", "not-applicable": "-"}.get(s["status"], " ")
        extra = f" ({s['reason']})" if s["status"] == "not-applicable" else ""
        print(f"[{mark}] {sid}: {s['status']}{extra} - {s['title']}" + (f"  -> {s['ref']}" if s["applies"] and s["status"] != "done" and s.get("ref") else ""))
    if changed:
        print("CHANGED REQUIREMENTS (evidence invalidated, redo or waive): " + ", ".join(changed))
    nxt = next((k for k, s in run["steps"].items() if s["applies"] and s["status"] not in GOOD), None)
    print(f"next: {nxt}" if nxt else "next: finish")
    return 0


def fetch_version(repo):
    raw = os.environ.get("STEM_RETRO_VERSION_URL") or repo.replace("github.com", "raw.githubusercontent.com") + "/main/STEM_VERSION"
    with urllib.request.urlopen(raw, timeout=5) as r:
        m = re.search(r"^version: *(\S+)", r.read().decode(), re.M)
    if not m:
        raise ValueError("no version line")
    return raw, m.group(1)


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def cmd_version_check(root, args):
    label, p, run = load_run(root, args)
    refresh(root, run)
    st = next((s for s in run["steps"].values() if s["kind"] == "version" and s["applies"]), None)
    if not st:
        die("no applicable version step")
    repo, local = run["stem"].get("repo"), run["stem"].get("version")
    rec = {"source": None, "time": now(args), "local": local, "remote": None, "status": None, "error": None}
    if os.environ.get("STEM_OFFLINE"):
        rec.update(status="blocked", error="STEM_OFFLINE set; not checked, not current")
    elif not repo or not local:
        rec.update(status="blocked", error="STEM_VERSION lacks repo or version")
    else:
        try:
            rec["source"], rec["remote"] = fetch_version(repo)
            newer = vkey(rec["remote"]) > vkey(local)
            rec["status"] = "newer" if newer else "current"
        except Exception as e:  # network, parse: all are "not checked"
            rec.update(source=repo, status="blocked", error=f"{type(e).__name__}: {e}"[:200])
    run["version_check"] = rec
    if rec["status"] == "current":
        st.update(status="done", evidence=f"remote {rec['remote']} == local {local} at {rec['time']} from {rec['source']}")
    elif rec["status"] == "newer":
        st.update(status="needs-decision", evidence=f"newer STEM {rec['remote']} available (local {local}); review changes, author chooses: decide --choice update|keep")
    else:
        st.update(status="blocked", evidence=f"not checked: {rec['error']}")
    save(p, run)
    print(f"version-check: {rec['status']} (local {local}, remote {rec['remote']}, source {rec['source']}, error {rec['error']})")
    return 0 if rec["status"] in ("current", "newer") else 1


def cmd_decide(root, args):
    label, p, run = load_run(root, args)
    st = next((s for s in run["steps"].values() if s["kind"] == "version"), None)
    if not st or st["status"] != "needs-decision":
        die("no pending STEM version decision (run version-check first)")
    if not (args.note or "").strip():
        die("decide needs --note: who decided and the reason (the author's choice, not the assistant's)")
    st.update(status="done", decision=args.choice, note=args.note,
              evidence=f"author chose '{args.choice}' for STEM {run['version_check']['remote']} (local {run['version_check']['local']}): {args.note}")
    save(p, run)
    print(f"decision recorded: {args.choice}. Nothing was updated; use stem-update for 'update'. Results that depend on changed instructions: recheck after the update.")
    return 0


def get_step(run, sid):
    st = run["steps"].get(sid)
    if st is None:
        die(f"unknown step '{sid}'")
    if not st["applies"]:
        die(f"step '{sid}' is not applicable ({st['reason']})")
    return st


def has_positional(args, value_flags):
    """True when args contain a value that is neither a flag nor the value of a flag in value_flags (e.g. a since-time)."""
    it = iter(args)
    for a in it:
        if a in value_flags: next(it, None)
        elif not a.startswith("--"): return True
    return False


def last_retro_time(root):
    """Local commit time ('YYYY-MM-DD HH:MM') of the newest committed retro notes file, or None."""
    names = sorted((f.name for f in (root / RETROS).glob("*.md") if re.fullmatch(r"\d{4}-\d\d-\d\d\.md", f.name)), reverse=True)
    for n in names:
        r = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=format-local:%Y-%m-%d %H:%M", "--", f"{RETROS}/{n}"],
                           cwd=root, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip(): return r.stdout.strip()
    return None


def cmd_run(root, args):
    label, p, run = load_run(root, args)
    refresh(root, run)
    st = get_step(run, args.step)
    if st["kind"] != "tech":
        die(f"step '{args.step}' is {st['kind']}: use {'version-check' if st['kind'] == 'version' else 'done'}")
    step = next(s for s in load_steps(root) if s["id"] == args.step)
    extra = list(args.arg or [])
    if step.get("since") == "last-retro" and not has_positional(extra, step.get("value_flags") or []):
        since = last_retro_time(root)
        if since: extra.append(since)  # first retro: the command's own default
    cmd = [c.replace("{label}", label) for c in step["command"]] + extra
    logdir = pathlib.Path(os.environ.get("AGENT_LOG_DIR") or root / ".agent-logs"); logdir.mkdir(parents=True, exist_ok=True)
    log = logdir / f"retro-{label}-{args.step}.log"
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
        out, code = r.stdout + r.stderr, r.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        out, code = f"{type(e).__name__}: {e}", 127
    log.write_text(out)
    rel = os.path.relpath(log, root) if str(log).startswith(str(root)) else str(log)
    st.update(command=" ".join(cmd), exit=code, log=rel, status="done" if code == 0 else "blocked",
              evidence=f"exit {code}: {' '.join(cmd)}; log {rel}")
    save(p, run)
    print(f"{args.step}: exit {code}, log {rel}")
    print("\n".join(out.strip().splitlines()[:15]))
    return 0 if code == 0 else 1


def cmd_done(root, args):
    label, p, run = load_run(root, args)
    refresh(root, run)
    st = get_step(run, args.step)
    if st["kind"] not in ("analysis", "decision"):
        die(f"step '{args.step}' is {st['kind']}: it cannot be marked done by hand ({'run it' if st['kind'] == 'tech' else 'use version-check/decide'})")
    ev, refs = (args.evidence or "").strip(), [r for r in (args.ref or []) if r.strip()]
    if len(ev) < 20 or WEAK.match(ev):
        die("evidence must be a concrete result (at least 20 characters, not just 'yes/done')")
    if not refs:
        die("at least one --ref (task ID, commit, file, run log) is required")
    st.update(status="done", evidence=ev, refs=refs, done_at=now(args))
    save(p, run)
    print(f"{args.step}: done")
    return 0


def cmd_waive(root, args):
    label, p, run = load_run(root, args)
    st = get_step(run, args.step)
    if not (args.reason or "").strip():
        die("waive needs --reason")
    quote = (args.author_said or "").strip()
    if len(quote) < 3:
        die("waive needs --author-said: the author's own words from the chat that allow skipping this step (an assistant may propose, never decide)")
    st.update(status="waived", waiver={"reason": args.reason.strip(), "author_said": quote, "confirmed_by": "author (chat quote)", "time": now(args)})
    save(p, run)
    print(f"{args.step}: waived on the author's word (the run can only end 'complete-with-exceptions')")
    return 0


def cmd_revalidate(root, args):
    """The author decides that stale evidence still holds (e.g. a wording-only skill change): previous status and evidence return, the decision is stored."""
    label, p, run = load_run(root, args)
    refresh(root, run)
    quote = (args.author_said or "").strip()
    if len(quote) < 3 or not (args.note or "").strip():
        die("revalidate needs --note (why the change does not affect the evidence) and --author-said (the author's own words)")
    ids = args.steps or [k for k, s in run["steps"].items() if s["status"] == "stale"]
    for sid in ids:
        st = run["steps"].get(sid)
        if not st or st["status"] != "stale" or not st.get("previous"):
            die(f"step '{sid}' is not stale")
    for sid in ids:
        st = run["steps"][sid]
        prev = st.pop("previous")
        st.update({k: v for k, v in prev.items() if v is not None and k not in ("fingerprint", "files")})
        st["revalidated"] = {"note": args.note.strip(), "author_said": quote, "time": now(args)}
    save(p, run)
    print(f"revalidated on the author's word: {', '.join(ids)}")
    return 0


def cost_of(root, run):
    """Cost of the run window from context-report.py --cost (numbers only); anything unusable is stored as an error, never guessed."""
    out = {"stage": run["stage"]}
    script = pathlib.Path(__file__).resolve().parent / "context-report.py"
    cmd = [sys.executable, str(script), "--cost", "--main-only", "--since", run["created"], "--until", run["finished"]]
    if os.environ.get("RETRO_TRANSCRIPT_DIR"): cmd.append(os.environ["RETRO_TRANSCRIPT_DIR"])
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120)
        kv = dict(x.split("=", 1) for x in r.stdout.split() if "=" in x)
        out.update({k: int(kv[k]) for k in ("turns", "tool_calls", "cache_read", "output")})
    except (OSError, subprocess.TimeoutExpired, KeyError, ValueError):
        out["error"] = "not evaluable"
    return out


def cmd_finish(root, args):
    label, p, run = load_run(root, args)
    changed = refresh(root, run)
    bad = {k: s["status"] for k, s in run["steps"].items() if s["applies"] and s["status"] not in GOOD}
    if bad:
        run["outcome"] = "incomplete"
        save(p, run)
        print("NOT COMPLETE: " + ", ".join(f"{k}={v}" for k, v in bad.items()) + (f"; changed requirements: {', '.join(changed)}" if changed else ""))
        return 1
    waived = [k for k, s in run["steps"].items() if s["status"] == "waived"]
    run["outcome"] = "complete-with-exceptions" if waived else "complete"
    run["finished"] = now(args)
    if args.adopted is not None and args.signals is not None:
        run["result"] = {"adopted": args.adopted, "open_signals": args.signals}
    run["cost"] = cost_of(root, run)
    save(p, run)
    print(f"{run['outcome'].upper()}" + (f": waived by author: {', '.join(waived)}" if waived else "") + ". Completeness only; judgement of the conclusions is not checked.")
    c = run["cost"]
    print("cost: " + (f"stage={c['stage']} turns={c['turns']} tool_calls={c['tool_calls']} cache_read={c['cache_read']} output={c['output']}" if "turns" in c else f"stage={c['stage']} {c['error']}")
          + f" (window {run['created']} .. {run['finished']})")
    print("result: " + (f"adopted={run['result']['adopted']} open_signals={run['result']['open_signals']}" if "result" in run else "not recorded (pass --adopted N --signals N; the retro due threshold stays 8)"))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="."); ap.add_argument("--now")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("--stage", choices=["light", "full"], default="light")
    s.add_argument("--first", action="store_true"); s.add_argument("--not-first", action="store_true")
    s.add_argument("--flag", action="append"); s.add_argument("--label")
    for name in ("status", "version-check"):
        sub.add_parser(name).add_argument("--label")
    f = sub.add_parser("finish"); f.add_argument("--label"); f.add_argument("--adopted", type=int); f.add_argument("--signals", type=int)
    d = sub.add_parser("decide"); d.add_argument("--choice", choices=["update", "keep"], required=True); d.add_argument("--note"); d.add_argument("--label")
    r = sub.add_parser("run"); r.add_argument("step"); r.add_argument("--label"); r.add_argument("--arg", action="append")
    dn = sub.add_parser("done"); dn.add_argument("step"); dn.add_argument("--evidence"); dn.add_argument("--ref", action="append"); dn.add_argument("--label")
    rv = sub.add_parser("revalidate"); rv.add_argument("steps", nargs="*"); rv.add_argument("--note"); rv.add_argument("--author-said"); rv.add_argument("--label")
    w = sub.add_parser("waive"); w.add_argument("step"); w.add_argument("--reason"); w.add_argument("--author-said"); w.add_argument("--label")
    args = ap.parse_args()
    root = pathlib.Path(args.root).resolve()
    sys.exit({"start": cmd_start, "status": cmd_status, "version-check": cmd_version_check, "decide": cmd_decide, "run": cmd_run,
              "done": cmd_done, "waive": cmd_waive, "revalidate": cmd_revalidate, "finish": cmd_finish}[args.cmd](root, args))


if __name__ == "__main__":
    main()
