#!/usr/bin/env python3
"""Tron mode runner (R-TRON, docs/agent/ADVANCED.md): hands one approved milestone to unattended agent sessions.

  scripts/tron.py run --milestone m-4 [--dry-run] [--run-id ID] [--max-tasks N] [--config FILE]

One fresh agent process per task, started from a command template in docs/agent/stem-config.json (key "tron").
The runner works on the branch tron/<milestone>, writes a journal docs/agent/tron/run-<id>.json and never
publishes anything: it does not push, tag or merge. State lives in git and the backlog.
Config example (spike TASK-265: inside the sandbox only; Bash is allowed in full there, the container is the boundary):
  {"tron": {"worker_cmd": ["claude", "-p", "{prompt}", "--session-id", "{session_id}", "--output-format", "json",
            "--max-budget-usd", "2", "--max-turns", "40", "--permission-mode", "dontAsk",
            "--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep"],
            "worker_model": "optional name when the output does not report one"}}
Placeholders: {prompt} {session_id} {task_id} {run_id} {milestone}. Roles: worker, evaluator, doctor, planner, retro
(key <role>_cmd; a missing one falls back to worker_cmd).
Python standard library only (macOS and Linux)."""
import argparse, datetime, hashlib, json, os, pathlib, re, subprocess, sys, uuid

ROLES = ("worker", "evaluator", "doctor", "planner", "retro")
DEFAULT_PROMPT = ("Work on backlog task {task_id} following AGENTS.md. This is an unattended Tron mode session "
                  "(STEM_TRON=1): read R-TRON first and follow it; nobody answers questions. Work on this one task only.")
JOURNAL_DIR = pathlib.Path("docs/agent/tron")
# files a session must not change: the gate itself, the config, the decision frame, the invariants, the evaluator (R-TRON)
PROTECTED = ("scripts/tron.py", "docs/agent/stem-config.json", "docs/agent/DECISION_FRAME.md", "docs/agent/INVARIANTS.md",
             ".claude/agents/evaluator.md")
BASELINE_PROMPT = ("The verification command fails on the current branch before any task starts (unattended Tron mode session, "
                   "STEM_TRON=1; read R-TRON first). Find the cause and fix it with the smallest change. Do not change acceptance "
                   "criteria and do not start task work.")


class TronError(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(root, path=None):
    cfg_path = pathlib.Path(path) if path else root / "docs/agent/stem-config.json"
    if not cfg_path.is_file():
        raise TronError(f"config missing: {cfg_path} (needs a key 'tron' with 'worker_cmd' and 'verify_cmd')")
    try:
        cfg = json.loads(cfg_path.read_text())
    except ValueError as e:
        raise TronError(f"config unreadable: {cfg_path}: {e}")
    tron = cfg.get("tron")
    if not isinstance(tron, dict) or not tron.get("worker_cmd"):
        raise TronError(f"config {cfg_path}: key 'tron.worker_cmd' missing (command template as a list of strings)")
    v = tron.get("verify_cmd")
    if not (isinstance(v, list) and v and all(isinstance(a, str) for a in v)):
        raise TronError(f"config {cfg_path}: key 'tron.verify_cmd' missing (the project's verification command via scripts/run.sh, as a list)")
    for role in ROLES:
        c = tron.get(f"{role}_cmd")
        if c is not None and not (isinstance(c, list) and c and all(isinstance(a, str) for a in c)):
            raise TronError(f"config {cfg_path}: tron.{role}_cmd must be a non-empty list of strings")
    return tron


def command_for(tron, role):
    """Command template of a role; a missing one falls back to worker_cmd."""
    return tron.get(f"{role}_cmd") or tron["worker_cmd"]


def fill(template, values):
    out = []
    for arg in template:
        for k, v in values.items():
            arg = arg.replace("{" + k + "}", str(v))
        out.append(arg)
    return out


def sh(cmd, cwd, check=False):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise TronError(f"{' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r


def ready_tasks(root, milestone):
    """Ready tasks of the milestone in backlog order (unblocked, dependencies done)."""
    r = sh(["backlog", "task", "list", "-m", milestone, "--ready", "--plain"], root)
    if r.returncode:
        raise TronError(f"backlog task list failed: {(r.stderr or r.stdout).strip()[:300]}")
    ids = []
    for line in r.stdout.splitlines():
        m = re.search(r"\b(TASK-\d+) - ", line)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def prepare_branch(root, milestone, dry):
    branch = f"tron/{milestone}"
    exists = sh(["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}"], root).returncode == 0
    cur = sh(["git", "branch", "--show-current"], root).stdout.strip()
    if dry:
        return branch, exists
    dirty = [l for l in sh(["git", "status", "--porcelain", "--", ".", *EXCLUDE], root).stdout.splitlines() if l.strip()]
    if dirty:
        raise TronError("working tree is not clean; commit or stash first (the run starts on its own branch)")
    if cur == branch:
        return branch, exists
    sh(["git", "checkout", "-q", branch] if exists else ["git", "checkout", "-q", "-b", branch], root, check=True)
    return branch, exists


def transcript_path(cwd, session_id, home=None):
    """Claude Code keeps transcripts at ~/.claude/projects/<cwd with non-alphanumerics as '-'>/<session>.jsonl."""
    home = pathlib.Path(home or os.path.expanduser("~"))
    return home / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd)) / f"{session_id}.jsonl"


def parse_output(text):
    """Cost, session id and model from an agent's JSON output (claude --output-format json); empty when not JSON."""
    try:
        d = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(d, dict):
        return {}
    out = {}
    if isinstance(d.get("total_cost_usd"), (int, float)):
        out["cost_usd"] = d["total_cost_usd"]
    if isinstance(d.get("session_id"), str):
        out["session_id"] = d["session_id"]
    mu = d.get("modelUsage")
    if isinstance(mu, dict) and mu:
        out["model"] = ", ".join(sorted(mu))
    return out


def write_journal(path, journal):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(journal, indent=1) + "\n")
    os.replace(tmp, path)


def run_session(root, tron, role, task_id, run_id, milestone, prompt=None):
    """Start one agent process for one task and return its journal entry."""
    session_id = str(uuid.uuid4())
    prompt = prompt or tron.get("prompt", DEFAULT_PROMPT).replace("{task_id}", task_id)
    cmd = fill(command_for(tron, role), {"prompt": prompt, "session_id": session_id, "task_id": task_id,
                                         "run_id": run_id, "milestone": milestone})
    env = dict(os.environ, STEM_TRON="1", STEM_TRON_RUN=run_id, STEM_TRON_TASK=task_id)
    entry = {"task": task_id, "role": role, "start": now(), "command": cmd}
    try:
        r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
        entry["exit_code"] = r.returncode
        info = parse_output(r.stdout)
        if r.returncode:
            entry["stderr_tail"] = (r.stderr or "").strip()[-300:]
    except OSError as e:
        entry["exit_code"] = 127
        entry["stderr_tail"] = str(e)[:300]
        info = {}
    entry["end"] = now()
    entry["session_id"] = info.get("session_id", session_id)
    entry["cost_usd"] = info.get("cost_usd")
    entry["model"] = info.get("model") or tron.get(f"{role}_model")
    tp = transcript_path(root, entry["session_id"])
    entry["transcript"] = str(tp)
    entry["transcript_exists"] = tp.is_file()
    return entry


# ---- gate (runner side; the session only proposes Done) ----

def git_ok(root, *args):
    """Run git; a failing command is an error, never an empty answer that looks like 'nothing changed'."""
    r = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root, capture_output=True, text=True)
    if r.returncode:
        raise TronError(f"git {' '.join(args[:2])} failed: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout


def head(root):
    return git_ok(root, "rev-parse", "HEAD").strip()


def branch_refs(root):
    """{branch: commit} of all local branches."""
    out = {}
    for line in git_ok(root, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads").splitlines():
        name, _, sha = line.rpartition(" ")
        out[name] = sha
    return out


def task_files(root):
    out = {}
    for p in sorted((root / "backlog/tasks").glob("task-*.md")):
        m = re.match(r"task-(\d+) - ", p.name)
        if m:
            out[f"TASK-{m.group(1)}"] = p
    return out


def parse_task(text):
    """Status, acceptance criteria [(checked, number, text)] and notes of a backlog task file."""
    m = re.search(r"^status: *(.+?) *$", text, re.M)
    block = re.search(r"<!-- AC:BEGIN -->(.*?)<!-- AC:END -->", text, re.S)
    acs = [(c.lower() == "x", int(n), s.strip()) for c, n, s in
           re.findall(r"^- \[([ xX])\] #(\d+) (.*)$", block.group(1) if block else "", re.M)]
    notes = re.search(r"<!-- SECTION:NOTES:BEGIN -->(.*?)<!-- SECTION:NOTES:END -->", text, re.S)
    return (m.group(1).strip("'\"") if m else None), acs, (notes.group(1) if notes else "")


def ac_hash(text):
    acs = parse_task(text)[1]
    return hashlib.sha256("\n".join(f"{n} {s}" for _, n, s in acs).encode()).hexdigest()


def snapshot_acs(root):
    return {i: ac_hash(p.read_text()) for i, p in task_files(root).items()}


def start_text(root, task_id, start_commit):
    """Task file text of the run-start commit, found by task id (the file may have been renamed since)."""
    n = task_id.split("-")[1]
    for f in git_ok(root, "ls-tree", "-r", "--name-only", start_commit, "backlog").splitlines():
        if re.match(rf"backlog/(tasks|completed|archive/tasks)/task-{n} - ", f):
            return git_ok(root, "show", f"{start_commit}:{f}")
    return None


def restore_acs(root, task_id, path, start_commit):
    """Put the AC block of the run-start commit back into the task file and commit the restoration."""
    try:
        old = start_text(root, task_id, start_commit)
        pat = re.compile(r"<!-- AC:BEGIN -->.*?<!-- AC:END -->", re.S)
        blk = pat.search(old or "")
        cur = path.read_text()
        if not blk or not pat.search(cur):
            return False
        path.write_text(pat.sub(lambda _: blk.group(0), cur, count=1))
        rel = path.relative_to(root).as_posix()
        git_ok(root, "add", "--", rel)
        git_ok(root, "commit", "-q", "-m", f"{task_id}: Tron gate restored the acceptance criteria", "--", rel)
        return True
    except TronError:
        return False


# run output the runner itself writes; every other path under docs/agent/tron/ counts as a change
EXCLUDE = [":(exclude,glob)docs/agent/tron/run-*", ":(exclude,glob)docs/agent/tron/REPORT-*"]
RUNNER_FILE = re.compile(r"^docs/agent/tron/(run-|REPORT-)")


def tree_dirty(root):
    lines = [l for l in git_ok(root, "status", "--porcelain", "--", ".", *EXCLUDE).splitlines() if l.strip()]
    # edits hidden from status (assume-unchanged / skip-worktree) still change what the next session runs
    lines += ["hidden: " + l[2:] for l in git_ok(root, "ls-files", "-v").splitlines() if l[:1].islower() or l[:1] == "S"]
    return lines


def changed_paths(root, base):
    """Paths changed since base: committed, uncommitted, new, deleted; renames count as delete plus add."""
    a = git_ok(root, "diff", "--name-only", "--no-renames", base).splitlines()
    b = git_ok(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({x for x in a + b if x and not RUNNER_FILE.match(x)})


def deleted_paths(root, base):
    return [x for x in git_ok(root, "diff", "--name-only", "--no-renames", "--diff-filter=D", base).splitlines() if x]


def added_lines(root, base):
    """{file: [added lines]} since base, including untracked files."""
    out, cur = {}, None
    for line in git_ok(root, "diff", "-U0", "--no-renames", base).splitlines():
        if line.startswith("+++ "):
            cur = line[6:].rstrip("\t") if line.startswith("+++ b/") else None
        elif cur and line.startswith("+"):
            out.setdefault(cur, []).append(line[1:])
    for f in git_ok(root, "ls-files", "--others", "--exclude-standard").splitlines():
        p = root / f
        if RUNNER_FILE.match(f) or not p.is_file() or p.stat().st_size > 200_000:
            continue
        try:
            out[f] = p.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            pass
    return out


PLACEHOLDER = re.compile(r"\b(TODO|stub|NotImplemented\w*)\b", re.I)
EMPTY_BODY = (re.compile(r"def\s+\w+\s*\([^)]*\)[^\n]*:\s*(\n\s*(\"\"\"[^\n]*\"\"\"\s*\n\s*)?)?(pass|\.\.\.)\s*(\n|$)"),
              re.compile(r"(function\s*\w*\s*\([^)]*\))\s*\{\s*\}"))


def scan_placeholders(root, base):
    """Hits for TODO, stub, NotImplemented and empty function bodies in the lines a session added (a hint, not a verdict)."""
    hits = []
    for f, lines in sorted(added_lines(root, base).items()):
        if f.startswith("backlog/") or f.endswith(".md") and not f.endswith("SKILL.md"):
            continue
        for l in lines:
            if PLACEHOLDER.search(l):
                hits.append({"file": f, "kind": "marker", "line": l.strip()[:120]})
        body = "\n".join(lines)
        for rx in EMPTY_BODY:
            for m in rx.finditer(body):
                hits.append({"file": f, "kind": "empty body", "line": " ".join(m.group(0).split())[:120]})
    return hits


def verify(root, tron):
    try:
        r = subprocess.run(tron["verify_cmd"], cwd=root, capture_output=True, text=True)
    except OSError as e:
        return 127, f"verify_cmd could not start: {e}"
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()[-300:]


def protected_paths(root, tron):
    """Gate and config files plus the files that decide the verdict: run.sh and every repo file named in verify_cmd."""
    prot = set(PROTECTED) | {"scripts/run.sh"} | set(tron.get("protected", []))
    for arg in tron["verify_cmd"]:
        p = (root / arg)
        try:
            if arg and p.is_file() and root.resolve() in p.resolve().parents:
                prot.add(p.resolve().relative_to(root.resolve()).as_posix())
        except OSError:
            pass
    return prot


STOPPING = {"tree", "ac_freeze", "protected", "branch", "refs", "git"}  # damage on the branch: the run stops (until TASK-269 adds Blocked)


def gate(root, tron, task_id, base, acs_before, start_commit, branch, refs0):
    """Checks after a session: verify, Done state, evidence, clean tree, frozen ACs, protected paths, branch and refs.
    task_id None: baseline repair session."""
    fails = []
    code, tail = verify(root, tron)
    if code:
        fails.append({"check": "verify", "reason": f"verification exited {code}", "detail": tail})
    try:
        files = task_files(root)
        if task_id:
            path = files.get(task_id)
            status, acs, notes = parse_task(path.read_text()) if path else (None, [], "")
            if status != "Done":
                fails.append({"check": "status", "reason": f"status is {status}, not Done"})
            for ticked, n, _ in acs:
                if not ticked:
                    fails.append({"check": "ac", "reason": f"AC#{n} is not ticked"})
                elif not re.search(rf"^\s*AC#{n}: E2 +\S", notes, re.M):
                    fails.append({"check": "evidence", "reason": f"AC#{n} has no 'AC#{n}: E2 <pointer>' line in the notes"})
            if not acs:
                fails.append({"check": "ac", "reason": "task has no acceptance criteria"})
        cur = git_ok(root, "branch", "--show-current").strip()
        if cur != branch:
            fails.append({"check": "branch", "reason": f"session left the run branch (now on '{cur or 'detached HEAD'}', expected {branch})"})
        elif subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=root).returncode:
            fails.append({"check": "branch", "reason": "history rewritten: the commit before the session is no longer an ancestor of HEAD"})
        other = {k: v for k, v in branch_refs(root).items() if k != branch}
        if other != {k: v for k, v in refs0.items() if k != branch}:
            fails.append({"check": "refs", "reason": "other branches changed during the run: " +
                          ", ".join(sorted(k for k in set(other) | set(refs0) if other.get(k) != refs0.get(k) and k != branch))})
        dirty = tree_dirty(root)
        if dirty:
            fails.append({"check": "tree", "reason": f"working tree not clean ({len(dirty)} entries)", "detail": "; ".join(dirty[:5])})
        changed = [i for i, p in files.items() if i in acs_before and ac_hash(p.read_text()) != acs_before[i]]
        changed += [i for i in acs_before if i not in files]
        if changed:
            restored = [i for i in changed if i in files and restore_acs(root, i, files[i], start_commit)]
            fails.append({"check": "ac_freeze", "reason": "acceptance criteria changed in " + ", ".join(changed),
                          "detail": "restored from the run-start commit: " + (", ".join(restored) or "none")})
        prot = protected_paths(root, tron)
        hit = [f for f in changed_paths(root, base) if f in prot]
        if hit:
            fails.append({"check": "protected", "reason": "protected files changed: " + ", ".join(hit)})
        return {"passed": not fails, "failures": fails, "placeholders": scan_placeholders(root, base),
                "deleted_files": [f for f in deleted_paths(root, base) if not f.startswith("backlog/")]}
    except TronError as e:
        fails.append({"check": "git", "reason": str(e)})
        return {"passed": False, "failures": fails, "placeholders": [], "deleted_files": []}


def cmd_run(args):
    root = pathlib.Path(args.root).resolve()
    tron = load_config(root, args.config)
    milestone = args.milestone
    run_id = args.run_id or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    first = ready_tasks(root, milestone)
    if args.dry_run:
        if not first:
            print(f"dry run: no ready task in {milestone}")
            return 0
        print(f"dry run: run {run_id}, branch tron/{milestone}, ready tasks in order: {', '.join(first)}")
        for t in first:
            cmd = fill(command_for(tron, "worker"), {"prompt": tron.get("prompt", DEFAULT_PROMPT).replace("{task_id}", t),
                                                    "session_id": "<new uuid>", "task_id": t, "run_id": run_id, "milestone": milestone})
            print(f"  {t}: STEM_TRON=1 {' '.join(cmd)}")
        print("dry run: nothing started (later tasks may become ready as earlier ones finish)")
        return 0
    if not first:
        print(f"no ready task in {milestone}; nothing to do")
        return 0
    branch, existed = prepare_branch(root, milestone, False)
    jpath = root / JOURNAL_DIR / f"run-{run_id}.json"
    start_commit = head(root)
    journal = {"run_id": run_id, "milestone": milestone, "branch": branch, "started": now(), "ended": None,
               "start_commit": start_commit, "ac_hashes": snapshot_acs(root), "sessions": []}
    write_journal(jpath, journal)
    print(f"run {run_id} on branch {branch} ({'reused' if existed else 'created'}); journal {jpath.relative_to(root)}")
    acs0 = journal["ac_hashes"]
    refs0 = branch_refs(root)
    journal["refs_start"] = refs0
    attempted = []
    while True:
        if args.max_tasks is not None and len(attempted) >= args.max_tasks:
            break
        code, tail = verify(root, tron)  # baseline: a red branch gets a repair session before the next task
        if code:
            print(f"baseline verification failed (exit {code}); starting a repair session")
            base = head(root); acs_before = snapshot_acs(root)
            entry = run_session(root, tron, "worker", "baseline", run_id, milestone, tron.get("baseline_prompt", BASELINE_PROMPT))
            entry["gate"] = gate(root, tron, None, base, acs_before, start_commit, branch, refs0)
            journal["sessions"].append(entry)
            write_journal(jpath, journal)
            if not entry["gate"]["passed"]:
                journal["ended"] = now(); journal["aborted"] = "baseline red after repair"
                write_journal(jpath, journal)
                print("baseline still red after the repair session: run stopped (nothing is built on a red branch)", file=sys.stderr)
                return 3
        # only tasks that existed when the run was approved; tasks a session creates stay drafts for the report
        todo = [t for t in ready_tasks(root, milestone) if t not in attempted and t in acs0]
        if not todo:
            break
        task_id = todo[0]
        attempted.append(task_id)
        print(f"{task_id}: starting worker session")
        base = head(root); acs_before = snapshot_acs(root)
        entry = run_session(root, tron, "worker", task_id, run_id, milestone)
        entry["gate"] = gate(root, tron, task_id, base, acs_before, start_commit, branch, refs0)
        journal["sessions"].append(entry)
        write_journal(jpath, journal)
        g = entry["gate"]
        print(f"{task_id}: exit {entry['exit_code']}, gate " + ("passed" if g["passed"] else "FAILED: " + "; ".join(f["reason"] for f in g["failures"]))
              + (f", cost {entry['cost_usd']}" if entry["cost_usd"] is not None else ""))
        stop = sorted({f["check"] for f in g["failures"]} & STOPPING)
        if stop:  # damage on the branch (dirty tree, protected or AC change, left branch): nothing is built on top of it
            journal["ended"] = now(); journal["aborted"] = "gate damage: " + ", ".join(stop)
            write_journal(jpath, journal)
            print(f"run stopped after {task_id}: {', '.join(stop)} (see the journal); nothing was discarded", file=sys.stderr)
            return 4
    journal["ended"] = now()
    write_journal(jpath, journal)
    print(f"run {run_id} ended after {len(attempted)} task(s)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="tron.py", description="Tron mode runner (R-TRON)")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the ready tasks of a milestone, one agent session per task")
    r.add_argument("--milestone", required=True, help="milestone id, e.g. m-4")
    r.add_argument("--dry-run", action="store_true", help="print task order and commands, start nothing")
    r.add_argument("--run-id", help="run id (default: timestamp)")
    r.add_argument("--max-tasks", type=int, help="stop after this many tasks")
    r.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    r.add_argument("--root", default=".", help="project root (default: current directory)")
    args = p.parse_args(argv)
    try:
        return cmd_run(args)
    except TronError as e:
        print(f"tron: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
