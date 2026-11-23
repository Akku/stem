#!/usr/bin/env python3
"""Tron mode runner (R-TRON, docs/agent/TRON.md): hands one approved milestone to unattended agent sessions.

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
import argparse, datetime, fnmatch, hashlib, json, os, pathlib, re, subprocess, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # sibling module also when loaded by path
import transcripts

ROLES = ("worker", "evaluator", "doctor", "planner", "retro", "applier")
DEFAULT_PROMPT = ("Work on backlog task {task_id} following AGENTS.md. This is an unattended Tron mode session "
                  "(STEM_TRON=1): read R-TRON first and follow it; nobody answers questions. Work on this one task only. "
                  "Bash is limited to an allowlist: run one command per call, never chained with &&, ;, | or a subshell; "
                  "a denied call means that command form is not allowed, not that Bash is banned: split it or use another listed command.")
JOURNAL_DIR = pathlib.Path("docs/agent/tron")
# files a session must not change (tier 3 of the retro changes, R-TRON): the gate itself, the config, the decision frame, the invariants,
# the judging and diagnosing agents, security and deny rules
PROTECTED = ("scripts/tron.py", "docs/agent/stem-config.json", "docs/agent/DECISION_FRAME.md", "docs/agent/INVARIANTS.md",
             ".claude/agents/evaluator.md", ".claude/agents/doctor.md", ".claude/agents/retro-analyst.md", ".claude/agents/planner.md",
             ".claude/settings.json", ".claude/settings.local.json", "scripts/deny-guard.py", "scripts/hooks/*", "scripts/githooks/*")
BASELINE_PROMPT = ("The verification command fails on the current branch before any task starts (unattended Tron mode session, "
                   "STEM_TRON=1; read R-TRON first). Find the cause and fix it with the smallest change. Do not change acceptance "
                   "criteria and do not start task work.")
# duties the runner always appends, also to a configured baseline_prompt: the gate checks a clean tree and one green run is no proof (TASK-282)
BASELINE_DUTIES = ("Before you end: run the verification command at least 3 times in a row and claim green only if every run passed "
                   "(a test that passes only sometimes, e.g. order- or time-dependent, is part of the red baseline: fix it too). "
                   "Then commit the fix (one commit, message starting with 'baseline:') and end on a clean working tree: "
                   "no uncommitted or untracked files; the runner's gate fails on a dirty tree.")


API_CODES = (429, 500, 502, 503, 504, 529)
API_RE = re.compile(r"rate.?limit|overloaded|too many requests|\b(429|502|503|504|529)\b|temporarily unavailable|ECONNRESET", re.I)
# files the runner writes itself (journal, report, stop file) do not count as changes
STOP_FILE = "docs/agent/tron/STOP"


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
    if tron.get("evaluator", "milestone") not in ("off", "milestone", "task"):
        raise TronError(f"config {cfg_path}: tron.evaluator must be 'off', 'milestone' or 'task'")
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


def is_blocked(text, blocked_status="Blocked"):
    """A task the runner (or the user) marked Blocked: status Blocked, or label 'blocked' where the project has no such status."""
    st = re.search(r"^status: *(.+?) *$", text, re.M)
    lab = re.search(r"^labels:(.*?)(?=^\S)", text, re.M | re.S)
    labels = re.findall(r"[\w-]+", lab.group(1)) if lab else []
    return (st and st.group(1).strip("'\"").lower() == blocked_status.lower()) or "blocked" in [l.lower() for l in labels]


def ready_tasks(root, milestone, blocked_status="Blocked"):
    """Ready tasks of the milestone in backlog order (unblocked, dependencies done; Blocked tasks are never offered again)."""
    r = sh(["backlog", "task", "list", "-m", milestone, "--ready", "--plain"], root)
    if r.returncode:
        raise TronError(f"backlog task list failed: {(r.stderr or r.stdout).strip()[:300]}")
    ids, files = [], task_files(root)
    for line in r.stdout.splitlines():
        m = re.search(r"\b(TASK-\d+) - ", line)
        if m and m.group(1) not in ids:
            f = files.get(m.group(1))
            if f and is_blocked(f.read_text(), blocked_status):
                continue
            ids.append(m.group(1))
    return ids


def task_deps(text):
    """Dependencies of a backlog task file: block list or inline list in the front matter."""
    m = re.search(r"^dependencies:(.*?)(?=^\S)", text, re.M | re.S)
    return re.findall(r"TASK-\d+", m.group(1)) if m else []


def stranded_by(root, milestone, blocked):
    """Open milestone tasks that wait for a Blocked task directly or indirectly: {task: blocked task it waits for} (TASK-296).
    The runner is serial and never offers a Blocked task again, so these never become ready in this run."""
    deps = {}
    for tid, f in task_files(root).items():
        text = f.read_text()
        m = re.search(r"^milestone: *(.+?) *$", text, re.M)
        st, _, _ = parse_task(text)
        if m and m.group(1).strip("'\"") == milestone and (st or "").lower() != "done":
            deps[tid] = task_deps(text)
    out = {}
    for b in blocked:
        todo = [b]
        while todo:
            cur = todo.pop()
            for tid, ds in deps.items():
                if cur in ds and tid not in out and tid not in blocked:
                    out[tid] = b; todo.append(tid)
    return out


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
    return home / ".claude/projects" / transcripts.slug(cwd) / f"{session_id}.jsonl"


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
    if d.get("is_error") and isinstance(d.get("api_error_status"), int):
        out["api_status"] = d["api_error_status"]
    if isinstance(d.get("result"), str):
        out["result_text"] = d["result"]
    mu = d.get("modelUsage")
    if isinstance(mu, dict) and mu:
        out["model"] = ", ".join(sorted(mu))
    return out


def write_journal(path, journal):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(journal, indent=1) + "\n")
    os.replace(tmp, path)


def kill_group(proc):
    import signal
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
    except (ProcessLookupError, PermissionError):
        proc.communicate()


def run_session(root, tron, role, task_id, run_id, milestone, prompt=None):
    """Start one agent process for one task and return its journal entry."""
    session_id = str(uuid.uuid4())
    prompt = prompt or tron.get("prompt", DEFAULT_PROMPT).replace("{task_id}", task_id)
    cmd = fill(command_for(tron, role), {"prompt": prompt, "session_id": session_id, "task_id": task_id,
                                         "run_id": run_id, "milestone": milestone})
    env = dict(os.environ, STEM_TRON="1", STEM_TRON_RUN=run_id, STEM_TRON_TASK=task_id, STEM_TRON_ROLE=role)
    entry = {"task": task_id, "role": role, "start": now(), "command": cmd}
    timeout = tron.get("session_timeout")
    try:
        # own process group: a timeout must also end the tools the agent started, or they keep writing into the tree
        proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_group(proc)
            raise
        entry["exit_code"] = proc.returncode
        info = parse_output(out)
        if role in ("evaluator", "planner", "doctor", "retro"):  # the verdict or sweep text goes to its own file, not into the journal
            entry["_out"] = info.get("result_text") or (out or "")[-30000:]
        if proc.returncode:
            entry["stderr_tail"] = (err or "").strip()[-300:]
        if info.get("api_status") in API_CODES or (proc.returncode and API_RE.search((err or "")[-2000:])):
            entry["api_error"] = True
    except subprocess.TimeoutExpired:
        entry["exit_code"] = 124
        entry["timeout"] = True
        entry["stderr_tail"] = f"session killed after {timeout} s"
        info = {}
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
EXCLUDE = [":(exclude,glob)docs/agent/tron/run-*", ":(exclude,glob)docs/agent/tron/REPORT-*", ":(exclude)docs/agent/tron/STOP", ":(exclude)docs/agent/tron/LOCK",
           ":(exclude,glob)docs/agent/tron/brief-*", ":(exclude,glob)docs/agent/tron/verdict-*", ":(exclude,glob)docs/agent/tron/doctor-*",
           ":(exclude,glob)docs/agent/tron/RETRO-*", ":(exclude,glob)docs/agent/tron/CALIBRATION-*"]
RUNNER_FILE = re.compile(r"^docs/agent/tron/(run-|REPORT-|STOP$|LOCK$|brief-|verdict-|doctor-|RETRO-|CALIBRATION-)")


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
    return r.returncode, "\n".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-40:])[-4000:]


def protected_paths(root, tron):
    """Gate and config files plus the files that decide the verdict: run.sh and every repo file named in verify_cmd."""
    prot = set(PROTECTED) | {"scripts/run.sh", "docs/agent/tron/ACCEPTANCE-*", EXPERIMENTS} | set(tron.get("protected", []))
    if tron.get("acceptance_scenario"):
        prot.add(tron["acceptance_scenario"])
    for arg in tron["verify_cmd"]:
        p = (root / arg)
        try:
            if arg and p.is_file() and root.resolve() in p.resolve().parents:
                prot.add(p.resolve().relative_to(root.resolve()).as_posix())
        except OSError:
            pass
    return prot


STOPPING = {"ac_freeze", "protected", "branch", "refs", "git"}  # damage the agent cannot repair: the run stops; a dirty tree is repaired or reset by the repair loop


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
            for l in notes.splitlines():
                if re.match(r"\s*AC#\d+: E2\b", l) and re.search(r"extrapolat|estimat", l, re.I):
                    fails.append({"check": "evidence", "reason": f"extrapolated or estimated figure graded E2: '{l.strip()[:100]}'; measure it for real or grade it E1"})
            old = start_text(root, task_id, base)
            if old is not None:
                now_lines = {x.strip() for x in notes.splitlines()}
                for l in parse_task(old)[2].splitlines():
                    if l.strip() and l.strip() not in now_lines:
                        fails.append({"check": "notes", "reason": f"a line of the task notes from before the task is missing: '{l.strip()[:100]}'; append with --append-notes, never overwrite"})
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
        hit = [f for f in changed_paths(root, base) if any(fnmatch.fnmatchcase(f, pat) for pat in prot)]
        if hit:
            fails.append({"check": "protected", "reason": "protected files changed: " + ", ".join(hit)})
        return {"passed": not fails, "failures": fails, "placeholders": scan_placeholders(root, base),
                "deleted_files": [f for f in deleted_paths(root, base) if not f.startswith("backlog/")]}
    except TronError as e:
        fails.append({"check": "git", "reason": str(e)})
        return {"passed": False, "failures": fails, "placeholders": [], "deleted_files": []}


# ---- evaluator (independent judge; fail is handled like a gate fail) ----

def labels_of(text):
    lab = re.search(r"^labels:(.*?)(?=^\S)", text, re.M | re.S)
    return [l.lower() for l in re.findall(r"[\w-]+", lab.group(1))] if lab else []


def eval_due(tron, task_text):
    """evaluator: off | milestone (default: milestone end, and per task for size-L or label review) | task (every task)."""
    mode = tron.get("evaluator", "milestone")
    if mode == "off":
        return False
    return mode == "task" or bool({"size-l", "review"} & set(labels_of(task_text)))


FINDING_KINDS = ("defect", "invariant", "not_verifiable", "placeholder", "risk")


def parse_verdict(text, expected_acs=None):
    """Verdict from the final message, fail-closed: any parseable fail block wins; a pass needs lists of objects, no findings and,
    for a single task, a 'checked' entry for every AC. Returns None when there is no usable block."""
    found = []
    for b in re.findall(r"```(?:json|jsonc)?\s*(\{.*?\})\s*```", text or "", re.S | re.I):
        try:
            d = json.loads(b)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("verdict") not in ("pass", "fail"):
            continue
        lists = {k: d.get(k) if d.get(k) is not None else [] for k in ("findings", "assumption_flags", "checked")}
        if any(not isinstance(v, list) or not all(isinstance(x, dict) for x in v) for v in lists.values()):
            continue
        for x in lists["findings"]:
            x["kind"] = str(x.get("kind") or "defect").strip().lower()
        if any(x["kind"] not in FINDING_KINDS for x in lists["findings"]):
            return None  # unknown kind: no usable verdict at all (fail-closed)
        for x in lists["findings"]:  # a risk that names an AC or an invariant is not beyond the criteria
            if x["kind"] == "risk" and re.match(r"\s*(AC\s*#|invariant)", str(x.get("ac", "")), re.I):
                x["kind"] = "invariant" if re.match(r"\s*invariant", str(x.get("ac", "")), re.I) else "defect"
        # risk findings (beyond the AC) never fail a verdict: they become draft tasks
        risks = [x for x in lists["findings"] if x["kind"] == "risk"]
        lists["findings"] = [x for x in lists["findings"] if x["kind"] != "risk"]
        verdict = d["verdict"]
        if risks and not lists["findings"] and not lists["assumption_flags"]:
            verdict = "pass"
        found.append(dict(verdict=verdict, risks=risks, **lists))
    if not found:
        return None
    v = next((x for x in found if x["verdict"] == "fail"), found[-1])
    if v["verdict"] == "pass":
        if v["findings"]:
            v = dict(v, verdict="fail")
        elif expected_acs:
            seen = {re.sub(r"\s", "", str(c.get("ac", ""))).upper() for c in v["checked"]}
            missing = [a for a in expected_acs if a.upper() not in seen]
            if missing:
                v = dict(v, verdict="fail", findings=[{"ac": a, "location": "evaluator output", "kind": "not_verifiable",
                         "scenario": "the verdict lists no check for this AC; a pass must say how each AC was exercised"} for a in missing])
    return v


def assumptions(root, ids):
    out = []
    files = task_files(root)
    for i in ids:
        if i in files:
            for l in parse_task(files[i].read_text())[2].splitlines():
                if re.match(r"\s*Assumption:", l):
                    out.append(f"{i}: {l.strip()}")
    return out


ASSUMPTION_BASIS = re.compile(r"\(basis:\s*([^)]*?)\s*\)\s*$", re.I)


def assumption_basis(line):
    """Basis of an 'Assumption:' line: text after '(basis: ...)' at the end, 'none' when it says so, None when the line names no basis."""
    m = ASSUMPTION_BASIS.search(line.strip())
    return (m.group(1) or "none").strip() if m else None


def task_intent(text):
    """Title and description only: the implementer's notes and evidence claims stay out of the evaluator's input."""
    title = re.search(r"^title: *(.+?) *$", text, re.M)
    desc = re.search(r"<!-- SECTION:DESCRIPTION:BEGIN -->(.*?)<!-- SECTION:DESCRIPTION:END -->", text, re.S)
    return f"{(title.group(1).strip(chr(39) + chr(34)) if title else '?')}\n\n{(desc.group(1).strip() if desc else '')}"[:4000]


def read_rel(root, rel):
    p = root / rel
    return p.read_text() if p.is_file() else f"(no {rel})"


DIFF_BUDGET = 60000  # characters of diff in one evaluator brief
PART_MIN = 4000  # every task of a milestone brief shows at least this much of its diff, even past DIFF_BUDGET


def milestone_diff(root, tron, journal, base, task_ids, stat, ex):
    """Milestone brief diff grouped by task (TASK-297): each accepted task's commits with a size budget per task, then the commits of
    no task (baseline and milestone repairs). Every cut part names the exact git command that shows it in full."""
    q = lambda: " ".join(["--", "."] + [f"'{e}'" for e in ex])
    rng = {i: journal.get("task_ranges", {}).get(i) for i in task_ids}
    groups, covered = [], set()
    for i in task_ids:
        r = rng.get(i)
        if r and r[0] != r[1]:
            covered |= set(git_ok(root, "rev-list", f"{r[0]}..{r[1]}").split())
            groups.append((f"### {i}: commits {r[0][:10]}..{r[1][:10]}", f"git diff --no-renames {r[0]} {r[1]} {q()}",
                           git_ok(root, "diff", "--no-renames", r[0], r[1], "--", ".", *ex)))
    other = [c for c in git_ok(root, "rev-list", "--reverse", f"{base}..HEAD").split() if c not in covered]
    for c in other:
        groups.append((f"### Commit {c[:10]} of no task: {git_ok(root, 'log', '-1', '--format=%s', c).strip()[:120]}",
                       f"git show --no-renames --format= {c} {q()}", git_ok(root, "show", "--no-renames", "--format=", c, "--", ".", *ex)))
    total = int(tron.get("brief_diff_chars", DIFF_BUDGET))
    budget = max(min(PART_MIN, total), total // max(len(groups), 1))
    out = [f"Whole diff: git diff --no-renames {base} {q()} (task files are left out). Below it is grouped by task, "
           f"at most {budget} characters per part; every cut part names the command that shows it in full.", "```", stat.strip(), "```"]
    cut = []
    for title, cmd, d in groups:
        out += ["", title, f"Full: `{cmd}`"]
        if not d.strip():
            out.append("(no change outside task files)"); continue
        out += ["```diff", d[:budget], "```"]
        if len(d) > budget:
            out.append(f"(cut: {budget} of {len(d)} characters shown; the rest: `{cmd}`)"); cut.append(f"- {title[4:]}: `{cmd}`")
    for i in task_ids:
        v = journal["tasks"].get(i, {})
        if not (rng.get(i) and rng[i][0] != rng[i][1]):
            out += ["", f"### {i}", f"closed by its subtasks {', '.join(v['closed_by'])} (their diffs are above)" if v.get("closed_by")
                    else "no commit range recorded for this task; its commits are among the commits of no task above"]
    out += ["", "### Left out of this brief", *(cut or ["(nothing: every part is shown in full)"])]
    return out


def write_brief(root, tron, journal, target, base, g, task_ids, intent):
    """The evaluator's only input besides the repository: intent, ACs, diff, verification, invariants, hints, assumptions."""
    files = task_files(root)
    parts = [f"# Evaluator brief: {target} (run {journal['run_id']})", "", "## Intent", intent, "", "## Acceptance criteria"]
    for i in task_ids:
        if i in files:
            _, acs, _ = parse_task(files[i].read_text())
            parts += [f"### {i}"] + [f"- AC#{n}: {s}" for _, n, s in acs]
    if target == "milestone":
        scen = tron.get("acceptance_scenario", f"docs/agent/tron/ACCEPTANCE-{journal['milestone']}.md")
        parts += ["", "## Milestone acceptance scenario", read_rel(root, scen)]
    code, tail = verify(root, tron)
    ex = EXCLUDE + [":(exclude)backlog"]  # task files carry the implementer's notes and evidence claims
    diff = git_ok(root, "diff", "--no-renames", base, "--", ".", *ex)
    stat = git_ok(root, "diff", "--no-renames", "--stat", base, "--", ".", *ex)
    if g is None:
        g = {"placeholders": scan_placeholders(root, base), "deleted_files": [f for f in deleted_paths(root, base) if not f.startswith("backlog/")]}
    parts += ["", "## Verification by the runner", f"exit code {code}", tail, "", f"## Diff since {base[:12]}"]
    if target == "milestone":
        parts += milestone_diff(root, tron, journal, base, task_ids, stat, ex)
    else:
        parts += [f"Full diff: git diff {base} -- . ':(exclude)backlog' (the text below is cut at {DIFF_BUDGET} characters; task files are left out)",
                  "```", stat.strip(), "```", diff[:DIFF_BUDGET] + ("\n(diff truncated)" if len(diff) > DIFF_BUDGET else "")]
    if tron.get("smoke_cmd"):
        parts += ["", "## Start or smoke command", " ".join(tron["smoke_cmd"]) if isinstance(tron["smoke_cmd"], list) else str(tron["smoke_cmd"])]
    parts += ["", "## Invariants", read_rel(root, "docs/agent/INVARIANTS.md"), "", "## Decision frame", read_rel(root, "docs/agent/DECISION_FRAME.md"),
              "", "## Hints from the runner", "Placeholder hits: " + json.dumps((g or {}).get("placeholders", [])),
              "Deleted files: " + json.dumps((g or {}).get("deleted_files", []))]
    al = assumptions(root, task_ids)
    parts += ["", "## Assumption list of this run", "\n".join(al) or "(none recorded)"]
    path = root / JOURNAL_DIR / f"brief-{journal['run_id']}-{target}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n")
    return path


def tree_state(root):
    """What an evaluator must not change: HEAD, branches, tracked content, hidden-edit flags."""
    return (head(root), sorted(branch_refs(root).items()), git_ok(root, "diff", "HEAD", "--", ".", *EXCLUDE),
            [l for l in git_ok(root, "ls-files", "-v").splitlines() if l[:1].islower() or l[:1] == "S"],
            git_ok(root, "config", "--local", "--list"), sorted(str(p.relative_to(root)) + str(p.stat().st_mtime_ns) for p in (root / ".git/hooks").glob("*") if p.is_file()) if (root / ".git/hooks").is_dir() else [])


def stash_artifacts(root, journal, target):
    """Files the evaluator created by running the product (data, caches) are kept in a named stash, so the next gate sees a clean tree."""
    if not [l for l in git_ok(root, "status", "--porcelain", "--", ".", *EXCLUDE).splitlines() if l.strip()]:
        return None
    name = f"tron {journal['run_id']} evaluator artifacts {target}"
    n0 = len(git_ok(root, "stash", "list").splitlines())
    git_ok(root, "stash", "push", "-u", "-q", "-m", name, "--", ".", *EXCLUDE)
    return name if len(git_ok(root, "stash", "list").splitlines()) > n0 else None


def evaluate(root, tron, journal, jpath, target, base, g, task_ids, intent, abort_check):
    """One evaluator session. Returns {'verdict','findings','assumption_flags','file'} or {'damage': reason} or {'unavailable': reason}."""
    brief = write_brief(root, tron, journal, target, base, g, task_ids, intent)
    prompt = (f"You are the independent evaluator of an unattended Tron mode run. Read .claude/agents/evaluator.md and follow it exactly. "
              f"Your brief is {brief.relative_to(root)}. Do not change any file in the project.")
    if not tron.get("evaluator_cmd"):
        print("tron: no evaluator_cmd configured: the evaluator runs with the worker command (Edit and Write allowed); "
              "read-only is only enforced by the tree check afterwards", file=sys.stderr)
    before = tree_state(root)
    verdict = None
    for attempt in (1, 2):  # a missing verdict gets one retry, then counts as a fail
        entry, up = sessions_with_retry(root, tron, "evaluator", target, journal["run_id"], journal["milestone"], journal, jpath, prompt, abort_check=abort_check)
        text = entry.pop("_out", "")
        if not up:
            return {"unavailable": entry.get("retry_aborted") or "API unavailable after retries"}
        if tree_state(root) != before:
            return {"damage": f"evaluator session for {target} changed HEAD, branches or tracked files"}
        stash = stash_artifacts(root, journal, target)
        expected = [f"AC#{n}" for i in task_ids[:1] for _, n, _ in parse_task(task_files(root)[i].read_text())[1]] if target != "milestone" else None
        verdict = parse_verdict(text, expected)
        entry["evaluator"] = {"target": target, "verdict": verdict["verdict"] if verdict else None}
        if stash:
            entry["evaluator"]["artifacts_stash"] = stash
        if verdict:
            break
    if not verdict:
        verdict = {"verdict": "fail", "assumption_flags": [], "checked": [], "findings": [{"ac": "-", "location": "evaluator output", "kind": "defect",
                   "scenario": "the evaluator gave no parseable verdict (final json block missing); treated as fail"}]}
    n = sum(1 for f in (root / JOURNAL_DIR).glob(f"verdict-{journal['run_id']}-{target}-*.json")) + 1
    vpath = root / JOURNAL_DIR / f"verdict-{journal['run_id']}-{target}-{n}.json"
    vpath.write_text(json.dumps(dict(verdict, target=target, at=now(), tail=(text or "")[-2000:]), indent=1) + "\n")
    entry["evaluator"]["file"] = str(vpath.relative_to(root))
    write_risk_drafts(root, target, verdict.get("risks") or [], journal)
    write_journal(jpath, journal)
    return dict(verdict, file=str(vpath.relative_to(root)))


def write_risk_drafts(root, target, risks, journal):
    """Each risk finding becomes a draft task (a question for the user); it never triggers a repair."""
    d = root / "backlog/drafts"
    wrote = False
    for r in risks:
        key = hashlib.sha256(f"{target}|{r.get('scenario', '')}".encode()).hexdigest()[:16]
        if key in journal.setdefault("risk_keys", []):
            continue  # the same risk re-reported after a repair round
        journal["risk_keys"].append(key); wrote = True
        d.mkdir(parents=True, exist_ok=True)
        n = max([int(m.group(1)) for p in d.glob("draft-*") for m in [re.match(r"draft-(\d+)", p.name)] if m] + [0]) + 1
        title = f"Risk found by the evaluator ({target}): " + str(r.get("scenario", ""))[:70].replace("\n", " ").replace("'", "")
        body = (f"Evaluator risk finding beyond the acceptance criteria (run {journal['run_id']}, {target}). It did not fail the verdict.\n\n"
                f"Location: {r.get('location', '?')}\nScenario: {r.get('scenario', '')}\n\nDecide: accept the risk, or create a task.")
        slug = re.sub(r"[^A-Za-z0-9]+", "-", title)[:60].strip("-")
        (d / f"draft-{n} - {slug}.md").write_text(f"---\nid: DRAFT-{n}\ntitle: '{title}'\nstatus: Draft\nassignee: []\nlabels:\n  - tron-risk\ndependencies: []\n---\n\n"
                                                  f"## Description\n\n<!-- SECTION:DESCRIPTION:BEGIN -->\n{body}\n<!-- SECTION:DESCRIPTION:END -->\n")
        journal.setdefault("risk_drafts", []).append(f"draft-{n}")
    if wrote:
        git_ok(root, "add", "-A", "--", "backlog/drafts")
        git_ok(root, "commit", "-q", "-m", f"Tron run: {target} evaluator risk finding(s) written as draft task(s)")  # target may be 'milestone'


DOCTOR_VERDICTS = ("retry_with_hint", "split_task", "environment_problem", "needs_user")


def parse_doctor(text):
    """The Doctor's valid json block: one verdict of DOCTOR_VERDICTS, a diagnosis and the field that verdict needs. None when there is none or when valid blocks disagree on the verdict (quoted data must not win)."""
    found, seen = None, set()
    for b in re.findall(r"```(?:json|jsonc)?\s*(\{.*?\})\s*```", text or "", re.S | re.I):
        try:
            d = json.loads(b)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("verdict") not in DOCTOR_VERDICTS or not str(d.get("diagnosis") or "").strip():
            continue
        if any(re.fullmatch(r"<.*>", str(d.get(k) or "").strip(), re.S) for k in ("diagnosis", "hint", "question")):
            continue  # the unfilled template placeholder
        v = d["verdict"]
        subs = d.get("subtasks")
        if v == "retry_with_hint" and not str(d.get("hint") or "").strip():
            continue
        if v == "needs_user" and not str(d.get("question") or "").strip():
            continue
        if v == "split_task" and not (isinstance(subs, list) and subs and all(isinstance(x, dict) and str(x.get("title") or "").strip()
                                                                             and isinstance(x.get("acs"), list) and x["acs"] and all(isinstance(a, str) for a in x["acs"]) for x in subs)):
            continue
        found = d
        seen.add(v)
    return found if len(seen) == 1 else None


def check_split(parent_acs, subtasks):
    """Why a proposed split is invalid (None when fine): 2 to 5 subtasks, every AC text verbatim from the parent, the union equals the parent's ACs."""
    if not 2 <= len(subtasks) <= 5:
        return f"{len(subtasks)} subtask(s); a split needs 2 to 5"
    want = {t.strip() for t in parent_acs}
    got = set()
    for x in subtasks:
        for a in x["acs"]:
            if a.strip() not in want:
                return f"subtask '{x['title'][:40]}' carries an AC that is not a parent AC verbatim: '{a.strip()[:80]}'"
            got.add(a.strip())
    if got != want:
        return "the subtasks do not cover every parent AC: missing '" + sorted(want - got)[0][:80] + "'"
    return None


def doctor_brief(root, tron, journal, task_id, base, intent, acs):
    """Input of the Doctor: intent, ACs, the failure summary of every attempt, the diff so far and the transcript paths."""
    parts = [f"# Doctor brief: {task_id} (run {journal['run_id']})", "", "## Intent", intent, "", "## Acceptance criteria"]
    parts += [f"- AC#{n}: {t}" for _, n, t in acs]
    parts += ["", "## Attempts"]
    k = 0
    for e in journal["sessions"]:
        if e.get("task") != task_id or e.get("role") != "worker":
            continue
        k += 1
        parts.append(f"### Attempt {k} ({'worker' if not e.get('repair') else 'repair ' + str(e['repair'])}; exit {e.get('exit_code')}; transcript {e.get('transcript')})")
        g = e.get("gate_after_evaluator") or e.get("gate") or {}
        for f in g.get("failures", []):
            parts.append(f"- {f.get('reason')}")
            if f.get("detail"):
                parts += ["  " + l for l in f["detail"].splitlines()[-15:]]
        if not g.get("failures"):
            parts.append("- gate passed")
    parts += ["", "## Diff so far (against the state before the task, capped)", "```diff", git_ok(root, "diff", base, "--", ".", *EXCLUDE)[:12000], "```", "",
              "## Invariants", read_rel(root, "docs/agent/INVARIANTS.md")[:3000], "", "## Decision frame", read_rel(root, "docs/agent/DECISION_FRAME.md")[:3000]]
    path = root / JOURNAL_DIR / f"brief-{journal['run_id']}-doctor-{task_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n")
    return path


def consult_doctor(root, tron, journal, jpath, task_id, base, intent, acs, abort_check):
    """One Doctor session (a missing verdict gets one retry). Returns the verdict dict, {'none': ...}, {'damage': ...} or {'unavailable': ...}."""
    brief = doctor_brief(root, tron, journal, task_id, base, intent, acs)
    prompt = (f"You are the Doctor of an unattended Tron mode run. Read .claude/agents/doctor.md and follow it exactly. "
              f"Your brief is {brief.relative_to(root)}. Do not change any file in the project.")
    before = (tree_state(root), tree_dirty(root))
    verdict = None
    for _ in (1, 2):
        entry, up = sessions_with_retry(root, tron, "doctor", task_id, journal["run_id"], journal["milestone"], journal, jpath, prompt, abort_check=abort_check)
        text = entry.pop("_out", "")
        if not up:
            return {"unavailable": entry.get("retry_aborted") or "API unavailable after retries"}
        if (tree_state(root), tree_dirty(root)) != before:
            return {"damage": f"doctor session for {task_id} changed HEAD, branches or files"}
        verdict = parse_doctor(text)
        entry["doctor"] = {"verdict": verdict["verdict"] if verdict else None}
        if verdict:
            break
    if not verdict:
        return {"none": "the Doctor gave no parseable verdict"}
    n = sum(1 for _ in (root / JOURNAL_DIR).glob(f"doctor-{journal['run_id']}-{task_id}-*.json")) + 1
    vpath = root / JOURNAL_DIR / f"doctor-{journal['run_id']}-{task_id}-{n}.json"
    vpath.write_text(json.dumps(dict(verdict, task=task_id, at=now()), indent=1) + "\n")
    entry["doctor"]["file"] = str(vpath.relative_to(root))
    write_journal(jpath, journal)
    return verdict


def next_draft_number(d):
    return max([int(m.group(1)) for p in d.glob("draft-*") for m in [re.match(r"draft-(\d+)", p.name)] if m] + [0]) + 1


def write_question_draft(root, journal, title, body, label):
    """A decision draft for the user, committed on its own (the blocked task's reset keeps drafts)."""
    d = root / "backlog/drafts"
    d.mkdir(parents=True, exist_ok=True)
    n = next_draft_number(d)
    title = title[:90].replace("\n", " ").replace("'", "")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title)[:60].strip("-")
    (d / f"draft-{n} - {slug}.md").write_text(f"---\nid: DRAFT-{n}\ntitle: '{title}'\nstatus: Draft\nassignee: []\nlabels:\n  - {label}\ndependencies: []\n---\n\n"
                                              f"## Description\n\n<!-- SECTION:DESCRIPTION:BEGIN -->\n{body}\n<!-- SECTION:DESCRIPTION:END -->\n")
    git_ok(root, "add", "-A", "--", "backlog/drafts")
    git_ok(root, "commit", "-q", "-m", f"Tron run: {label} draft DRAFT-{n}")
    return f"draft-{n}"


def create_subtasks(root, tron, journal, parent, parent_text, subtasks):
    """Subtasks of a split parent in the same milestone through the backlog CLI; their ACs are verified against the parent's afterwards."""
    milestone = journal["milestone"]
    labels = ",".join(l for l in labels_of(parent_text) if l not in ("blocked",)) or "size-S"
    before = set(task_files(root))
    try:
        return _create_subtasks(root, journal, parent, parent_text, subtasks, milestone, labels, before)
    except TronError:
        for i in set(task_files(root)) - before:  # a half-made split must not stay in the tree
            try:
                task_files(root)[i].unlink()
            except (OSError, KeyError):
                pass
        raise


def _create_subtasks(root, journal, parent, parent_text, subtasks, milestone, labels, before):
    made = []
    for x in subtasks:
        cmd = ["backlog", "task", "create", x["title"].strip().lstrip("-").strip() or "split part", "-m", milestone, "-l", labels,
               "-d", f"Split off {parent} by the Doctor of run {journal['run_id']}; the parent closes when all its subtasks pass."]
        for a in x["acs"]:
            cmd += ["--ac", a.strip()]
        r = sh(cmd, root)
        if r.returncode:
            raise TronError(f"could not create a subtask of {parent}: {(r.stderr or r.stdout).strip()[:200]}")
        new = sorted(set(task_files(root)) - before - set(made), key=lambda t: int(t.split("-")[1]))
        if not new:
            raise TronError(f"backlog created no task file for a subtask of {parent}")
        made.append(new[-1])
    files = task_files(root)
    parent_acs = [t for _, _, t in parse_task(parent_text)[1]]
    got = {t for i in made for _, _, t in parse_task(files[i].read_text())[1]}
    if got != {t.strip() for t in parent_acs}:
        raise TronError(f"the subtasks of {parent} do not carry exactly the parent's ACs; check {', '.join(made)}")
    git_ok(root, "add", "-A", "--", "backlog")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode:
        git_ok(root, "commit", "-q", "-m", f"{parent}: Tron Doctor split the task into {', '.join(made)}")
    for i in made:
        journal["ac_hashes"][i] = ac_hash(files[i].read_text())  # created by the runner, so inside the AC freeze
    return made


def close_split_parents(root, tron, journal):
    """A split parent is Done when all its subtasks were accepted by the gate."""
    closed = []
    for pid, v in journal["tasks"].items():
        subs = v.get("subtasks")
        if v.get("state") != "split" or not subs or any(journal["tasks"].get(s, {}).get("state") != "accepted" for s in subs):
            continue
        f = task_files(root).get(pid)
        if not f:
            continue
        acs = parse_task(f.read_text())[1]
        cmd = ["backlog", "task", "edit", pid, "-s", "Done"]
        notes = []
        for _, n, _ in acs:
            cmd += ["--check-ac", str(n)]
            notes.append(f"AC#{n}: E2 carried by {', '.join(subs)}; each subtask passed the runner's gate")
        r = sh(cmd + ["--append-notes", "\n".join(notes + [f"Closed by the Tron runner: all subtasks of the Doctor's split are accepted ({', '.join(subs)})"])], root)
        if r.returncode:
            raise TronError(f"could not close {pid}: {(r.stderr or r.stdout).strip()[:200]}")
        git_ok(root, "add", "-A", "--", "backlog")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode:
            git_ok(root, "commit", "-q", "-m", f"{pid}: Tron run closed the split task")
        v["state"] = "accepted"; v["closed_by"] = subs
        closed.append(pid)
    return closed


def verdict_failure(ev):
    lines = [f"verdict file: {ev['file']}"]
    for f in ev["findings"]:
        lines.append(f"{f.get('ac', '-')} at {f.get('location', '?')}: {f.get('scenario', '')}")
    for a in ev["assumption_flags"]:
        lines.append(f"assumption conflicts: {a.get('assumption', '?')} ({a.get('conflict', '?')})")
    sig = {(str(f.get("ac", "-")), str(f.get("kind", "defect"))) for f in ev["findings"]}
    if ev["assumption_flags"]:
        sig.add(("assumption", "conflict"))
    sig = sorted(sig)
    # findings a worker cannot repair (environment, assumptions): block at once instead of spending repair sessions
    unrepairable = bool(ev["assumption_flags"] or ev["findings"]) and all(f.get("kind") == "not_verifiable" for f in ev["findings"])
    return {"passed": False, "placeholders": [], "deleted_files": [],
            "failures": [{"check": "evaluator", "reason": f"evaluator verdict fail: {len(ev['findings'])} finding(s)", "detail": "\n".join(lines)[:4000],
                          "sig": sig, "unrepairable": unrepairable}]}


def fingerprint(root):
    """Hash of HEAD, status and diff: equal before and after a session means the session left no diff."""
    parts = [head(root), git_ok(root, "status", "--porcelain", "--", ".", *EXCLUDE), git_ok(root, "diff", "HEAD", "--", ".", *EXCLUDE)]
    for f in git_ok(root, "ls-files", "--others", "--exclude-standard").splitlines():
        if not RUNNER_FILE.match(f) and (root / f).is_file():
            parts.append(f + ":" + hashlib.sha256((root / f).read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def signature(gate_result):
    return sorted((f["check"], f["reason"], hashlib.sha256((json.dumps(f["sig"]) if "sig" in f else re.sub(r"\d+", "#", f.get("detail", ""))).encode()).hexdigest()[:12])
                  for f in gate_result["failures"])


def wall_hours(journal, t0):
    """Wall-clock hours of the run: earlier invocations plus this one (gate runs and backoff included, pauses between runs not)."""
    return (journal.get("wall_seconds", 0) + time.time() - t0) / 3600


def limit_hit(journal, tron, max_tasks, t0=None):
    cost = sum(s.get("cost_usd") or 0 for s in journal["sessions"])
    if tron.get("max_cost") is not None and cost >= float(tron["max_cost"]):
        return f"max_cost reached ({cost:.2f} of {tron['max_cost']})"
    if tron.get("max_hours") is not None and t0 is not None and wall_hours(journal, t0) >= float(tron["max_hours"]):
        return f"max_hours reached ({wall_hours(journal, t0):.2f} of {tron['max_hours']})"
    if max_tasks is not None and len(journal["tasks"]) >= max_tasks:
        return f"max_tasks reached ({max_tasks}; counts all tasks of the run, blocked ones included)"
    return None


def repair_prompt(tron, task_id, gate_result, n, limit):
    lines = [f"The runner's gate failed your previous session for {task_id} (repair {n} of {limit}). Fix exactly this and nothing else:"]
    log = []
    for f in gate_result["failures"]:
        lines.append(f"- {f['reason']}")
        if f.get("detail"):
            log += f["detail"].splitlines()
    if log:
        lines += ["Last log lines:"] + log[-40:]
    return tron.get("prompt", DEFAULT_PROMPT).replace("{task_id}", task_id) + "\n\n" + "\n".join(lines)


def sessions_with_retry(root, tron, role, task_id, run_id, milestone, journal, jpath, prompt=None, sleep=time.sleep, abort_check=None):
    """Run a session; API and rate-limit errors are retried with backoff (capped, interruptible) and are not repairs. Returns (entry, available)."""
    retries, delay = int(tron.get("api_retries", 5)), float(tron.get("backoff_base", 30))
    for k in range(retries + 1):
        write_journal(jpath, journal)  # in_progress is on disk before the process starts (crash recovery)
        entry = run_session(root, tron, role, task_id, run_id, milestone, prompt)
        entry["attempt"] = k
        journal["sessions"].append(entry)
        write_journal(jpath, journal)
        if not entry.get("api_error"):
            return entry, True
        entry.pop("_out", None)
        why = abort_check() if abort_check else None
        if why:
            entry["retry_aborted"] = why
            return entry, False
        if k < retries:
            sleep(min(delay * 2 ** k, 900))
    return entry, False


def set_blocked(root, tron, task_id, note):
    """Mark the task Blocked with the diagnosis (falls back to In Progress plus label 'blocked' where the project has no such status)."""
    status = tron.get("blocked_status", "Blocked")
    r = sh(["backlog", "task", "edit", task_id, "-s", status, "--append-notes", note], root)
    if r.returncode:
        r = sh(["backlog", "task", "edit", task_id, "-s", "In Progress", "--add-label", "blocked", "--append-notes", note], root)
    if r.returncode:
        raise TronError(f"could not mark {task_id} Blocked: {(r.stderr or r.stdout).strip()[:200]}")
    git_ok(root, "add", "-A", "--", "backlog")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode:
        git_ok(root, "commit", "-q", "-m", f"{task_id}: Tron run marked the task Blocked")


def unhide(root):
    """Clear assume-unchanged / skip-worktree flags so that stash and reset see every edit."""
    for l in git_ok(root, "ls-files", "-v").splitlines():
        if l[:1].islower() or l[:1] == "S":
            git_ok(root, "update-index", "--no-assume-unchanged", "--no-skip-worktree", "--", l[2:])


KEEP_DRAFT = re.compile(r"^backlog/drafts/")
NOTES_RE = re.compile(r"<!-- SECTION:NOTES:BEGIN -->\n?(.*?)<!-- SECTION:NOTES:END -->", re.S)


def worker_notes(root, task_id):
    """Notes the worker wrote in the task file; they survive the reset inside the Blocked note."""
    for p in (root / "backlog/tasks").glob(f"task-{task_id.split('-')[-1]} - *.md"):
        m = NOTES_RE.search(p.read_text())
        return m.group(1).strip() if m else ""
    return ""


def block_task(root, tron, task_id, base, reason, journal, refs0):
    """Failed work is kept (backup branch for commits, named stash for loose files), then the task's files go back to the state before the task. Decision drafts stay; the worker's notes move into the Blocked note."""
    kept = {}
    wnotes = worker_notes(root, task_id)
    if head(root) != base:
        name = f"tron/blocked-{task_id.lower()}-{journal['run_id']}"
        existing = set(branch_refs(root))
        k = 1
        while name in existing:
            k += 1; name = f"tron/blocked-{task_id.lower()}-{journal['run_id']}-{k}"
        git_ok(root, "branch", name)
        kept["branch"] = name
    unhide(root)
    if tree_dirty(root):
        n0 = len(git_ok(root, "stash", "list").splitlines())
        git_ok(root, "stash", "push", "-u", "-q", "-m", f"tron {journal['run_id']} {task_id} blocked", "--", ".", ":(exclude,glob)backlog/drafts/**", *EXCLUDE)
        if len(git_ok(root, "stash", "list").splitlines()) > n0:
            kept["stash"] = f"tron {journal['run_id']} {task_id} blocked"
    at_base = set(git_ok(root, "ls-tree", "-r", "--name-only", base).splitlines())
    for f in changed_paths(root, base):
        if KEEP_DRAFT.match(f):
            continue
        if f in at_base:
            git_ok(root, "checkout", base, "--", f)
        else:
            git_ok(root, "rm", "-rf", "-q", "--ignore-unmatch", "--", f)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode:
        git_ok(root, "commit", "-q", "-m", f"{task_id}: Tron run reset the files of the blocked task")
    note = f"Blocked by the Tron runner (run {journal['run_id']}): {reason}. Failed work kept: " + (", ".join(f"{k} {v}" for k, v in kept.items()) or "none")
    if wnotes:
        note += "\nWorker notes before the reset:\n" + wnotes
    set_blocked(root, tron, task_id, note)
    refs0.clear(); refs0.update(branch_refs(root))
    return kept


def find_journal(root, milestone, run_id):
    d = root / JOURNAL_DIR
    if run_id:
        p = d / f"run-{run_id}.json"
        return p if p.is_file() else None
    open_ = []
    for p in sorted(d.glob("run-*.json")) if d.is_dir() else []:
        try:
            j = json.loads(p.read_text())
        except ValueError:
            continue
        if j.get("milestone") == milestone and not j.get("complete"):
            open_.append((j.get("started", ""), p))
    return max(open_)[1] if open_ else None


def acs_at(root, commit):
    """AC hashes of the task files at a commit (like snapshot_acs on the tree)."""
    out = {}
    for f in git_ok(root, "ls-tree", "-r", "--name-only", commit, "backlog/tasks").splitlines():
        m = re.match(r"backlog/tasks/task-(\d+) - .*\.md$", f)
        if m:
            out[f"TASK-{m.group(1)}"] = ac_hash(git_ok(root, "show", f"{commit}:{f}"))
    return out


def move_base_past_repairs(root, journal, ip, tron):
    """TASK-366: commits made between the run's stop and this resume are repairs by the user, not the interrupted task's work.
    The task's base moves to HEAD so the gate does not count them; only when the task's own part (base..stop) is clean."""
    stop = journal.pop("stop_head", None) or {}
    cur = head(root)
    if not stop.get("commit") or stop.get("ip_base") != ip["base"] or stop["commit"] == cur:
        return None
    if subprocess.run(["git", "merge-base", "--is-ancestor", stop["commit"], cur], cwd=root).returncode:
        return None
    prot = protected_paths(root, tron)
    own = [f for f in git_ok(root, "diff", "--name-only", "--no-renames", ip["base"], stop["commit"]).splitlines()
           if any(fnmatch.fnmatchcase(f, pat) for pat in prot)]
    own_acs = acs_at(root, stop["commit"])
    if own or any(own_acs.get(i) != h for i, h in ip["acs_before"].items()):
        return None  # the task's own damage stays under the gate
    n = len(git_ok(root, "rev-list", f"{stop['commit']}..{cur}").splitlines())
    moved = {"from": ip["base"], "to": cur, "repair_commits": n}
    ip["base"], ip["acs_before"] = cur, snapshot_acs(root)
    return moved


def recover(root, journal, jpath, tron=None):
    """A killed runner leaves a session unfinished: loose files go into a named stash; the task goes on from its recorded base."""
    ip = journal.get("in_progress")
    if not ip:
        return None
    note = {"task": ip["task"], "base": ip["base"]}
    unhide(root)
    if tree_dirty(root):
        name = f"tron {journal['run_id']} {ip['task']} interrupted"
        n0 = len(git_ok(root, "stash", "list").splitlines())
        git_ok(root, "stash", "push", "-u", "-q", "-m", name, "--", ".", *EXCLUDE)
        if len(git_ok(root, "stash", "list").splitlines()) > n0:
            note["stash"] = name
    moved = move_base_past_repairs(root, journal, ip, tron or {}) if not tree_dirty(root) else None
    if moved:
        note["base_moved"] = moved
        print(f"resume: base of {ip['task']} moved past {moved['repair_commits']} repair commit(s) made after the stop")
    journal.setdefault("recovered", []).append(note)
    write_journal(jpath, journal)
    print(f"resume: session for {ip['task']} was interrupted" + (f"; loose files are in the stash '{note['stash']}'" if "stash" in note else ""))
    return ip


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


# ---- report (generated from journal and backlog only) ----

def money(x, partial=False):
    return "unknown" if x is None else (f"at least {x:.2f} USD" if partial else f"{x:.2f} USD")


def cost_of(sessions):
    """(sum of the known costs, whether some session has no cost data); None when no session reports a cost."""
    known = [s["cost_usd"] for s in sessions if s.get("cost_usd") is not None]
    return (sum(known) if known else None), len(known) < len(sessions)


def duration(s):
    try:
        f = "%Y-%m-%dT%H:%M:%SZ"
        return (datetime.datetime.strptime(s["end"], f) - datetime.datetime.strptime(s["start"], f)).total_seconds()
    except (KeyError, ValueError, TypeError):
        return None


def build_report(root, journal, tron):
    """Markdown report of a run: what is ready to look at, what failed, what the user must decide, what it cost."""
    sess, tasks = journal["sessions"], journal["tasks"]
    files, out = task_files(root), []
    steps = lambda v: " -> ".join(f"{x['step']}: {x['result']}" for x in v.get("ladder", []))
    acc = [i for i, v in tasks.items() if v["state"] == "accepted"]
    blk = [i for i, v in tasks.items() if v["state"] == "blocked"]
    out += [f"# Tron mode report: run {journal['run_id']} ({journal['milestone']})", "",
            f"Branch `{journal['branch']}`, run start commit `{journal['start_commit'][:10]}`. State: " +
            (("complete" + (f" ({journal['stop_reason']})" if "stranded" in (journal.get("stop_reason") or "") else "")) if journal.get("complete") else f"not complete ({journal.get('stop_reason') or 'running'})") +
            f". Review with: `git log --oneline {journal['start_commit'][:10]}..{journal['branch']}`. The run did not push, tag or merge; merging is your decision.", ""]
    start_cmd = tron.get("preview_cmd") or tron.get("smoke_cmd") or "not configured"
    start_cmd = " ".join(start_cmd) if isinstance(start_cmd, list) else start_cmd
    out += ["## Look at this first", "",
            f"- Preview start command: `{start_cmd}`",
            f"- Preview URL: {tron.get('preview_url', 'not configured')}",
            "- The first core flows are tested by you: " + (", ".join(acc) or "(no accepted task)")]
    out += [f"- Unattended retro (analysis): {journal['retro']}"] if journal.get("retro") else []
    out += [f"- Unattended retro failed: {journal['retro_error']}"] if journal.get("retro_error") else []
    out += [f"- The run ended by an error: {journal['error']}. Run again to continue after fixing it"
            + (f"; loose files of that moment are in the stash '{journal['error_stash']}'" if journal.get("error_stash") else "")
            + (f"; cleanup failed: {journal['error_cleanup']}" if journal.get("error_cleanup") else "")] if journal.get("error") else []
    out += [""] + retro_changes_report(journal) + calibration_report(journal)
    out += ["## Accepted tasks: acceptance criteria and evidence", ""]
    for i in acc:
        f = files.get(i)
        if not f:
            out.append(f"- {i}: task file not found"); continue
        _, acs, notes = parse_task(f.read_text())
        out.append(f"### {i}")
        out += [f"- ladder: {steps(journal['tasks'][i])}"] if journal["tasks"].get(i, {}).get("ladder") else []
        for ticked, n, text in acs:
            ev = re.search(rf"^\s*AC#{n}: (E\d.*)$", notes, re.M)
            out.append(f"- [{'x' if ticked else ' '}] AC#{n} {text}" + (f" (evidence: {ev.group(1)[:160]})" if ev else " (no evidence line)"))
    if not acc:
        out.append("(none)")
    out += ["", "## Evaluator findings", ""]
    vfiles = sorted((root / JOURNAL_DIR).glob(f"verdict-{journal['run_id']}-*.json"))
    for vf in vfiles:
        try:
            v = json.loads(vf.read_text())
        except ValueError:
            continue
        out.append(f"- {v.get('target')}: {v.get('verdict')} ({len(v.get('findings', []))} finding(s)) [{vf.name}]")
        for fi in v.get("findings", []):
            out.append(f"  - {fi.get('ac', '-')} at {fi.get('location', '?')}: {fi.get('scenario', '')}")
        for a in v.get("assumption_flags", []):
            out.append(f"  - assumption conflict: {a.get('assumption', '?')} ({a.get('conflict', '?')})")
    if not vfiles:
        out.append("(no evaluator verdict in this run)")
    out += ["", "## Assumptions made", ""]
    al = assumptions(root, list(tasks))
    groups = {}
    for a in al:
        b = assumption_basis(a)
        groups.setdefault(b.lower() if b and b.lower() == "none" else (b or "none"), []).append(a if b is not None else a + "  [no basis named]")
    for b in sorted(groups, key=lambda k: (k != "none", k)):
        out += [f"Basis: {b}" + (" (needs your ruling)" if b == "none" else "")] + [f"- {a}" for a in groups[b]] + [""]
    out += [] if al else ["(none recorded)"]
    out += ["", "## Blocked tasks", ""]
    for i in blk:
        v = tasks[i]
        out.append(f"- {i}: {v['reason']}" + (f" (failed work kept: {', '.join(f'{k} {x}' for k, x in v.get('kept', {}).items())})" if v.get("kept") else ""))
        out += [f"  - ladder: {steps(v)}"] if v.get("ladder") else []
    strand = {k: b for k, b in stranded_by(root, journal["milestone"], blk).items() if k not in tasks}
    for b in blk:
        waits = sorted(k for k, x in strand.items() if x == b)
        out += [f"- stranded: {', '.join(waits)} wait(s) for {b} (directly or indirectly) and never became ready; unblock {b} and run again"] if waits else []
    for i, v in tasks.items():
        if v["state"] == "split":
            out.append(f"- {i}: split by the Doctor into {', '.join(v.get('subtasks', []))}; closes when all of them pass (not closed yet" + "".join(f"; {x} is {tasks.get(x, {}).get('state', 'not run')}" for x in v.get("subtasks", []) if tasks.get(x, {}).get("state") != "accepted") + ")")
            out.append(f"  - ladder: {steps(v)}")
    out += ["(none)"] if not blk and not any(v["state"] == "split" for v in tasks.values()) else []
    out += ["", "## Open questions for you", ""]
    q = []
    d = root / "backlog/drafts"
    if d.is_dir():
        added = set(git_ok(root, "diff", "--name-only", "--diff-filter=A", journal["start_commit"], "HEAD", "--", "backlog/drafts").splitlines())
        for rel in sorted(added):
            p = root / rel
            if p.is_file():
                title = re.search(r"^title: *(.+?) *$", p.read_text(), re.M)
                q.append(f"- {title.group(1).strip(chr(39) + chr(34)) if title else rel} ({rel})")
    out += q or ["(no new draft task)"]
    out += ["", "## Cost and time", ""]
    tot, part = cost_of(sess)
    wall = journal.get("wall_seconds")
    out += [f"- Total cost: {money(tot, part)}; sessions: {len(sess)}; wall time: " + (f"{wall / 3600:.2f} h" if wall else "unknown"), "", "| Task | Sessions | Repairs | Cost |", "| --- | --- | --- | --- |"]
    for i in list(tasks) + [x for x in dict.fromkeys(s["task"] for s in sess) if x not in tasks]:
        ss = [s for s in sess if s["task"] == i and (s["role"] != "evaluator" or i == "milestone")]
        c, pt = cost_of(ss) if ss else (None, False)
        out.append(f"| {i} | {len(ss)} | {tasks.get(i, {}).get('repairs', '-')} | {money(c, pt)} |")
    out += ["", "| Role | Sessions | Cost | Models |", "| --- | --- | --- | --- |"]
    for role in sorted({s["role"] for s in sess}):
        ss = [s for s in sess if s["role"] == role]
        c, pt = cost_of(ss)
        out.append(f"| {role} | {len(ss)} | {money(c, pt)} | {', '.join(sorted({s.get('model') or 'unknown' for s in ss}))} |")
    n_acc, n_blk = len(acc), len(blk)
    # a repair answers a failed gate or evaluator verdict (task or milestone); journals before TASK-304 lack "repair" on milestone sessions
    repair_sessions = sum(1 for s in sess if s["role"] == "worker" and (s.get("repair") or s["task"] == "milestone"))
    worker_sessions = [s for s in sess if s["role"] == "worker"]
    out += ["", "## Metrics", ""]
    out.append("- Cost per accepted task: " + (money(tot / n_acc, part) if tot is not None and n_acc else "unknown"))
    out.append("- Repair rate: " + (f"{repair_sessions} repair session(s) in {len(worker_sessions)} worker session(s) ({repair_sessions / len(worker_sessions):.0%})" if worker_sessions else "unknown"))
    out.append("- Blocked rate: " + (f"{n_blk} of {n_acc + n_blk} settled task(s) ({n_blk / (n_acc + n_blk):.0%})" if n_acc + n_blk else "unknown"))
    ud = journal.get("user_defects", [])
    out.append("- Evaluator misses: " + (f"{len(missed(journal))} of {len(ud)} defect(s) you found were in tasks the evaluator had passed" if ud
                                         else "0 (you found no defect)" if journal.get("defects_reviewed")
                                         else "unknown until you answer the defects question (`tron.py defect`, or `--none`)"))
    out.append("")
    return "\n".join(out)


def cmd_report(args):
    root = pathlib.Path(args.root).resolve()
    d = root / JOURNAL_DIR
    if args.run_id:
        jp = d / f"run-{args.run_id}.json"
    else:
        cand = sorted(d.glob("run-*.json"), key=lambda p: json.loads(p.read_text()).get("started", "")) if d.is_dir() else []
        jp = cand[-1] if cand else None
    if not jp or not jp.is_file():
        raise TronError("no run journal found (docs/agent/tron/run-<id>.json)")
    journal = json.loads(jp.read_text())
    try:
        tron = load_config(root, args.config)
    except TronError:
        tron = {}
    out = d / f"REPORT-{journal['run_id']}.md"
    out.write_text(build_report(root, journal, tron))
    print(f"report written: {out.relative_to(root)}")
    return 0


def finish(journal, jpath, reason=None, complete=False, root=None):
    if root is not None:  # where the run stopped: commits after this one are the user's repairs (TASK-366)
        try:
            journal["stop_head"] = {"commit": head(root), "ip_base": (journal.get("in_progress") or {}).get("base")}
        except TronError:
            pass
    journal["ended"] = now()
    journal["stop_reason"] = reason
    journal["complete"] = complete
    write_journal(jpath, journal)


def cmd_run(args):
    root = pathlib.Path(args.root).resolve()
    tron = load_config(root, args.config)
    milestone = args.milestone
    if tron.get("pause_after", "task") not in ("task", "milestone"):
        raise TronError("config tron.pause_after must be 'task' or 'milestone'")
    jpath = find_journal(root, milestone, args.run_id)
    run_id = args.run_id or (jpath.stem[4:] if jpath else datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    first = ready_tasks(root, milestone, tron.get("blocked_status", "Blocked"))
    if args.dry_run:
        if not first:
            print(f"dry run: no ready task in {milestone}")
            return 0
        print(f"dry run: run {run_id}{' (resumes a journal)' if jpath else ''}, branch tron/{milestone}, ready tasks in order: {', '.join(first)}")
        for t in first:
            cmd = fill(command_for(tron, "worker"), {"prompt": tron.get("prompt", DEFAULT_PROMPT).replace("{task_id}", t),
                                                    "session_id": "<new uuid>", "task_id": t, "run_id": run_id, "milestone": milestone})
            print(f"  {t}: STEM_TRON=1 {' '.join(cmd)}")
        print("dry run: nothing started (later tasks may become ready as earlier ones finish)")
        return 0
    if not jpath and not first:
        print(f"no ready task in {milestone}; nothing to do")
        return 0
    if args.detach:
        return detach_run(root, args, milestone, run_id)
    lock = root / JOURNAL_DIR / "LOCK"  # two runners on one checkout would corrupt each other
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.is_file():
        try:
            pid = int(lock.read_text().strip())
        except ValueError:
            pid = 0
        if pid and pid_alive(pid):
            raise TronError(f"another run is active (pid {pid}, {lock.relative_to(root)})")
    lock.write_text(str(os.getpid()))
    os.environ["STEM_TRON_RUN"] = run_id  # the runner's commits and its sessions pass the pre-commit LOCK check (TASK-366)
    ctx = {}  # run_loop puts its clean-end handler here once the journal exists
    try:
        return run_loop(root, tron, args, milestone, jpath, run_id, ctx)
    except Exception as e:  # TASK-365: an error mid-run ends the run like a stop (journal, report, clean index), never a dead process
        if "fail" not in ctx:
            raise
        ctx["fail"](e)
        if not isinstance(e, TronError):
            raise
        print(f"tron: run ended by an error: {e}; see docs/agent/tron/REPORT-{run_id}.md", file=sys.stderr)
        return 2
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def detach_run(root, args, milestone, run_id):
    """TASK-366: the run lives in its own process session (no terminal, no stdin), so ending the chat that started it
    cannot end the run. This process only waits for it and passes on its exit code; killing the waiter leaves the run going."""
    log = root / JOURNAL_DIR / f"run-{run_id}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), "run", "--milestone", milestone, "--run-id", run_id, "--root", str(root)]
    cmd += ["--config", args.config] if args.config else []
    cmd += ["--max-tasks", str(args.max_tasks)] if args.max_tasks is not None else []
    cmd += ["--accept-damage"] if args.accept_damage else []
    with open(log, "a") as out:
        proc = subprocess.Popen(cmd, cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    print(f"run {run_id} started as its own process (pid {proc.pid}); log {log.relative_to(root)}; "
          f"report docs/agent/tron/REPORT-{run_id}.md. Stopping this command does not stop the run (STOP file does).", flush=True)
    return proc.wait()


def milestone_evaluation(root, tron, journal, jpath, accepted, start_commit, max_repairs, no_count, fin, branch, refs0, run_id, milestone):
    """Evaluator at milestone end; a fail gets repair sessions like a gate fail (bounded by max_repairs, cost, time and the stop file).
    Returns an exit code to end the run, None to complete it."""
    files = task_files(root)
    titles = "; ".join(f"{i}: {task_intent(files[i].read_text()).splitlines()[0]}" for i in accepted if i in files)
    while True:
        why = no_count()
        if why:
            fin(why); print(f"run ended: {why}; run again to continue"); return 0
        print(f"milestone {milestone}: evaluator session")
        ev = evaluate(root, tron, journal, jpath, "milestone", start_commit, None, accepted,
                      f"Milestone {milestone}: the accepted tasks of this run work together as intended. Tasks: {titles}", no_count)
        if "unavailable" in ev:
            fin(ev["unavailable"]); print("run ended early; run again to continue", file=sys.stderr); return 0
        if "damage" in ev:
            journal["aborted"] = "gate damage: " + ev["damage"]; journal["damage"] = True; fin(journal["aborted"])
            print(f"run stopped: {ev['damage']}", file=sys.stderr); return 4
        if ev["verdict"] == "pass" and not ev["assumption_flags"]:
            journal["milestone_verdict"] = "pass"; journal["milestone_repairs"] = 0; write_journal(jpath, journal)
            print(f"milestone {milestone}: evaluator says pass; {ev['file']}")
            return None
        repairs = journal.get("milestone_repairs", 0)  # kept in the journal: a resume does not get a fresh budget
        g = verdict_failure(ev)
        if repairs >= max_repairs or g["failures"][0]["unrepairable"]:
            fin(f"milestone evaluation failed ({'not repairable by a session' if g['failures'][0]['unrepairable'] else f'after {repairs} repair(s)'}): {ev['file']}")
            print(f"milestone {milestone}: evaluator says fail; read {ev['file']}", file=sys.stderr)
            return 0
        journal["milestone_repairs"] = repairs + 1
        why = no_count()
        if why:
            fin(why); print(f"run ended: {why}; run again to continue"); return 0
        base, acs_before = head(root), snapshot_acs(root)
        journal["in_progress"] = {"task": "baseline", "base": base, "acs_before": acs_before}
        prompt = ("The independent evaluation of the milestone found problems (unattended Tron mode session, STEM_TRON=1; read R-TRON first). "
                  f"Fix exactly these findings and nothing else (repair {repairs + 1} of {max_repairs}):\n" + g["failures"][0]["detail"])
        before = fingerprint(root)
        entry, up = sessions_with_retry(root, tron, "worker", "milestone", run_id, milestone, journal, jpath, prompt, abort_check=no_count)
        if not up:
            fin(entry.get("retry_aborted") or "API unavailable after retries"); return 0
        entry["repair"] = repairs + 1  # counted by the report's repair rate
        entry["gate"] = gate(root, tron, None, base, acs_before, start_commit, branch, refs0)
        journal.pop("in_progress", None)
        write_journal(jpath, journal)
        if not entry["gate"]["passed"] or fingerprint(root) == before:
            stop = sorted({f["check"] for f in entry["gate"]["failures"]} & STOPPING)
            journal["aborted"] = ("gate damage: " + ", ".join(stop)) if stop else ("milestone repair failed the gate" if not entry["gate"]["passed"] else "milestone repair left no diff")
            journal["damage"] = bool(stop)
            fin(journal["aborted"])
            print(f"milestone repair stopped: {journal['aborted']}", file=sys.stderr)
            return 4 if stop else 3


def run_loop(root, tron, args, milestone, jpath, run_id, ctx=None):
    t0 = time.time()
    max_tasks = args.max_tasks if args.max_tasks is not None else tron.get("max_tasks")
    max_repairs = int(tron.get("max_repairs", 3))
    pause_after = tron.get("pause_after", "task")
    blocked_status = tron.get("blocked_status", "Blocked")
    stop_path = root / STOP_FILE
    resume_ip = None
    if jpath:
        journal = json.loads(jpath.read_text())
        if journal.get("complete"):
            raise TronError(f"run {run_id} is already complete; start a new one without --run-id")
        if journal.get("damage"):
            if not args.accept_damage:
                raise TronError(f"run {run_id} stopped for gate damage ({journal.get('aborted')}). Inspect the branch first; "
                                "to go on anyway run again with --accept-damage (the damage then becomes part of the run branch)")
            journal.setdefault("damage_history", []).append(journal.pop("aborted", None)); journal["damage"] = False
        branch = journal["branch"]
        if git_ok(root, "branch", "--show-current").strip() != branch:
            if tree_dirty(root):
                raise TronError("working tree is not clean; commit or stash first (the run continues on its own branch)")
            git_ok(root, "checkout", "-q", branch)
        resume_ip = recover(root, journal, jpath, tron)
        if tree_dirty(root):
            raise TronError("working tree is not clean; commit or stash first")
        journal["ended"] = None; journal["stop_reason"] = None
        if journal.get("retro"):  # the retro of the earlier stop is kept under its own name; the run end writes a new one (TASK-299)
            old = root / journal["retro"]
            keep = old.with_name(f"{old.stem}-stop{len(journal.get('retro_history', [])) + 1}.md")
            if old.is_file():
                old.rename(keep)
            journal.setdefault("retro_history", []).append(str(keep.relative_to(root)))
            journal.pop("retro")
        journal.pop("retro_error", None)
        if journal.get("error"):  # the error of the earlier stop stays in the history; the report shows only a current one
            journal.setdefault("error_history", []).append({k: journal.pop(k) for k in ("error", "error_stash", "error_cleanup") if k in journal})
        print(f"resuming run {run_id} on branch {branch}; {len(journal['tasks'])} task(s) settled before")
    else:
        branch, existed = prepare_branch(root, milestone, False)
        jpath = root / JOURNAL_DIR / f"run-{run_id}.json"
        journal = {"run_id": run_id, "milestone": milestone, "branch": branch, "started": now(), "ended": None, "complete": False,
                   "stop_reason": None, "start_commit": head(root), "ac_hashes": snapshot_acs(root), "tasks": {}, "sessions": []}
        print(f"run {run_id} on branch {branch} ({'reused' if existed else 'created'}); journal {jpath.relative_to(root)}")
    start_commit, acs0 = journal["start_commit"], journal["ac_hashes"]
    refs0 = branch_refs(root)  # the user's own work between sessions is legitimate: the reference is taken now
    journal.setdefault("refs_start", refs0)
    if journal["sessions"]:
        journal.setdefault("refs_resumes", []).append({"at": now(), "refs": refs0})
    wall0 = journal.get("wall_seconds", 0)
    journal["no_diff_blocks"] = journal.get("no_diff_blocks", 0)
    write_journal(jpath, journal)

    def fin(reason, complete=False):
        journal["wall_seconds"] = wall0 + time.time() - t0
        finish(journal, jpath, reason, complete, root)
        if tron.get("retro") == "on" and not journal.get("retro"):  # unattended retro analysis at every run end, stopped runs included (TASK-299); a failure never fails the run
            try:
                retro_for_run(root, tron, journal, jpath)
            except (TronError, OSError, ValueError) as e:
                journal["retro_error"] = str(e)[:300]; write_journal(jpath, journal)
        if complete and tron.get("retro_apply") == "on":  # tier 1 and 2 changes, experiment checks (R-TRON "Retro changes"); never fails the run
            try:
                apply_retro(root, tron, journal, jpath)
            except (TronError, OSError, ValueError) as e:
                journal["retro_apply_error"] = str(e)[:300]; write_journal(jpath, journal)
        try:  # one report per run, rewritten whenever the run stops
            (root / JOURNAL_DIR / f"REPORT-{journal['run_id']}.md").write_text(build_report(root, journal, tron))
        except (OSError, TronError, KeyError, ValueError):
            pass

    def fail(e):
        """End the run after an error: loose and staged files go into a named stash (a resume needs a clean tree), then fin()."""
        journal["error"] = f"{type(e).__name__}: {e}"[:300]
        try:
            unhide(root)
            if tree_dirty(root) or git_ok(root, "diff", "--cached", "--name-only").strip():
                name = f"tron {journal['run_id']} error leftovers"
                n0 = len(git_ok(root, "stash", "list").splitlines())
                git_ok(root, "stash", "push", "-u", "-q", "-m", name, "--", ".", *EXCLUDE)
                if len(git_ok(root, "stash", "list").splitlines()) > n0:
                    journal["error_stash"] = name
            git_ok(root, "reset", "-q")  # nothing the runner staged stays in the index
        except (TronError, OSError) as e2:
            journal["error_cleanup"] = str(e2)[:300]
        fin("runner error: " + journal["error"])

    if ctx is not None:
        ctx["fail"] = fail

    def stop_reason(count_tasks=True):
        if stop_path.is_file():
            return "stop file docs/agent/tron/STOP"
        return limit_hit(journal, tron, max_tasks if count_tasks else None, t0)

    def settle(task_id, base, reason, repairs):
        kept = block_task(root, tron, task_id, base, reason, journal, refs0)
        stranded = sorted(stranded_by(root, milestone, [task_id]))
        journal["tasks"][task_id] = {"state": "blocked", "reason": reason, "repairs": repairs, "kept": kept, "stranded": stranded}
        journal.pop("blocking", None); journal.pop("in_progress", None)
        write_journal(jpath, journal)
        print(f"{task_id}: BLOCKED ({reason})" + (f"; stranded (never ready in this run): {', '.join(stranded)}" if stranded else ""))

    def do_split(task_id, plan, ladder):
        """Subtasks of the Doctor's split; a failure becomes a draft question, never a half-made split."""
        try:
            made = create_subtasks(root, tron, journal, task_id, start_text(root, task_id, start_commit) or "", plan)
        except TronError as e:
            dn = write_question_draft(root, journal, f"Split of {task_id} proposed by the Doctor could not be created",
                                      f"Run {journal['run_id']}: creating the subtasks failed ({e}). {task_id} stays Blocked.", "tron-doctor")
            ladder.append({"step": "split", "result": "failed: " + str(e)[:150], "draft": dn})
            print(f"{task_id}: split failed ({e}); see {dn}")
            return
        journal["tasks"][task_id].update(state="split", subtasks=made)
        ladder.append({"step": "split", "result": "created " + ", ".join(made)})
        print(f"{task_id}: split into {', '.join(made)}")

    if journal.get("blocking"):  # the runner was killed while blocking a task: finish that step first
        bl = journal["blocking"]
        settle(bl["task"], bl["base"], bl["reason"], bl.get("repairs", 0))
        lad = bl.get("ladder") or []
        if bl.get("split_plan") and journal["tasks"][bl["task"]].get("state") != "split":
            do_split(bl["task"], bl["split_plan"], lad)
        if lad:
            journal["tasks"][bl["task"]]["ladder"] = lad
        write_journal(jpath, journal)
        resume_ip = None

    no_count = lambda: stop_reason(count_tasks=False)  # limits that end a session in flight (not the task count)
    while True:
        for pid in close_split_parents(root, tron, journal):
            print(f"{pid}: closed, all subtasks of its split are accepted")
        write_journal(jpath, journal)
        task_resumed = resume_ip is not None and resume_ip.get("task") != "baseline" and resume_ip.get("task") not in journal["tasks"]
        todo = [] if task_resumed else [t for t in ready_tasks(root, milestone, blocked_status) if t not in journal["tasks"] and t in acs0]
        if not task_resumed and not todo:  # milestone end: the task count must not keep the evaluation from running
            why = no_count()
            if why:
                fin(why); print(f"run ended: {why}; run again to continue"); return 0
            accepted = [i for i, v in journal["tasks"].items() if v["state"] == "accepted"]
            if accepted and tron.get("evaluator", "milestone") != "off" and journal.get("milestone_verdict") != "pass":
                res = milestone_evaluation(root, tron, journal, jpath, accepted, start_commit, max_repairs, no_count, fin, branch, refs0, run_id, milestone)
                if res is not None:
                    return res
            strand = stranded_by(root, milestone, [i for i, v in journal["tasks"].items() if v["state"] == "blocked"])
            strand = {k: v for k, v in strand.items() if k not in journal["tasks"]}
            fin("no ready task left" + ("; stranded: " + ", ".join(f"{k} waits for Blocked {v}" for k, v in sorted(strand.items())) if strand else ""), complete=True)
            print(f"run {run_id} complete after {len(journal['tasks'])} task(s)")
            return 0
        why = stop_reason()
        if why:
            fin(why)
            print(f"run ended: {why}; run again to continue")
            return 0
        if not task_resumed and verify(root, tron)[0]:  # baseline: a red branch gets a repair session before the next task
            print("baseline verification failed; starting a repair session")
            base, acs_before = head(root), snapshot_acs(root)
            journal["in_progress"] = {"task": "baseline", "base": base, "acs_before": acs_before}
            entry, up = sessions_with_retry(root, tron, "worker", "baseline", run_id, milestone, journal, jpath,
                                            baseline_prompt(root, tron, milestone), abort_check=stop_reason)
            if not up:
                fin(entry.get("retry_aborted") or "API unavailable after retries"); print("run ended early; run again to continue", file=sys.stderr); return 0
            entry["gate"] = gate(root, tron, None, base, acs_before, start_commit, branch, refs0)
            journal.pop("in_progress", None)
            write_journal(jpath, journal)
            if not entry["gate"]["passed"]:
                stop = sorted({f["check"] for f in entry["gate"]["failures"]} & STOPPING)
                journal["aborted"] = "baseline red after repair" if not stop else "gate damage: " + ", ".join(stop)
                journal["damage"] = bool(stop)
                fin(journal["aborted"])
                print("baseline still red after the repair session: run stopped (nothing is built on a red branch)", file=sys.stderr)
                return 4 if stop else 3
        resume_ip_task = resume_ip if task_resumed else None
        resume_ip = None
        if resume_ip_task and resume_ip_task["task"] not in journal["tasks"]:
            task_id = resume_ip_task["task"]
            base, acs_before = resume_ip_task["base"], resume_ip_task["acs_before"]  # commits of the interrupted session stay under the gate
            repairs, last_sig = resume_ip_task.get("repairs", 0), resume_ip_task.get("last_sig")
            last_sig = [tuple(x) for x in last_sig] if last_sig else None
        else:
            task_id = todo[0]
            base, acs_before = head(root), snapshot_acs(root)
            repairs, last_sig = 0, None
        journal["in_progress"] = {"task": task_id, "base": base, "acs_before": acs_before, "repairs": repairs, "last_sig": last_sig}
        prompt = None
        outcome = None
        limit, ladder, doctored, hint, split_plan = max_repairs, [], False, None, None
        rip = resume_ip_task if resume_ip_task and resume_ip_task["task"] == task_id else None
        if rip and rip.get("ladder") is not None:  # the ladder state survives a stop: the Doctor runs once per task
            limit, ladder, doctored, hint = rip.get("limit", limit), rip["ladder"], rip.get("doctored", False), rip.get("hint")

        def persist():
            journal["in_progress"].update(limit=limit, ladder=ladder, doctored=doctored, hint=hint)
            write_journal(jpath, journal)
        if rip and rip.get("ladder") is not None:
            persist()
        while True:
            print(f"{task_id}: starting " + ("worker session" if repairs == 0 else f"repair session {repairs}"))
            before = fingerprint(root)
            entry, up = sessions_with_retry(root, tron, "worker", task_id, run_id, milestone, journal, jpath, prompt, abort_check=stop_reason)
            if not up:
                fin(entry.get("retry_aborted") or "API unavailable after retries"); print("run ended early; run again to continue", file=sys.stderr); return 0
            entry["repair"] = repairs
            g = entry["gate"] = gate(root, tron, task_id, base, acs_before, start_commit, branch, refs0)
            write_journal(jpath, journal)
            print(f"{task_id}: exit {entry['exit_code']}, gate " + ("passed" if g["passed"] else "FAILED: " + "; ".join(f["reason"] for f in g["failures"]))
                  + (f", cost {entry['cost_usd']}" if entry["cost_usd"] is not None else ""))
            if g["passed"] and tron.get("evaluator", "milestone") != "off":
                tf = task_files(root).get(task_id)
                # labels are read from the run-start commit: a session cannot switch the evaluation off by editing them
                text0 = start_text(root, task_id, start_commit) or (tf.read_text() if tf else "")
                if tf and eval_due(tron, text0):
                    print(f"{task_id}: evaluator session")
                    ev = evaluate(root, tron, journal, jpath, task_id, base, g, [task_id], task_intent(tf.read_text()), no_count)
                    if "unavailable" in ev:
                        fin(ev["unavailable"]); print("run ended early; run again to continue", file=sys.stderr); return 0
                    if "damage" in ev:
                        journal["aborted"] = "gate damage: " + ev["damage"]; journal["damage"] = True; fin(journal["aborted"])
                        print(f"run stopped: {ev['damage']}", file=sys.stderr); return 4
                    if ev["verdict"] == "fail" or ev["assumption_flags"]:
                        g = entry["gate_after_evaluator"] = verdict_failure(ev)
                        print(f"{task_id}: evaluator says fail ({len(ev['findings'])} finding(s)); {ev['file']}")
                    else:
                        print(f"{task_id}: evaluator says pass; {ev['file']}")
            if g["passed"]:
                outcome = ("accepted", None); break
            stop = sorted({f["check"] for f in g["failures"]} & STOPPING)
            if stop:
                journal["aborted"] = "gate damage: " + ", ".join(stop); journal["damage"] = True
                fin(journal["aborted"])
                print(f"run stopped after {task_id}: {', '.join(stop)} (see the journal); nothing was discarded", file=sys.stderr)
                return 4
            sig = signature(g)
            if any(f.get("unrepairable") for f in g["failures"]):
                outcome = ("blocked", "the evaluator could not verify or flagged assumptions; a repair session cannot fix that: " + g["failures"][0]["detail"][:200].replace("\n", " ")); break
            stall = None
            if fingerprint(root) == before:
                if entry["exit_code"] == 127:  # the agent command does not start: blocking every task would not help
                    fin("worker command could not start (exit 127): fix the config, then run again"); print("worker command could not start", file=sys.stderr); return 0
                stall = "the session left no diff"
            elif sig == last_sig:
                stall = "the same failure twice in a row: " + "; ".join(r for _, r, _ in sig)
            fail_reason = stall or f"still failing after {limit} repair(s): " + "; ".join(r for _, r, _ in sig)
            if tron.get("doctor_cmd") and not doctored and (stall or repairs >= limit - 1):
                doctored = True
                persist()
                tf = task_files(root).get(task_id)
                print(f"{task_id}: Doctor session ({stall or str(repairs) + ' failed repair(s)'})")
                t0txt = start_text(root, task_id, start_commit) or (tf.read_text() if tf else "")  # the ACs the split is checked against
                dv = consult_doctor(root, tron, journal, jpath, task_id, base, task_intent(t0txt) if t0txt else task_id,
                                    parse_task(t0txt)[1] if t0txt else [], stop_reason)
                if "unavailable" in dv:
                    fin(dv["unavailable"]); print("run ended early; run again to continue", file=sys.stderr); return 0
                if "damage" in dv:
                    journal["aborted"] = "gate damage: " + dv["damage"]; journal["damage"] = True; fin(journal["aborted"])
                    print(f"run stopped: {dv['damage']}", file=sys.stderr); return 4
                if "none" in dv:
                    ladder.append({"step": "doctor", "result": "no verdict"})
                    outcome = ("blocked", fail_reason + " (the Doctor gave no verdict)"); break
                v = dv["verdict"]
                ladder.append({"step": "doctor", "result": v, "diagnosis": dv["diagnosis"][:300]})
                if v == "retry_with_hint":
                    hint, limit, stall = dv["hint"], max(limit, repairs + 1), None
                    persist()
                if v == "retry_with_hint":
                    pass
                elif v == "environment_problem":
                    print(f"{task_id}: Doctor says environment problem; baseline repair session")
                    b2, a2 = head(root), snapshot_acs(root)
                    be, up = sessions_with_retry(root, tron, "worker", "baseline", run_id, milestone, journal, jpath,
                                                 baseline_prompt(root, tron, milestone) + "\n\nThe Doctor's diagnosis: " + dv["diagnosis"], abort_check=stop_reason)
                    if not up:
                        fin(be.get("retry_aborted") or "API unavailable after retries"); print("run ended early; run again to continue", file=sys.stderr); return 0
                    be["gate"] = gate(root, tron, None, b2, a2, start_commit, branch, refs0)
                    write_journal(jpath, journal)
                    stop2 = sorted({f["check"] for f in be["gate"]["failures"]} & STOPPING)
                    if stop2:
                        journal["aborted"] = "gate damage: " + ", ".join(stop2); journal["damage"] = True; fin(journal["aborted"])
                        print(f"run stopped after the baseline repair: {', '.join(stop2)}", file=sys.stderr); return 4
                    # the task's own work is still in the tree, so a red gate here proves nothing: the next repair session's gate decides
                    ladder.append({"step": "baseline repair", "result": "ran"})
                    hint, limit, stall = "a baseline repair session ran for this environment problem: " + dv["diagnosis"], max(limit, repairs + 1), None
                    persist()
                elif v == "needs_user":
                    dn = write_question_draft(root, journal, f"Question from the Doctor about {task_id}: " + dv["question"][:60],
                                              f"Run {journal['run_id']}, {task_id} kept failing.\n\nDiagnosis: {dv['diagnosis']}\n\nQuestion: {dv['question']}", "tron-doctor")
                    ladder.append({"step": "draft question", "result": dn}); persist()
                    outcome = ("blocked", f"the Doctor needs the user: see {dn} ({dv['question'][:150]})"); break
                else:  # split_task
                    parent_acs = [t for _, _, t in parse_task(start_text(root, task_id, start_commit) or "")[1]]
                    bad = check_split(parent_acs, dv["subtasks"])
                    if bad:
                        dn = write_question_draft(root, journal, f"Split of {task_id} proposed by the Doctor is invalid",
                                                  f"Run {journal['run_id']}: the Doctor proposed splitting {task_id}, but the split is invalid ({bad}).\n\nDiagnosis: {dv['diagnosis']}", "tron-doctor")
                        ladder.append({"step": "split", "result": "invalid: " + bad[:150], "draft": dn})
                        outcome = ("blocked", f"the Doctor's split is invalid ({bad[:120]}): see {dn}"); break
                    split_plan = dv["subtasks"]
                    journal["in_progress"]["split_plan"] = split_plan; persist()
                    outcome = ("blocked", "split by the Doctor: " + dv["diagnosis"][:200]); break
            if stall:
                outcome = ("blocked", stall); break
            last_sig = sig
            repairs += 1
            if repairs > limit:
                outcome = ("blocked", fail_reason); break
            why = stop_reason(count_tasks=False)
            journal["in_progress"].update(repairs=repairs, last_sig=last_sig)
            persist()
            if why:
                fin(why); print(f"run ended: {why}; run again to continue"); return 0
            prompt = repair_prompt(tron, task_id, g, repairs, limit)
            if hint:
                prompt += "\n\nThe Doctor's diagnosis and hint for this repair: " + hint
                ladder.append({"step": f"repair {repairs} with hint", "result": "started"})
                hint = None
        state, reason = outcome
        if state == "blocked":
            wn = worker_notes(root, task_id)
            if re.search(r"\bblock(ed)?\b", wn, re.I):  # the worker blocked on purpose: its reason is the reason
                reason = "the worker blocked the task on purpose: " + wn[:300].replace("\n", " ")
            journal["blocking"] = {"task": task_id, "base": base, "reason": reason, "repairs": repairs, "split_plan": split_plan, "ladder": ladder}
            write_journal(jpath, journal)
            settle(task_id, base, reason, repairs)
            if split_plan:
                do_split(task_id, split_plan, ladder)
            if ladder:
                journal["tasks"][task_id]["ladder"] = ladder
            write_journal(jpath, journal)
            journal["no_diff_blocks"] = journal["no_diff_blocks"] + 1 if "no diff" in reason else 0
            if journal["no_diff_blocks"] >= 2:
                fin("two sessions in a row left no diff: check the agent setup (login, command, permissions), then run again")
                print("two sessions in a row left no diff: run ended", file=sys.stderr)
                return 0
        else:
            journal["no_diff_blocks"] = 0
            journal.pop("in_progress", None)
            journal["tasks"][task_id] = {"state": "accepted", "repairs": repairs}
            journal.setdefault("task_ranges", {})[task_id] = [base, head(root)]  # commits of this task, for the milestone brief (TASK-297)
            if ladder:
                journal["tasks"][task_id]["ladder"] = ladder
            nb = [a for a in assumptions(root, [task_id]) if assumption_basis(a) is None]
            if nb:
                journal["tasks"][task_id]["warnings"] = [f"assumption without a basis: {a[:160]}" for a in nb]
        write_journal(jpath, journal)
        if state == "accepted" and pause_after == "task" and [t for t in ready_tasks(root, milestone, blocked_status) if t not in journal["tasks"] and t in acs0]:
            fin("pause_after task")
            print(f"paused after {task_id} (pause_after task); review: git log --oneline {start_commit[:8]}..HEAD; run again to continue")
            return 0


SWEEP_Q = re.compile(r"^\s*-\s*\[(.)\]\s*Q\d+", re.M)
SWEEP_ID = re.compile(r"[\w.-]+")
# TASK-367: an AC an unattended run cannot meet (user judgement, real data, interface decision) is split out before the run
SWEEP_N = re.compile(r"^\s*-\s*\[(.)\]\s*(N\d+)\s*\((TASK-\d+) AC#(\d+)\)\s*(judgement|real data|interface)\b", re.M)
NEEDS_USER = "## Needs the user"
NEEDS_KIND = {"judgement": "the user's judgement", "real data": "real data", "interface": "an interface decision"}


def sweep_needs_user(text):
    """Flagged ACs of the '## Needs the user' section: (id, task, ac, kind, resolved); resolved = ticked with a 'Resolved:' line."""
    sec = re.search(rf"^{NEEDS_USER}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not sec:
        return []
    body = sec.group(1)
    ms = list(SWEEP_N.finditer(body))
    out = []
    for i, m in enumerate(ms):
        block = body[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(body)]
        done = m.group(1).lower() == "x" and bool(re.search(r"^\s*(?:[-*]\s*)?Resolved:\s*\S", block, re.M | re.I))
        out.append((m.group(2), m.group(3), int(m.group(4)), m.group(5), done))
    return out


def sweep_open(text):
    """Number of questions without a tick and a non-empty 'Answer:' line in their own block."""
    ms = list(SWEEP_Q.finditer(text))
    n = 0
    for i, m in enumerate(ms):
        block = text[m.end():ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        if m.group(1).lower() != "x" or not re.search(r"^\s*(?:[-*]\s*)?Answer:\s*\S", block, re.M | re.I):
            n += 1
    return n


def sweep_answers(text):
    """Answered sweep questions as text blocks ('- [x] Q<n> ...' with its 'Answer:' line), in file order."""
    ms = list(SWEEP_Q.finditer(text))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        block = text[m.start():end].split("\n## ")[0].strip()
        if m.group(1).lower() == "x" and re.search(r"^\s*(?:[-*]\s*)?Answer:\s*\S", block, re.M | re.I):
            out.append(block)
    return out


def baseline_prompt(root, tron, milestone):
    """Prompt of a baseline repair session: configured or default text, the fixed duties, the user's answered sweep questions."""
    parts = [tron.get("baseline_prompt", BASELINE_PROMPT), BASELINE_DUTIES]
    sw = root / f"docs/agent/tron/SWEEP-{milestone}.md"
    answers = sweep_answers(sw.read_text()) if sw.is_file() else []
    if answers:
        parts.append("The user answered these questions before the run (docs/agent/tron/" + sw.name + "); follow the answers "
                     "that concern the red baseline, the rest belong to later tasks:\n" + "\n".join(answers))
    return "\n\n".join(parts)


# kinds of question the planner must not ask (TASK-302); repeated in .claude/agents/planner.md
SWEEP_NOT_QUESTIONS = ("## Not questions",
                       "- A red or flaky baseline: the runner starts a baseline repair session on its own before the next task; do not ask about it.",
                       "- Anything a precedent below answers: do not ask it; name the precedent (e.g. P-1) in the draft acceptance scenario instead.",
                       f"- An AC that needs the user's judgement, real data or an interface decision is no question either: list it under '{NEEDS_USER}' "
                       "(the run cannot meet it alone; it is split out before the run).")


def sweep_brief(root, milestone):
    """Input of the planner: vision, frame, invariants, precedents and every open task of the milestone (intent, ACs, labels)."""
    def read(rel, cap=6000):
        f = root / rel
        return f.read_text()[:cap] if f.is_file() else "(none)"
    vision = next((r for r in ("VISION.md", "docs/VISION.md", "README.md") if (root / r).is_file()), None)
    parts = [f"# Planner brief: milestone {milestone}", "", f"## Vision ({vision})", read(vision) if vision else "(none)", "",
             "## Decision frame", read("docs/agent/DECISION_FRAME.md"), "", "## Invariants", read("docs/agent/INVARIANTS.md"), "",
             "## Precedents", read("docs/agent/PRECEDENTS.md"), "", *SWEEP_NOT_QUESTIONS, "", "## Tasks"]
    for tid, f in task_files(root).items():
        text = f.read_text()
        m = re.search(r"^milestone: *(.+?) *$", text, re.M)
        if not m or m.group(1).strip("'\"") != milestone:
            continue
        st, acs, _ = parse_task(text)
        if st and st.lower() == "done":
            continue
        parts += ["", f"### {tid}", task_intent(text), f"Labels: {', '.join(labels_of(text))}"] + [f"- AC#{n}: {t}" for _, n, t in acs]
    return "\n".join(parts) + "\n"


def cmd_sweep(args):
    """Question sweep (doc-12 11.3 A2-1): a fresh planner session lists what a run would have to ask; writes docs/agent/tron/SWEEP-<milestone>.md."""
    root = pathlib.Path(args.root).resolve()
    if not SWEEP_ID.fullmatch(args.milestone):
        raise TronError(f"invalid milestone id: {args.milestone!r}")
    tron = load_config(root, args.config)
    d = root / "docs/agent/tron"
    out = d / f"SWEEP-{args.milestone}.md"
    if out.exists() and not getattr(args, "force", False):
        raise TronError(f"{out.relative_to(root)} exists (answers would be lost); pass --force to overwrite")
    d.mkdir(parents=True, exist_ok=True)
    brief = d / f"brief-sweep-{args.milestone}.md"
    brief.write_text(sweep_brief(root, args.milestone))
    prompt = (f"You are the planner of an unattended Tron mode run. Read .claude/agents/planner.md and follow it exactly. "
              f"Your brief is {brief.relative_to(root)}. Change no file in the project; answer with the sweep in your final message.")
    if not tron.get("planner_cmd"):
        print("warning: tron.planner_cmd is unset; the planner falls back to worker_cmd, which may edit files", file=sys.stderr)
    before = (tree_state(root), tree_dirty(root))
    entry = run_session(root, tron, "planner", "sweep", f"sweep-{args.milestone}", args.milestone, prompt)
    if (tree_state(root), tree_dirty(root)) != before:
        raise TronError("the planner session changed HEAD, branches or files; nothing written")
    text = entry.pop("_out", "") or ""
    if entry.get("exit_code") or "## Questions" not in text:
        raise TronError(f"planner session gave no usable sweep (exit {entry.get('exit_code')}); tail: {text[-200:]!r}")
    m = re.search(r"^# ", text, re.M)
    body = re.sub(r"\n?```\s*$", "", text[m.start() if m else 0:].rstrip())
    qs = re.search(r"^## Questions\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    bad = [l for l in (qs.group(1).splitlines() if qs else []) if re.match(r"\s*[-*]\s*(\[|Q\d)", l) and not SWEEP_Q.match(l)]
    if not qs or bad:
        raise TronError(f"sweep has no parsable '## Questions' section (lines must be '- [ ] Q<n> ...' or '- none'); bad: {bad[:2]}")
    nu = re.search(rf"^{NEEDS_USER}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    bad = [l for l in (nu.group(1).splitlines() if nu else []) if re.match(r"\s*[-*]\s*(\[|N\d)", l) and not SWEEP_N.match(l)]
    if bad:
        raise TronError(f"sweep has malformed '{NEEDS_USER}' lines (must be '- [ ] N<n> (TASK-n AC#k) judgement|real data|interface: ...'); bad: {bad[:2]}")
    out.write_text(body + "\n")
    n = sweep_open(body)
    flagged = sweep_needs_user(body)
    if flagged:
        print(f"{len(flagged)} AC(s) need the user ({', '.join(f'{t} AC#{a} {k}' for _, t, a, k, _ in flagged)}): split them out of the milestone before the run")
    cost = entry.get("cost_usd")
    print(f"sweep written: {out.relative_to(root)} ({n} open question(s); cost {cost if cost is not None else 'unknown'} USD)")
    print("next: answer the questions with the user (skill tron), tick them '[x]' with 'Answer: ...', commit the file, then run the check")
    return 0


RETRO_LAYERS = ("task_quality", "rule", "environment", "model", "evaluator_miss")
RETRO_METRICS = ("blocked_tasks", "repairs_per_task", "cost_per_accepted_task", "doctor_calls", "evaluator_fails", "sessions_per_task", "evaluator_misses")


def run_metrics(journal):
    """Numbers of one run for the retro: the names are the fixed list RETRO_METRICS."""
    tasks, sess = journal.get("tasks", {}), journal.get("sessions", [])
    acc = [v for v in tasks.values() if v.get("state") == "accepted"]
    cost = sum(s.get("cost_usd") or 0 for s in sess if s.get("role") not in ("retro", "applier"))  # the retro's own cost is not the run's
    n = max(len(tasks), 1)
    return {"blocked_tasks": sum(1 for v in tasks.values() if v.get("state") == "blocked"),
            "repairs_per_task": round(sum(v.get("repairs", 0) for v in tasks.values()) / n, 2),
            "cost_per_accepted_task": round(cost / len(acc), 2) if acc else None,
            "doctor_calls": sum(1 for s in sess if s.get("role") == "doctor"),
            "evaluator_fails": sum(1 for s in sess if s.get("role") == "evaluator" and (s.get("evaluator") or {}).get("verdict") == "fail"),
            "sessions_per_task": round(sum(1 for s in sess if s.get("role") == "worker") / n, 2),
            # defects the user found in tasks the evaluator had passed; unknown until the user answered the defects question
            "evaluator_misses": len(missed(journal)) if journal.get("defects_reviewed") else None}


def retro_brief(root, tron, journal):
    """Input of the retro analyst: journal summary, gate failures, pointers to verdicts and diagnoses, assumptions, metrics, the previous retro."""
    rid = journal["run_id"]
    d = root / JOURNAL_DIR
    parts = [f"# Retro brief: run {rid} (milestone {journal['milestone']})", "", f"Ended: {journal.get('ended')}; reason: {journal.get('stop_reason')}; complete: {journal.get('complete')}", "", "## Tasks"]
    for tid, v in journal.get("tasks", {}).items():
        parts.append(f"- {tid}: {v.get('state')}, repairs {v.get('repairs', 0)}" + (f", reason: {v['reason'][:300]}" if v.get("reason") else ""))
        for x in v.get("ladder", []):
            parts.append(f"  - ladder {x.get('step')}: {x.get('result')}")
    parts += ["", "## Gate failures per session"]
    for e in journal.get("sessions", []):
        g = e.get("gate_after_evaluator") or e.get("gate") or {}
        for f in g.get("failures", []):
            parts.append(f"- {e.get('task')} ({e.get('role')}, transcript {e.get('transcript')}): {f.get('reason')}")
    parts += ["", "## Evaluator verdicts and Doctor diagnoses (read them where a failure needs it)"]
    for pat in (f"verdict-{rid}-*.json", f"doctor-{rid}-*.json"):
        parts += [f"- {p.relative_to(root)}" for p in sorted(d.glob(pat))]
    parts += ["", "## Assumptions"]
    parts += [f"- {a[:200]}" for a in assumptions(root, list(journal.get("tasks", {})))] or ["(none)"]
    parts += ["", "## Defects the user found after the run (an evaluator miss is a failure of layer evaluator_miss)"]
    parts += [f"- {x['id']} {x['task']}: {x['text'][:200]} (evaluator: {x['evaluator']})" for x in journal.get("user_defects", [])] or ["(none recorded)"]
    m = run_metrics(journal)
    parts += ["", "## Metrics of this run (names are the only allowed metrics)", "", "| Metric | Value |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in m.items()]
    prev = [p for p in sorted(d.glob("RETRO-*.md")) if p.stem != f"RETRO-{rid}"]
    parts += ["", "## Previous retro"]
    if prev:
        pj = d / f"run-{prev[-1].stem[6:]}.json"
        pm = run_metrics(json.loads(pj.read_text())) if pj.is_file() else None
        parts += [f"File: {prev[-1].relative_to(root)}", prev[-1].read_text()[:4000], "", "Metrics of the previous run: " + (json.dumps(pm) if pm else "(journal not found)")]
    else:
        parts.append("(no previous retro)")
    path = d / f"brief-{rid}-retro.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n")
    return path


def validate_retro(text, journal):
    """Why a retro file is invalid (list; empty when fine): fixed layers, one layer and an evidence pointer per failure, every blocked task covered, at most three proposals with target, tier and metric from the list, a previous-retro section."""
    errs = []

    def section(name):
        m = re.search(rf"^## {name}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        return [l for l in m.group(1).splitlines() if l.strip()] if m else None
    fails, props, prev = section("Failures"), section("Proposals"), section("Previous retro")
    if fails is None or props is None or prev is None:
        return ["missing section (needs '## Failures', '## Proposals', '## Previous retro')"]
    covered = set()
    for l in fails:
        if re.fullmatch(r"\s*[-*]\s*none\s*", l, re.I):
            continue
        layers = re.findall(r"\blayer:\s*(\w+)", l)
        ev = re.search(r"\bevidence:\s*([^|\s][^|]*)", l)
        if len(layers) != 1 or layers[0] not in RETRO_LAYERS:
            errs.append(f"failure line needs exactly one layer from {RETRO_LAYERS}: {l.strip()[:80]}")
        if not ev:
            errs.append(f"failure line has no evidence pointer: {l.strip()[:80]}")
        covered.update(re.findall(r"TASK-\d+", l))
    for tid, v in journal.get("tasks", {}).items():
        if v.get("state") == "blocked" and tid not in covered:
            errs.append(f"blocked task {tid} has no failure line")
    plist = [l for l in props if not re.fullmatch(r"\s*[-*]\s*none\s*", l, re.I)]
    if len(plist) > 3:
        errs.append(f"{len(plist)} proposals; at most 3")
    for l in plist:
        t, tier, met = re.search(r"\btarget:\s*([^|\s]+)", l), re.search(r"\btier:\s*(\d)", l), re.search(r"\bmetric:\s*(\w+)", l)
        if not t or not tier or tier.group(1) not in "123" or not met or met.group(1) not in RETRO_METRICS or not re.search(r"\beffect:\s*\S", l):
            errs.append(f"proposal needs target, tier 1-3, a metric from {RETRO_METRICS} and an effect: {l.strip()[:80]}")
            continue
        if re.search(r"waiver", l, re.I):
            errs.append("waivers are never produced unattended (decision-11)")
        if any(fnmatch.fnmatch(t.group(1), pat) for pat in PROTECTED + ("docs/agent/tron/*",)) and tier.group(1) != "3":
            errs.append(f"protected target {t.group(1)} must be tier 3")
    return errs


def retro_for_run(root, tron, journal, jpath, force=False):
    """One retro analyst session over a finished run; writes docs/agent/tron/RETRO-<run>.md. Returns the path or raises TronError."""
    rid = journal["run_id"]
    out = root / JOURNAL_DIR / f"RETRO-{rid}.md"
    if out.exists() and not force:
        raise TronError(f"{out.relative_to(root)} exists; pass --force to overwrite")
    brief = retro_brief(root, tron, journal)
    prompt = (f"You are the retro analyst of an unattended Tron mode run. Read .claude/agents/retro-analyst.md and follow it exactly. "
              f"Your brief is {brief.relative_to(root)}. Change no file in the project; answer with the retro in your final message.")
    before = (tree_state(root), tree_dirty(root))
    entry = run_session(root, tron, "retro", "retro", rid, journal["milestone"], prompt)
    text = entry.pop("_out", "") or ""
    journal["sessions"].append(entry)
    write_journal(jpath, journal)
    if (tree_state(root), tree_dirty(root)) != before:
        raise TronError("the retro session changed HEAD, branches or files; nothing written")
    if entry.get("exit_code"):
        raise TronError(f"retro session failed (exit {entry.get('exit_code')}); tail: {text[-200:]!r}")
    m = re.search(r"^# ", text, re.M)
    body = re.sub(r"\n?```\s*$", "", text[m.start() if m else 0:].rstrip())
    errs = validate_retro(body, journal)
    if errs:
        raise TronError("retro file rejected: " + "; ".join(errs[:4]))
    out.write_text(body + "\n")
    journal["retro"] = str(out.relative_to(root))
    write_journal(jpath, journal)
    return out


def cmd_retro(args):
    """Unattended retro analysis (doc-12 11.3 A2-5, analysis part): a fresh analyst session over one run's data."""
    root = pathlib.Path(args.root).resolve()
    tron = load_config(root, args.config)
    d = root / JOURNAL_DIR
    if args.run_id:
        jpath = d / f"run-{args.run_id}.json"
    else:
        runs = sorted(d.glob("run-*.json")) if d.is_dir() else []
        jpath = runs[-1] if runs else None
    if not jpath or not jpath.is_file():
        raise TronError("no run journal found (pass --run <id>)")
    journal = json.loads(jpath.read_text())
    if not journal.get("ended"):
        raise TronError(f"run {journal['run_id']} has not ended")
    if not tron.get("retro_cmd"):
        print("warning: tron.retro_cmd is unset; the analyst falls back to worker_cmd, which may edit files", file=sys.stderr)
    out = root / JOURNAL_DIR / f"RETRO-{journal['run_id']}.md"
    if not args.apply or args.force or not out.is_file():
        out = retro_for_run(root, tron, journal, jpath, force=args.force)
        print(f"retro written: {out.relative_to(root)}")
    elif not journal.get("retro"):
        errs = validate_retro(out.read_text(), journal)
        if errs:
            raise TronError(f"{out.relative_to(root)} is invalid: " + "; ".join(errs[:4]))
        journal["retro"] = str(out.relative_to(root)); write_journal(jpath, journal)
    if missed(journal):  # evaluator calibration: misses the user recorded get their example verdicts drafted (tier 3)
        refuse_while_locked(root)
        ids = calibrate_run(root, tron, journal, jpath)
        print(f"calibration drafted: {', '.join(ids)}" if ids else "calibration: every missed defect has an example")
    if args.apply:
        lock = root / JOURNAL_DIR / "LOCK"  # never next to an active run on the same checkout
        try:
            pid = int(lock.read_text().strip()) if lock.is_file() else 0
        except ValueError:
            pid = 0
        if pid and pid_alive(pid):
            raise TronError(f"a run or another --apply is active (pid {pid}, {lock.relative_to(root)})")
        lock.write_text(str(os.getpid()))
        try:
            apply_retro(root, tron, journal, jpath)
        finally:
            try:
                lock.unlink()
            except OSError:
                pass
            try:
                (root / JOURNAL_DIR / f"REPORT-{journal['run_id']}.md").write_text(build_report(root, journal, tron))
            except (OSError, TronError, KeyError, ValueError) as e:
                print(f"warning: report not written: {e}", file=sys.stderr)
        for r in journal.get("retro_changes", []):
            print(f"{r['id']} tier {r['tier']} {r['target']}: {r['result']}")
        for e in journal.get("experiment_checks", []):
            print(f"experiment {e['run']} {e['id']}: {e['result']}")
    return 0


# ---- unattended retro: changes applied in tiers (R-TRON "Retro changes") ----

PITFALLS, EXPERIMENTS, PITFALLS_CAP = "docs/agent/PITFALLS.md", "docs/agent/EXPERIMENTS.md", 30
TIER2_GLOBS = ("AGENTS.md", "CLAUDE.md", "docs/agent/*.md", ".claude/skills/*.md", ".agents/skills/*.md")
NOT_TIER2 = ("docs/agent/tron/*", EXPERIMENTS, "backlog/*")
TEST_NAME = re.compile(r"^(test_\w+\.py|\w+_test\.\w+|[\w.-]+\.(test|spec)\.\w+|Test\w+\.\w+|\w+Tests?\.\w+)$")
EXP_TAG = re.compile(r"<!-- tron-exp run=(\S+) p=(\S+) commits=(\w+)\.\.(\w+) metric=(\w+) baseline=(\S+) -->")
APPLY_PROMPT = ("You apply one change proposal from the unattended retro of Tron mode run {rid} (STEM_TRON=1; read R-TRON first, "
                "'Retro changes'). Proposal {pid}: target {target}, tier {tier}, expected effect on {metric}: {effect}. "
                "Make the smallest change that implements it ({scope}). Change no other file, no task and no protected file. "
                "Run the verification command, then commit once with a message that starts with 'retro: {rid} {pid}'. "
                "Nobody answers questions: if the proposal cannot be done safely, change nothing and say why.")
TIER_SCOPE = {1: f"tier 1: add lines to {PITFALLS} (at most {PITFALLS_CAP} project entries) or add a new regression test file named like test_x.py, x_test.go or x.test.ts; change no existing line",
              2: "tier 2: project rule or skill text only"}


def is_test_path(path, tron):
    """A regression test file by its name (or tron.test_globs); helpers, fixtures and conftest files in test folders are not."""
    return bool(TEST_NAME.match(path.rsplit("/", 1)[-1])) or any(fnmatch.fnmatchcase(path, g) for g in tron.get("test_globs", []))


def tier_of_path(root, tron, path):
    """3 for a protected path, 1 for PITFALLS.md or a test file, 2 for other rule or skill text, None for anything else (no retro change may touch it)."""
    if any(fnmatch.fnmatchcase(path, pat) for pat in protected_paths(root, tron)):
        return 3
    if path == PITFALLS or is_test_path(path, tron):
        return 1
    if any(fnmatch.fnmatchcase(path, g) for g in TIER2_GLOBS) and not any(fnmatch.fnmatchcase(path, g) for g in NOT_TIER2):
        return 2
    return None


def pitfall_entries(text):
    """Project entries of PITFALLS.md: non-empty lines after the '<!-- Project entries: -->' marker (the whole file without it)."""
    _, sep, rest = text.partition("<!-- Project entries: -->")
    return [l for l in (rest if sep else text).splitlines() if l.strip()]


def retro_proposals(text):
    """Proposals of a validated retro file: [{id, target, tier, metric, effect}] in file order."""
    m = re.search(r"^## Proposals\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    out = []
    for l in (m.group(1).splitlines() if m else []):
        t, tier, met, eff = (re.search(r"\btarget:\s*([^|\s]+)", l), re.search(r"\btier:\s*(\d)", l),
                             re.search(r"\bmetric:\s*(\w+)", l), re.search(r"\beffect:\s*(.+)$", l))
        if t and tier and met and eff:
            pid = re.match(r"\s*[-*]\s*(P\d+)\b", l)
            out.append({"id": pid.group(1) if pid else f"P{len(out) + 1}", "target": t.group(1), "tier": int(tier.group(1)),
                        "metric": met.group(1), "effect": eff.group(1).replace("|", "/").strip()[:200]})
    return out


def retro_gate(root, tron, base, tier, branch, refs0):
    """Checks after an applier session: run branch and other refs untouched, clean tree, only 'retro:' commits,
    no protected path, every path inside the tier, tier 1 only adds lines and keeps the PITFALLS cap, verification passes."""
    fails = []
    try:
        cur = git_ok(root, "branch", "--show-current").strip()
        if cur != branch:
            return {"passed": False, "failures": [{"check": "branch", "reason": f"session left the run branch (now on '{cur or 'detached HEAD'}')"}]}
        if subprocess.run(["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=root).returncode:
            return {"passed": False, "failures": [{"check": "branch", "reason": "history rewritten: the commit before the session is no longer an ancestor of HEAD"}]}
        if {k: v for k, v in branch_refs(root).items() if k != branch} != {k: v for k, v in refs0.items() if k != branch}:
            return {"passed": False, "failures": [{"check": "refs", "reason": "other branches changed during the session"}]}
        dirty = tree_dirty(root)
        if dirty:
            fails.append({"check": "tree", "reason": f"working tree not clean ({len(dirty)} entries)", "detail": "; ".join(dirty[:5])})
        subjects = [x for x in git_ok(root, "log", "--format=%s", f"{base}..HEAD").splitlines() if x.strip()]
        paths = changed_paths(root, base)
        if not subjects and not paths:
            return {"passed": False, "no_change": True, "failures": [{"check": "change", "reason": "the session changed nothing"}]}
        if not subjects:
            fails.append({"check": "commit", "reason": "no commit"})
        bad = [x for x in subjects if not x.startswith("retro:")]
        if bad:
            fails.append({"check": "commit", "reason": f"commit message without the prefix 'retro:': '{bad[0][:80]}'"})
        tiers = {f: tier_of_path(root, tron, f) for f in paths}
        hit = [f for f, t in tiers.items() if t == 3]
        if hit:
            fails.append({"check": "protected", "reason": "protected files changed: " + ", ".join(hit)})
        out = [f for f, t in tiers.items() if t is None or (t != 3 and t > tier)]
        if out:
            fails.append({"check": "tier", "reason": f"files outside tier {tier}: " + ", ".join(out)})
        t1 = [f for f, t in tiers.items() if t == 1]
        if t1:  # tier 1 rules hold for these paths in every tier: PITFALLS only grows, tests only arrive as new files
            status = dict(reversed(l.split("\t", 1)) for l in git_ok(root, "diff", "--name-status", "--no-renames", base, "--", *t1).splitlines() if "\t" in l)
            old_tests = [f for f in t1 if f != PITFALLS and f in status and status[f] != "A"]
            if old_tests:
                fails.append({"check": "tier", "reason": "existing test files changed (tier 1 only adds new test files): " + ", ".join(old_tests)})
            removed = [l for l in git_ok(root, "diff", "-U0", "--no-renames", base, "--", *t1).splitlines() if l.startswith("-") and not l.startswith("---")]
            if removed or PITFALLS in status and status[PITFALLS] not in ("M", "A"):
                fails.append({"check": "tier", "reason": f"tier 1 paths only gain lines; {len(removed)} line(s) removed or changed"})
            odd = [l for l in git_ok(root, "diff", "--numstat", "--summary", "--no-renames", base, "--", *t1).splitlines() if l.startswith("-\t") or "mode change" in l]
            if odd:
                fails.append({"check": "tier", "reason": "binary or mode changes in tier 1 paths: " + "; ".join(odd)[:200]})
        if PITFALLS in paths and (root / PITFALLS).is_file() and len(pitfall_entries((root / PITFALLS).read_text())) > PITFALLS_CAP:
            fails.append({"check": "cap", "reason": f"{PITFALLS} has more than {PITFALLS_CAP} project entries"})
        if not fails:
            code, tail = verify(root, tron)
            if code:
                fails.append({"check": "verify", "reason": f"verification exited {code}", "detail": tail})
    except TronError as e:
        fails.append({"check": "git", "reason": str(e)})
    return {"passed": not fails, "failures": fails}


def revert_retro(root, base, msg):
    """Undo one applier session on the run branch: loose files go to a named stash, committed changes are undone by one
    'retro: revert' commit (history keeps them). Returns the revert commit or None."""
    unhide(root)
    if tree_dirty(root):
        git_ok(root, "stash", "push", "-u", "-q", "-m", msg[:100], "--", ".", *EXCLUDE)
    at_base = set(git_ok(root, "ls-tree", "-r", "--name-only", base).splitlines())
    for f in changed_paths(root, base):
        if f in at_base:
            git_ok(root, "checkout", base, "--", f)
        else:
            git_ok(root, "rm", "-rf", "-q", "--ignore-unmatch", "--", f)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode:
        r = sh(["git", "commit", "-q", "-m", msg], root)
        if r.returncode:
            raise TronError(f"revert commit refused ({(r.stderr or r.stdout).strip()[:200]}); the restored files are staged on the run branch")
        return head(root)
    return None


def record_experiment(root, journal, prop, base, commit, baseline):
    """Tier 2 bookkeeping: one row in EXPERIMENTS.md with metric, baseline and the change commits, committed by the runner as
    'retro: experiment ...'. Idempotent: a row that is already there is only committed."""
    p, rid = root / EXPERIMENTS, journal["run_id"]
    if p.is_file() and f"<!-- tron-exp run={rid} p={prop['id']} " in p.read_text():
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", EXPERIMENTS], cwd=root).returncode:
            git_ok(root, "add", "--", EXPERIMENTS)
            git_ok(root, "commit", "-q", "-m", f"retro: experiment {rid} {prop['id']} ({prop['metric']} baseline {baseline})")
        return
    text = p.read_text() if p.is_file() else ("# Experiments on cost-carrying rules\n\n| Rule / change | Hypothesis | Metric (per accepted task) and threshold "
                                              "| Baseline | Check by | Confounders to note | Result | Grade |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n")
    row = (f"| Tron retro {rid} {prop['id']}: {prop['target']} (commit {commit[:10]}) <!-- tron-exp run={rid} p={prop['id']} commits={base}..{commit} "
           f"metric={prop['metric']} baseline={baseline} --> | {prop['effect']} | {prop['metric']}, lower is better: not worse than the baseline, "
           f"else the runner reverts the change | {baseline} (run {rid}) | next Tron run's retro | other changes between the runs, task mix | open | G1 (one run) |")
    marker = "<!-- New entries above this line. -->"
    text = text.replace(marker, row + "\n" + marker, 1) if marker in text else text.rstrip("\n") + "\n" + row + "\n"
    p.write_text(text)
    git_ok(root, "add", "--", EXPERIMENTS)
    git_ok(root, "commit", "-q", "-m", f"retro: experiment {rid} {prop['id']} ({prop['metric']} baseline {baseline})")


def check_experiments(root, tron, journal, jpath):
    """Open tier 2 experiments of earlier runs: compare the metric with this run's value; worse reverts the change commit, with a record in EXPERIMENTS.md and the journal."""
    p, rid = root / EXPERIMENTS, journal["run_id"]
    if not p.is_file():
        return
    metrics = run_metrics(journal)
    checks = journal.setdefault("experiment_checks", [])
    for line in p.read_text().splitlines():
        m = EXP_TAG.search(line)
        if not m or m.group(1) == rid or not re.search(r"\| open \|[^|]*\|\s*$", line):
            continue
        run, pid, c0, commit, metric, base = m.groups()
        rec = {"run": run, "id": pid, "commit": commit, "metric": metric, "baseline": base, "current": metrics.get(metric), "at_run": rid}
        try:
            b, c = float(base), metrics.get(metric)
        except ValueError:
            b, c = None, None
        stays = ("not measurable (stays open)" if b is None or c is None else
                 "commit not on this branch (stays open)" if subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=root, capture_output=True).returncode
                 else None)
        if stays:
            if not any(x["run"] == run and x["id"] == pid and x.get("result") == stays for x in checks):
                checks.append(dict(rec, result=stays)); write_journal(jpath, journal)
            continue
        rec["result"] = "checking"  # a runner killed from here on leaves this mark; the next --apply stashes what it left and checks again
        checks.append(rec); write_journal(jpath, journal)
        # the change commits minus runner files (a session may have committed the journal with 'git add -A'); git apply is all or nothing
        patch = git_ok(root, "diff", "--binary", c0, commit, "--", ".", *EXCLUDE)
        apply = lambda *a: subprocess.run(["git", "apply", "--index", *a], cwd=root, input=patch, capture_output=True, text=True).returncode
        if c <= b:
            result = f"kept: {metric} {base} -> {c} (run {rid})"
        elif not patch.strip():
            result = f"worse ({metric} {base} -> {c}, run {rid}) but the change has no file changes left to revert: needs the user"
        elif apply("-R"):
            result = f"worse ({metric} {base} -> {c}, run {rid}) but the revert conflicts: needs the user"
        elif verify(root, tron)[0]:
            if apply():
                raise TronError(f"experiment {run} {pid}: undoing the revert failed; the run branch has staged changes")
            result = f"worse ({metric} {base} -> {c}, run {rid}) but the revert breaks verification: needs the user"
        else:
            result = f"reverted: {metric} {base} -> {c} (run {rid})"
        rec["result"] = result
        cur = p.read_text()
        p.write_text(cur.replace(line, re.sub(r"\| open \|([^|]*)\|\s*$", lambda x: f"| {result} |{x.group(1)}|", line), 1))
        git_ok(root, "add", "--", EXPERIMENTS)
        git_ok(root, "commit", "-q", "-m", f"retro: {'revert' if result.startswith('reverted') else 'check'} experiment {run} {pid} "
               f"({metric} {base} -> {c})")
        rec["check_commit"] = head(root)
        write_journal(jpath, journal)


def apply_one(root, tron, journal, jpath, prop, rec):
    """Settle one tier 1 or 2 proposal whose applier session ran (or was interrupted): keep it when the gate passes, else revert it."""
    rid = journal["run_id"]
    g = retro_gate(root, tron, rec["base"], prop["tier"], journal["branch"], rec["refs"])
    rec["gate"] = g["failures"]
    if g["passed"]:
        rec["result"], rec["commit"] = "applied", head(root)
        write_journal(jpath, journal)  # before the experiment row: a resume then records the row instead of judging it as a protected change
        if prop["tier"] == 2:
            record_experiment(root, journal, prop, rec["base"], rec["commit"], rec["baseline"])
            rec["experiment"] = EXPERIMENTS
    elif g.get("no_change"):
        rec["result"] = "stopped: the session hit an API error; a later --apply retries" if rec.get("api_error") else "skipped: the session changed nothing"
    elif any(f["check"] in ("branch", "refs") for f in g["failures"]):
        rec["result"] = "stopped: " + g["failures"][0]["reason"]
        write_journal(jpath, journal)
        raise TronError(f"retro change {prop['id']}: {g['failures'][0]['reason']}; the run branch needs the user")
    else:
        why = "; ".join(f["reason"] for f in g["failures"])[:300]
        rec["result"], rec["reason"] = "reverted", why
        rec["revert_commit"] = revert_retro(root, rec["base"], f"retro: revert {rid} {prop['id']} ({why[:120]})")
    write_journal(jpath, journal)


def apply_retro(root, tron, journal, jpath):
    """Run end, retro part 2: check open tier 2 experiments of earlier runs, then apply the tier 1 and 2 proposals of this run's retro,
    each in its own applier session behind retro_gate; tier 3 stays in the report. Resumable: settled proposals are skipped."""
    branch = journal["branch"]
    cur = git_ok(root, "branch", "--show-current").strip()
    if cur != branch:
        raise TronError(f"retro changes need the run branch {branch} checked out (now '{cur or 'detached HEAD'}')")
    recs = {r["id"]: r for r in journal.setdefault("retro_changes", [])}
    pending = [r for r in recs.values() if r.get("result") == "started"]
    unrecorded = [r for r in recs.values() if r.get("result") == "applied" and r["tier"] == 2 and not r.get("experiment")]
    checking = [x for x in journal.get("experiment_checks", []) if x.get("result") == "checking"]
    if checking:  # a killed experiment check: keep what it left in a stash, then check again from a clean tree
        unhide(root)
        if tree_dirty(root):
            git_ok(root, "stash", "push", "-u", "-q", "-m", f"tron {journal['run_id']} interrupted experiment check", "--", ".", *EXCLUDE)
        journal["experiment_checks"] = [x for x in journal["experiment_checks"] if x.get("result") != "checking"]
        write_journal(jpath, journal)
    if tree_dirty(root) and not pending and not unrecorded:
        raise TronError("working tree is not clean; retro changes need a clean run branch")
    for r in pending:  # an applier session was interrupted: judge what it left
        apply_one(root, tron, journal, jpath, r["proposal"], r)
    for r in unrecorded:  # killed between the applied mark and the experiment row
        record_experiment(root, journal, r["proposal"], r["base"], r["commit"], r["baseline"])
        r["experiment"] = EXPERIMENTS
        write_journal(jpath, journal)
    check_experiments(root, tron, journal, jpath)
    if not journal.get("retro"):
        return
    text = (root / journal["retro"]).read_text()
    errs = validate_retro(text, journal)  # the file is runner output outside the gate: check it again before acting on it
    if errs:
        raise TronError(f"{journal['retro']} is invalid now: " + "; ".join(errs[:3]))
    metrics = journal.setdefault("retro_baseline", run_metrics(journal))  # one baseline per run, taken before any applier session
    for prop in retro_proposals(text):
        r = recs.get(prop["id"])
        if r and not str(r.get("result", "")).startswith("stopped"):
            continue
        base_rec = {"id": prop["id"], "tier": prop["tier"], "target": prop["target"], "metric": prop["metric"], "proposal": prop}
        t = tier_of_path(root, tron, prop["target"])
        if prop["tier"] == 3 or t == 3:
            rec = dict(base_rec, result="proposed (tier 3: for the user)")
        elif t is None or t > prop["tier"]:
            rec = dict(base_rec, result=f"skipped: target {prop['target']} is not a tier {prop['tier']} path")
        elif prop["tier"] == 2 and metrics.get(prop["metric"]) is None:
            rec = dict(base_rec, result=f"skipped: no baseline value for {prop['metric']} in this run")
        else:
            stop = ("stop file docs/agent/tron/STOP" if (root / STOP_FILE).is_file() else limit_hit(journal, tron, None))
            if stop:
                rec = dict(base_rec, result=f"stopped: {stop}")
            else:
                rec = dict(base_rec, result="started", base=head(root), refs=branch_refs(root), baseline=metrics.get(prop["metric"]))
        journal["retro_changes"] = [x for x in journal["retro_changes"] if x["id"] != prop["id"]] + [rec]
        recs[prop["id"]] = rec
        write_journal(jpath, journal)
        if rec["result"] != "started":
            continue
        prompt = APPLY_PROMPT.format(rid=journal["run_id"], pid=prop["id"], target=prop["target"], tier=prop["tier"],
                                     metric=prop["metric"], effect=prop["effect"], scope=TIER_SCOPE[prop["tier"]])
        entry = run_session(root, tron, "applier", f"retro-{prop['id']}", journal["run_id"], journal["milestone"], prompt)
        journal["sessions"].append(entry)
        rec["session"] = entry.get("session_id")
        rec["api_error"] = bool(entry.get("api_error"))
        apply_one(root, tron, journal, jpath, prop, rec)


def retro_changes_report(journal):
    rows, exps = journal.get("retro_changes", []), journal.get("experiment_checks", [])
    if not rows and not exps and not journal.get("retro_apply_error"):
        return []
    out = ["## Unattended retro changes (R-TRON 'Retro changes')", ""]
    for r in rows:
        extra = (f", commit `{r['commit'][:10]}`" if r.get("commit") else "") + (f", reason: {r['reason']}" if r.get("reason") else "")
        extra += f", recorded in {r['experiment']} (metric {r['metric']}, baseline {r.get('baseline')})" if r.get("experiment") else ""
        out.append(f"- {r['id']} tier {r['tier']} `{r['target']}`: {r['result']}{extra}")
    out += [f"- Experiment {e['run']} {e['id']} ({e['metric']} baseline {e['baseline']}, now {e['current']}): {e['result']}" for e in exps]
    if journal.get("retro_apply_error"):
        out.append(f"- Retro changes stopped: {journal['retro_apply_error']}")
    tier3 = [r for r in rows if r["result"].startswith("proposed")]
    if tier3:
        out.append("- Tier 3 proposals touch protected parts and are yours to decide: " + ", ".join(f"{r['id']} ({r['target']})" for r in tier3))
    return out + [""]


# ---- evaluator calibration from defects the user finds (R-TRON "Evaluator calibration") ----

EVALUATOR_FILE = ".claude/agents/evaluator.md"
CALIBRATE_PROMPT = ("You are the retro analyst of an unattended Tron mode run, in calibration mode. Read .claude/agents/retro-analyst.md "
                    "('Calibration mode') and follow it exactly. Your brief is {brief}. Change no file in the project; answer with the "
                    "calibration in your final message.")


def evaluator_status(root, run_id, task_id):
    """What the evaluator said about a task in a run, from the verdict files: (passed|failed|not evaluated, file). The task's own last
    verdict wins; without one the last milestone verdict counts."""
    d = root / JOURNAL_DIR
    for target in (task_id, "milestone"):
        files = sorted(d.glob(f"verdict-{run_id}-{target}-*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem.rsplit("-", 1)[-1]) or 0))
        for vf in reversed(files):
            try:
                v = json.loads(vf.read_text()).get("verdict")
            except (OSError, ValueError):
                continue
            if v not in ("pass", "fail"):
                continue
            if v == "fail" and target == "milestone":  # a failed milestone verdict caught only the tasks its findings name
                fs = json.loads(vf.read_text()).get("findings") or []
                named = any(re.search(rf"\b{re.escape(task_id)}\b", json.dumps(f)) for f in fs if isinstance(f, dict))
                return ("failed" if named else "passed"), str(vf.relative_to(root))
            return ("passed" if v == "pass" else "failed"), str(vf.relative_to(root))
    return "not evaluated", None


def missed(journal):
    return [x for x in journal.get("user_defects", []) if x.get("evaluator") == "passed"]


def load_journal(root, run_id):
    d = root / JOURNAL_DIR
    if run_id:
        jpath = d / f"run-{run_id}.json"
    else:
        runs = sorted(d.glob("run-*.json"), key=lambda p: json.loads(p.read_text()).get("started", "")) if d.is_dir() else []
        jpath = runs[-1] if runs else None
    if not jpath or not jpath.is_file():
        raise TronError("no run journal found (pass --run <id>)")
    return jpath, json.loads(jpath.read_text())


def write_report(root, journal, tron):
    try:
        (root / JOURNAL_DIR / f"REPORT-{journal['run_id']}.md").write_text(build_report(root, journal, tron))
    except (OSError, TronError, KeyError, ValueError) as e:
        print(f"warning: report not written: {e}", file=sys.stderr)


def record_defect(root, journal, jpath, task_id, text):
    """One defect the user found after the run; idempotent for the same task and text. Returns the record."""
    task_id, text = task_id.strip().upper(), " ".join(text.split())
    if task_id not in journal.get("tasks", {}):
        raise TronError(f"{task_id} is not a task of run {journal['run_id']} ({', '.join(journal.get('tasks', {})) or 'no tasks'})")
    if not text:
        raise TronError("the defect needs a description (--text)")
    defects = journal.setdefault("user_defects", [])
    for x in defects:
        if x["task"] == task_id and x["text"] == text:
            return x
    status, vfile = evaluator_status(root, journal["run_id"], task_id)
    rec = {"id": f"D{len(defects) + 1}", "task": task_id, "text": text, "at": now(), "evaluator": status, "verdict": vfile}
    defects.append(rec)
    journal["defects_reviewed"] = now()  # the user answered the defects question
    write_journal(jpath, journal)
    return rec


def calibration_brief(root, journal, todo):
    rid = journal["run_id"]
    files = task_files(root)
    parts = [f"# Calibration brief: run {rid} (milestone {journal['milestone']})", "",
             "The user found these defects after the run; the evaluator had passed each task. Draft one example verdict per defect.", ""]
    for x in todo:
        parts += [f"## {x['id']} ({x['task']})", f"Defect found by the user: {x['text']}", f"Evaluator verdict that passed it: {x['verdict']}"]
        if x["task"] in files:
            _, acs, _ = parse_task(files[x["task"]].read_text())
            parts += ["Acceptance criteria:"] + [f"- AC#{n}: {s}" for _, n, s in acs]
        parts.append("")
    ev = read_rel(root, EVALUATOR_FILE)
    m = re.search(r"^## Calibrated examples\s*$.*", ev, re.M | re.S)
    parts += ["## Calibrated examples already in the evaluator file (do not repeat them)", m.group(0) if m else "(none)"]
    path = root / JOURNAL_DIR / f"brief-{rid}-calibration.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n")
    return path


def calibration_sections(text):
    """{defect id: (task, body)} of a calibration file: '### D<n> (TASK-m)' headings, body up to the next heading."""
    out = {}
    for m in re.finditer(r"^### (D\d+) \((TASK-\d+)\)\s*$(.*?)(?=^#{1,3} |\Z)", text, re.M | re.S):
        out[m.group(1)] = (m.group(2), m.group(3).strip())
    return out


def example_parts(body):
    """(paragraph, verdict json) of one drafted example, or (None, reason): one '**Example...**' paragraph of plain text (no fence,
    no heading, at most 1500 characters) and one json verdict that fails with a finding, re-serialized with the known keys only."""
    if body.count("```") % 2:
        return None, "unbalanced code fence"
    blocks = re.findall(r"```[^\n]*\n.*?```", body, re.S)
    prose = [x.strip() for x in re.split(r"\n\s*\n", re.sub(r"```[^\n]*\n.*?```", "\n\n", body, flags=re.S)) if x.strip()]
    prose = [x for x in prose if not x.startswith("Defect found by the user:")]
    if len(prose) != 1 or len(blocks) != 1:
        return None, "needs exactly one paragraph and one json block"
    para = " ".join(prose[0].split())
    if not re.match(r"\*\*Example[^*]*\*\*\s*\S", para) or len(para) > 1500 or re.search(r"(^|\s)#|`{3}", para):
        return None, "the paragraph must start with '**Example: <title>.**', hold no heading or fence and stay under 1500 characters"
    v = parse_verdict(blocks[0])
    if not v or v["verdict"] != "fail" or not v["findings"]:
        return None, "needs a json verdict block that fails with at least one finding"
    title = re.match(r"\*\*Example\W*(?:\d+\W*)?([^*]*)\*\*\s*(.*)", para)
    para = f"**Example: {title.group(1).strip()}** {title.group(2)}"
    keep = {k: v[k] for k in ("verdict", "checked", "findings", "assumption_flags")}
    return para, json.dumps(keep)


def validate_calibration(text, todo):
    """Why a calibration answer is invalid (list; empty when fine): one section per defect with its task, a scenario paragraph
    and a parseable example verdict that fails with at least one finding."""
    errs, secs = [], calibration_sections(text)
    for x in todo:
        s = secs.get(x["id"])
        if not s:
            errs.append(f"no section '### {x['id']} ({x['task']})'"); continue
        if s[0] != x["task"]:
            errs.append(f"{x['id']} names {s[0]}, expected {x['task']}"); continue
        para, why = example_parts(s[1])
        if para is None:
            errs.append(f"{x['id']}: {why}")
    extra = sorted(set(secs) - {x["id"] for x in todo})
    if extra:
        errs.append("sections for defects not asked for: " + ", ".join(extra))
    return errs


def calibrate_run(root, tron, journal, jpath):
    """Draft example verdicts for missed defects that have none yet (one read-only analyst session); each becomes a tier 3 proposal
    for the evaluator file. Returns the drafted defect ids. Resumable: drafted defects are skipped."""
    rid = journal["run_id"]
    out = root / JOURNAL_DIR / f"CALIBRATION-{rid}.md"
    have = calibration_sections(out.read_text()) if out.is_file() else {}
    todo = [x for x in missed(journal) if x["id"] not in have]
    rows = {r["id"]: r for r in journal.get("retro_changes", [])}
    for x in missed(journal):  # resume: a draft written before the journal row
        if x["id"] in have and f"C-{x['id']}" not in rows:
            add_calibration_row(journal, x, out.relative_to(root))
    write_journal(jpath, journal)
    if not todo:
        return []
    brief = calibration_brief(root, journal, todo)
    before = (tree_state(root), tree_dirty(root))
    entry = run_session(root, tron, "retro", "calibration", rid, journal["milestone"], CALIBRATE_PROMPT.format(brief=brief.relative_to(root)))
    text = entry.pop("_out", "") or ""
    journal["sessions"].append(entry)
    write_journal(jpath, journal)
    if (tree_state(root), tree_dirty(root)) != before:
        raise TronError("the calibration session changed HEAD, branches or files; nothing written")
    if entry.get("exit_code"):
        raise TronError(f"calibration session failed (exit {entry.get('exit_code')}); tail: {text[-200:]!r}")
    errs = validate_calibration(text, todo)
    if errs:
        raise TronError("calibration rejected: " + "; ".join(errs[:4]))
    secs = calibration_sections(text)
    parts = {x["id"]: example_parts(secs[x["id"]][1]) for x in todo}  # stored in a fixed structure, never as raw analyst text
    body = "".join(f"\n### {x['id']} ({x['task']})\nDefect found by the user: {x['text']}\n\n{parts[x['id']][0]}\n\n```json\n{parts[x['id']][1]}\n```\n" for x in todo)
    head_ = f"# Calibration: {rid}\nProposed example verdicts for {EVALUATOR_FILE} (tier 3: applied only on the user's yes).\n"
    out.write_text((out.read_text().rstrip() + "\n" if out.is_file() else head_) + body)
    for x in todo:
        add_calibration_row(journal, x, out.relative_to(root))
    write_journal(jpath, journal)
    return [x["id"] for x in todo]


def add_calibration_row(journal, defect, rel):
    rows = journal.setdefault("retro_changes", [])
    if not any(r["id"] == f"C-{defect['id']}" for r in rows):
        rows.append({"id": f"C-{defect['id']}", "tier": 3, "target": EVALUATOR_FILE, "metric": "evaluator_misses",
                     "result": "proposed (tier 3: for the user)", "reason": f"example verdict for {defect['id']} ({defect['task']}) in {rel}"})


def accept_calibration(root, journal, jpath, did, accept):
    """The user's answer to one drafted example: yes appends it to the evaluator file as the next numbered example."""
    if os.environ.get("STEM_TRON") == "1":
        raise TronError("an unattended session never changes the evaluator file; the user decides")
    rows = {r["id"]: r for r in journal.get("retro_changes", [])}
    row = rows.get(f"C-{did}")
    if not row:
        raise TronError(f"no drafted example for {did} (run: tron.py calibrate --run {journal['run_id']})")
    if not (row["result"].startswith("proposed") or row["result"] == "applying"):
        return row
    if accept:
        cal = root / JOURNAL_DIR / f"CALIBRATION-{journal['run_id']}.md"
        sec = calibration_sections(cal.read_text()).get(did) if cal.is_file() else None
        if not sec:
            raise TronError(f"{cal.relative_to(root)} has no section for {did}; draft it again with tron.py calibrate")
        para, js = example_parts(sec[1])  # checked again: the file may have been edited since it was drafted
        if para is None:
            raise TronError(f"the drafted example {did} is invalid now ({js}); nothing applied")
        ev = root / EVALUATOR_FILE
        if not ev.is_file():
            raise TronError(f"{EVALUATOR_FILE} not found")
        text = ev.read_text()
        tail = para.split("** ", 1)[1]
        if row["result"] == "applying" and tail in text:  # killed after writing the evaluator file: do not add it twice
            row["result"] = f"applied by the user {now()[:10]}"
            write_journal(jpath, journal)
            return row
        row["result"] = "applying"
        write_journal(jpath, journal)
        n = max([int(x) for x in re.findall(r"^\*\*Example (\d+)", text, re.M)] or [0]) + 1
        body = para.replace("**Example: ", f"**Example {n}: ", 1) + f"\n\n```json\n{js}\n```"
        m = re.search(r"^## Calibrated examples\s*$.*?(?=^## |\Z)", text, re.M | re.S)
        cut = m.end() if m else len(text)  # after the last example, before any later section
        ev.write_text(text[:cut].rstrip() + "\n\n" + body + "\n" + ("\n" + text[cut:] if text[cut:].strip() else ""))
        row["result"] = f"applied by the user {now()[:10]} (example {n})"
    else:
        row["result"] = f"rejected by the user {now()[:10]}"
    write_journal(jpath, journal)
    return row


def calibration_report(journal):
    ds = journal.get("user_defects", [])
    if not ds:
        return []
    rows = {r["id"]: r for r in journal.get("retro_changes", [])}
    out = ["## Defects you found after the run", ""]
    for x in ds:
        r = rows.get(f"C-{x['id']}")
        out.append(f"- {x['id']} {x['task']}: {x['text']} (evaluator: {x['evaluator']}" + (f", {x['verdict']}" if x.get("verdict") else "") + ")"
                   + (f"; example verdict: {r['result']}" if r else ("; example verdict: not drafted yet (`tron.py calibrate`)" if x["evaluator"] == "passed" else "")))
    return out + [""]


def refuse_while_locked(root):
    lock = root / JOURNAL_DIR / "LOCK"
    try:
        pid = int(lock.read_text().strip()) if lock.is_file() else 0
    except ValueError:
        pid = 0
    if pid and pid_alive(pid):
        raise TronError(f"a run or --apply is active (pid {pid}, {lock.relative_to(root)}); try again when it has ended")


def cmd_defect(args):
    """Record a defect the user found after a run (the tron skill asks for them when reading the report); --none records 'none found'."""
    root = pathlib.Path(args.root).resolve()
    refuse_while_locked(root)
    jpath, journal = load_journal(root, args.run_id)
    if args.none:
        journal["defects_reviewed"] = now(); write_journal(jpath, journal)
        try:
            write_report(root, journal, load_config(root, args.config))
        except TronError:
            write_report(root, journal, {})
        print(f"run {journal['run_id']}: defects reviewed, {len(journal.get('user_defects', []))} recorded")
        return 0
    if not args.task or not args.text:
        raise TronError("pass --task and --text, or --none when you found no (further) defect")
    rec = record_defect(root, journal, jpath, args.task, args.text)
    try:
        tron = load_config(root, args.config)
    except TronError:
        tron = {}
    write_report(root, journal, tron)
    print(f"{rec['id']} {rec['task']}: evaluator {rec['evaluator']}" + (" (a miss: draft an example with tron.py calibrate)" if rec["evaluator"] == "passed" else ""))
    return 0


def cmd_calibrate(args):
    """Draft example verdicts for missed defects (tier 3), or take the user's yes or no on one (--accept/--reject D<n>)."""
    root = pathlib.Path(args.root).resolve()
    refuse_while_locked(root)
    jpath, journal = load_journal(root, args.run_id)
    try:
        tron = load_config(root, args.config)
    except TronError:
        if not (args.accept or args.reject):
            raise
        tron = {}
    try:
        if args.accept or args.reject:
            row = accept_calibration(root, journal, jpath, args.accept or args.reject, bool(args.accept))
            print(f"{row['id']}: {row['result']}")
        else:
            if not tron.get("retro_cmd"):
                print("warning: tron.retro_cmd is unset; the analyst falls back to worker_cmd, which may edit files", file=sys.stderr)
            ids = calibrate_run(root, tron, journal, jpath)
            print(f"drafted: {', '.join(ids)} in docs/agent/tron/CALIBRATION-{journal['run_id']}.md" if ids else "nothing to draft (no missed defect without an example)")
    finally:
        write_report(root, journal, tron)
    return 0


def check_milestone(root, milestone, cfg_path=None):
    """Readiness check (doc-12 3.1): returns (failures, warnings, tron config or None). Deterministic, starts nothing."""
    fails, warns = [], []
    cp = pathlib.Path(cfg_path) if cfg_path else root / "docs/agent/stem-config.json"
    tron = {}
    try:
        tron = json.loads(cp.read_text()).get("tron") or {}
        if not isinstance(tron, dict):
            tron = {}
    except (OSError, ValueError):
        fails.append(f"config missing or unreadable: {cp} (needs key 'tron')")
    def cmdok(c):
        return isinstance(c, list) and bool(c) and all(isinstance(a, str) for a in c)
    if not cmdok(tron.get("worker_cmd")):
        fails.append("tron.worker_cmd is unset (command template as a list of strings)")
    if not cmdok(tron.get("verify_cmd")):
        fails.append("tron.verify_cmd is unset (the verification command via scripts/run.sh, as a list)")
    if not (tron.get("smoke_cmd") or tron.get("preview_cmd")):
        fails.append("no start-and-smoke command for the product (tron.smoke_cmd or tron.preview_cmd)")
    if all(tron.get(k) is None for k in ("max_cost", "max_hours", "max_tasks")):
        fails.append("no limit configured (tron.max_cost, max_hours or max_tasks)")
    for rel in ("docs/agent/DECISION_FRAME.md", "docs/agent/INVARIANTS.md"):
        f = root / rel
        if not f.is_file() or not f.read_text().strip():
            fails.append(f"{rel} is missing or empty")
    scen = tron.get("acceptance_scenario") or f"docs/agent/tron/ACCEPTANCE-{milestone}.md"
    sf = root / scen
    if not sf.is_file() or not sf.read_text().strip():
        fails.append(f"acceptance scenario missing or empty: {scen}")
    files = task_files(root)
    ids = []
    for tid, f in files.items():
        text = f.read_text()
        m = re.search(r"^milestone: *(.+?) *$", text, re.M)
        if m and m.group(1).strip("'\"") == milestone:
            ids.append(tid)
    if not ids:
        fails.append(f"no task found in milestone {milestone}")
    for tid in ids:
        text = files[tid].read_text()
        st, acs, _ = parse_task(text)
        if st and st.lower() == "done":
            continue
        if not acs:
            fails.append(f"{tid}: no acceptance criteria")
        if not any(re.fullmatch(r"size-[sml]", l) for l in labels_of(text)):
            fails.append(f"{tid}: no size label (size-S, size-M or size-L)")
    if tron.get("sweep", True) is not False:
        sw = root / f"docs/agent/tron/SWEEP-{milestone}.md"
        if not sw.is_file():
            fails.append(f"question sweep missing: run 'python3 scripts/tron.py sweep --milestone {milestone}' and answer its questions (or set tron.sweep to false)")
        else:
            n = sweep_open(sw.read_text())
            if n:
                fails.append(f"{sw.relative_to(root)} holds {n} unanswered question(s): answer them with the user, tick them '[x]' and add 'Answer: ...'")
            open_ids = {t for t in ids if (parse_task(files[t].read_text())[0] or "").lower() != "done"}
            for nid, tid, ac, kind, done in sweep_needs_user(sw.read_text()):
                if not done and tid in open_ids:
                    fails.append(f"{tid} AC#{ac} needs {NEEDS_KIND[kind]} "
                                 f"({sw.name} {nid}): split it into a task outside {milestone} before the run, then tick {nid} '[x]' and add 'Resolved: ...'")
    dirty = tree_dirty(root)
    if dirty:
        fails.append(f"working tree is not clean ({len(dirty)} change(s), first: {dirty[0].strip()[:80]})")
    wc = tron.get("worker_cmd") if cmdok(tron.get("worker_cmd")) else []
    sandbox = os.path.exists("/.dockerenv") or os.environ.get("IS_SANDBOX") == "1" or bool(os.environ.get("STEM_SANDBOX"))
    allow = any(a in ("--allowedTools", "--allowed-tools") for a in wc)
    if not (sandbox or allow):
        fails.append("neither a sandbox nor a permission allowlist is detected (run inside the STEM sandbox, or put --allowedTools in tron.worker_cmd)")
    if os.environ.get("CLAUDE_CODE_EFFORT_LEVEL"):
        warns.append("CLAUDE_CODE_EFFORT_LEVEL is set and beats --effort in the role commands")
    if not cmdok(tron.get("doctor_cmd")):
        warns.append("tron.doctor_cmd is missing: no Doctor step; a stalled task goes straight to Blocked (set a read-only command, ideally on a stronger model, R-ROUTING)")
    elif not any(x in ("--allowedTools", "--allowed-tools", "--disallowedTools", "--permission-mode") for x in tron["doctor_cmd"]):
        warns.append("tron.doctor_cmd has no tool restriction (--allowedTools or --permission-mode): read-only is then only enforced by the tree check afterwards")
    if tron.get("retro") == "on" and not cmdok(tron.get("retro_cmd")):
        warns.append("tron.retro is on but tron.retro_cmd is missing: the analyst falls back to worker_cmd, which may edit files")
    prot_lits = sorted(x for x in protected_paths(root, dict(tron, verify_cmd=tron.get("verify_cmd") or [])) if "*" not in x) + ["scripts/hooks/", "scripts/githooks/"]
    for tid in ids:
        named = [x for x in prot_lits if x in files[tid].read_text()]
        if named and parse_task(files[tid].read_text())[0] != "Done":
            warns.append(f"{tid} names protected paths ({', '.join(named[:3])}): a session that changes them stops the run; do it by hand or take the task out")
    if tron.get("retro_apply") == "on" and tron.get("retro") != "on":
        warns.append("tron.retro_apply is on but tron.retro is not: open experiments are checked, no new proposals are applied")
    if not cmdok(tron.get("evaluator_cmd")) and tron.get("evaluator", "milestone") != "off":
        warns.append("tron.evaluator_cmd is missing: the evaluator falls back to worker_cmd, which may edit files")
    return fails, warns, tron


def cmd_check(args):
    root = pathlib.Path(args.root).resolve()
    fails, warns, tron = check_milestone(root, args.milestone, args.config)
    for w in warns:
        print(f"warning: {w}")
    if fails:
        print(f"NOT READY: {len(fails)} problem(s) for {args.milestone}")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"READY: {args.milestone}")
    for role in ROLES:
        c = tron.get(f"{role}_cmd")
        print(f"  {role}: {' '.join(c) if c else '(falls back to worker_cmd)'}")
    print(f"  verify: {' '.join(tron['verify_cmd'])}")
    print(f"start: scripts/tron.py run --milestone {args.milestone} --detach")
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
    r.add_argument("--accept-damage", action="store_true", help="resume a run that stopped for gate damage (the damage stays on the run branch)")
    r.add_argument("--detach", action="store_true", help="start the run as its own process (log docs/agent/tron/run-<id>.log) and wait for it; "
                   "ending this command or the session that started it does not end the run")
    c = sub.add_parser("check", help="readiness check for a milestone: lists what blocks an unattended run, starts nothing")
    c.add_argument("--milestone", required=True, help="milestone id, e.g. m-4")
    c.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    c.add_argument("--root", default=".", help="project root (default: current directory)")
    sw = sub.add_parser("sweep", help="start the planner in a fresh session; writes docs/agent/tron/SWEEP-<milestone>.md with the questions a run would hit")
    sw.add_argument("--milestone", required=True, help="milestone id, e.g. m-5")
    sw.add_argument("--force", action="store_true", help="overwrite an existing SWEEP file (its answers are lost)")
    sw.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    sw.add_argument("--root", default=".", help="project root (default: current directory)")
    rt = sub.add_parser("retro", help="start the retro analyst in a fresh session over a finished run; writes docs/agent/tron/RETRO-<run>.md")
    rt.add_argument("--run", dest="run_id", help="run id (default: the latest run)")
    rt.add_argument("--force", action="store_true", help="overwrite an existing RETRO file")
    rt.add_argument("--apply", action="store_true", help="also apply the tier 1 and 2 proposals on the run branch and check open experiments (R-TRON 'Retro changes')")
    rt.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    rt.add_argument("--root", default=".", help="project root (default: current directory)")
    df = sub.add_parser("defect", help="record a defect you found after a run (task, text); notes whether the evaluator had passed the task")
    df.add_argument("--run", dest="run_id", help="run id (default: the latest run)")
    df.add_argument("--task", help="task id, e.g. TASK-12")
    df.add_argument("--text", help="what is wrong, in one line")
    df.add_argument("--none", action="store_true", help="you found no (further) defect: makes the metric evaluator_misses known")
    df.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    df.add_argument("--root", default=".", help="project root (default: current directory)")
    ca = sub.add_parser("calibrate", help="draft example verdicts for the evaluator from defects it missed (tier 3); --accept/--reject D<n> takes your answer")
    ca.add_argument("--run", dest="run_id", help="run id (default: the latest run)")
    g = ca.add_mutually_exclusive_group()
    g.add_argument("--accept", metavar="D<n>", help="append that drafted example to .claude/agents/evaluator.md (your yes)")
    g.add_argument("--reject", metavar="D<n>", help="record your no for that drafted example")
    ca.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    ca.add_argument("--root", default=".", help="project root (default: current directory)")
    rp = sub.add_parser("report", help="write docs/agent/tron/REPORT-<run>.md from the journal and the backlog")
    rp.add_argument("--run-id", help="run id (default: the latest run)")
    rp.add_argument("--config", help="config file (default: docs/agent/stem-config.json)")
    rp.add_argument("--root", default=".", help="project root (default: current directory)")
    args = p.parse_args(argv)
    try:
        return {"report": cmd_report, "check": cmd_check, "sweep": cmd_sweep, "retro": cmd_retro, "defect": cmd_defect, "calibrate": cmd_calibrate}.get(args.cmd, cmd_run)(args)
    except TronError as e:
        print(f"tron: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
