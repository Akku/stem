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
import argparse, datetime, json, os, pathlib, re, subprocess, sys, uuid

ROLES = ("worker", "evaluator", "doctor", "planner", "retro")
DEFAULT_PROMPT = ("Work on backlog task {task_id} following AGENTS.md. This is an unattended Tron mode session "
                  "(STEM_TRON=1): read R-TRON first and follow it; nobody answers questions. Work on this one task only.")
JOURNAL_DIR = pathlib.Path("docs/agent/tron")


class TronError(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(root, path=None):
    cfg_path = pathlib.Path(path) if path else root / "docs/agent/stem-config.json"
    if not cfg_path.is_file():
        raise TronError(f"config missing: {cfg_path} (needs a key 'tron' with 'worker_cmd')")
    try:
        cfg = json.loads(cfg_path.read_text())
    except ValueError as e:
        raise TronError(f"config unreadable: {cfg_path}: {e}")
    tron = cfg.get("tron")
    if not isinstance(tron, dict) or not tron.get("worker_cmd"):
        raise TronError(f"config {cfg_path}: key 'tron.worker_cmd' missing (command template as a list of strings)")
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
    if dry or cur == branch:
        return branch, exists
    dirty = [l for l in sh(["git", "status", "--porcelain", "--", ".", f":!{JOURNAL_DIR}"], root).stdout.splitlines() if l.strip()]
    if dirty:
        raise TronError("working tree is not clean; commit or stash first (the run starts on its own branch)")
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


def run_session(root, tron, role, task_id, run_id, milestone):
    """Start one agent process for one task and return its journal entry."""
    session_id = str(uuid.uuid4())
    prompt = tron.get("prompt", DEFAULT_PROMPT).replace("{task_id}", task_id)
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
    journal = {"run_id": run_id, "milestone": milestone, "branch": branch, "started": now(), "ended": None, "sessions": []}
    write_journal(jpath, journal)
    print(f"run {run_id} on branch {branch} ({'reused' if existed else 'created'}); journal {jpath.relative_to(root)}")
    attempted = []
    while True:
        if args.max_tasks is not None and len(attempted) >= args.max_tasks:
            break
        todo = [t for t in ready_tasks(root, milestone) if t not in attempted]
        if not todo:
            break
        task_id = todo[0]
        attempted.append(task_id)
        print(f"{task_id}: starting worker session")
        entry = run_session(root, tron, "worker", task_id, run_id, milestone)
        journal["sessions"].append(entry)
        write_journal(jpath, journal)
        print(f"{task_id}: exit {entry['exit_code']}" + (f", cost {entry['cost_usd']}" if entry["cost_usd"] is not None else ""))
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
