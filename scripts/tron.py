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
import argparse, datetime, hashlib, json, os, pathlib, re, subprocess, sys, time, uuid

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
    env = dict(os.environ, STEM_TRON="1", STEM_TRON_RUN=run_id, STEM_TRON_TASK=task_id)
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
        if role == "evaluator":  # the verdict text goes to the verdict file, not into the journal
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
           ":(exclude,glob)docs/agent/tron/brief-*", ":(exclude,glob)docs/agent/tron/verdict-*"]
RUNNER_FILE = re.compile(r"^docs/agent/tron/(run-|REPORT-|STOP$|LOCK$|brief-|verdict-)")


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
    prot = set(PROTECTED) | {"scripts/run.sh"} | set(tron.get("protected", []))
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


def parse_verdict(text):
    """The last fenced json block that carries a verdict; None if there is none."""
    for b in reversed(re.findall(r"```json\s*(\{.*?\})\s*```", text or "", re.S)):
        try:
            d = json.loads(b)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("verdict") in ("pass", "fail"):
            return {"verdict": d["verdict"], "findings": list(d.get("findings") or []), "assumption_flags": list(d.get("assumption_flags") or [])}
    return None


def assumptions(root, ids):
    out = []
    files = task_files(root)
    for i in ids:
        if i in files:
            for l in parse_task(files[i].read_text())[2].splitlines():
                if re.match(r"\s*Assumption:", l):
                    out.append(f"{i}: {l.strip()}")
    return out


def read_rel(root, rel):
    p = root / rel
    return p.read_text() if p.is_file() else f"(no {rel})"


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
    diff = git_ok(root, "diff", "--no-renames", base, "--", ".", *EXCLUDE)
    parts += ["", "## Verification by the runner", f"exit code {code}", tail, "", "## Diff", diff[:60000] + ("\n(diff truncated)" if len(diff) > 60000 else "")]
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


def evaluate(root, tron, journal, jpath, target, base, g, task_ids, intent, abort_check):
    """One evaluator session. Returns {'verdict','findings','assumption_flags','file'} or {'damage': reason} or {'unavailable': reason}."""
    brief = write_brief(root, tron, journal, target, base, g, task_ids, intent)
    prompt = (f"You are the independent evaluator of an unattended Tron mode run. Read .claude/agents/evaluator.md and follow it exactly. "
              f"Your brief is {brief.relative_to(root)}. Do not change any file in the project.")
    before = fingerprint(root)
    verdict = None
    for attempt in (1, 2):  # a missing verdict gets one retry, then counts as a fail
        entry, up = sessions_with_retry(root, tron, "evaluator", target, journal["run_id"], journal["milestone"], journal, jpath, prompt, abort_check=abort_check)
        text = entry.pop("_out", "")
        if not up:
            return {"unavailable": entry.get("retry_aborted") or "API unavailable after retries"}
        if fingerprint(root) != before:
            return {"damage": f"evaluator session for {target} changed the working tree"}
        verdict = parse_verdict(text)
        entry["evaluator"] = {"target": target, "verdict": verdict["verdict"] if verdict else None}
        if verdict:
            break
    if not verdict:
        verdict = {"verdict": "fail", "assumption_flags": [], "findings": [{"ac": "-", "location": "evaluator output", "kind": "defect",
                   "scenario": "the evaluator gave no parseable verdict (final json block missing); treated as fail"}]}
    n = sum(1 for f in (root / JOURNAL_DIR).glob(f"verdict-{journal['run_id']}-{target}-*.json")) + 1
    vpath = root / JOURNAL_DIR / f"verdict-{journal['run_id']}-{target}-{n}.json"
    vpath.write_text(json.dumps(dict(verdict, target=target, at=now(), tail=(text or "")[-2000:]), indent=1) + "\n")
    entry["evaluator"]["file"] = str(vpath.relative_to(root))
    write_journal(jpath, journal)
    return dict(verdict, file=str(vpath.relative_to(root)))


def verdict_failure(ev):
    lines = []
    for f in ev["findings"]:
        lines.append(f"{f.get('ac', '-')} at {f.get('location', '?')}: {f.get('scenario', '')}")
    for a in ev["assumption_flags"]:
        lines.append(f"assumption conflicts: {a.get('assumption', '?')} ({a.get('conflict', '?')})")
    return {"passed": False, "placeholders": [], "deleted_files": [],
            "failures": [{"check": "evaluator", "reason": f"evaluator verdict fail: {len(ev['findings'])} finding(s), see {ev['file']}", "detail": "\n".join(lines)[:4000]}]}


def fingerprint(root):
    """Hash of HEAD, status and diff: equal before and after a session means the session left no diff."""
    parts = [head(root), git_ok(root, "status", "--porcelain", "--", ".", *EXCLUDE), git_ok(root, "diff", "HEAD", "--", ".", *EXCLUDE)]
    for f in git_ok(root, "ls-files", "--others", "--exclude-standard").splitlines():
        if not RUNNER_FILE.match(f) and (root / f).is_file():
            parts.append(f + ":" + hashlib.sha256((root / f).read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def signature(gate_result):
    return sorted((f["check"], f["reason"], hashlib.sha256(re.sub(r"\d+", "#", f.get("detail", "")).encode()).hexdigest()[:12])
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


def block_task(root, tron, task_id, base, reason, journal, refs0):
    """Failed work is kept (backup branch for commits, named stash for loose files), then the task's files go back to the state before the task."""
    kept = {}
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
        git_ok(root, "stash", "push", "-u", "-q", "-m", f"tron {journal['run_id']} {task_id} blocked", "--", ".", *EXCLUDE)
        if len(git_ok(root, "stash", "list").splitlines()) > n0:
            kept["stash"] = f"tron {journal['run_id']} {task_id} blocked"
    at_base = set(git_ok(root, "ls-tree", "-r", "--name-only", base).splitlines())
    for f in changed_paths(root, base):
        if f in at_base:
            git_ok(root, "checkout", base, "--", f)
        else:
            git_ok(root, "rm", "-rf", "-q", "--ignore-unmatch", "--", f)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode:
        git_ok(root, "commit", "-q", "-m", f"{task_id}: Tron run reset the files of the blocked task")
    note = f"Blocked by the Tron runner (run {journal['run_id']}): {reason}. Failed work kept: " + (", ".join(f"{k} {v}" for k, v in kept.items()) or "none")
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


def recover(root, journal, jpath):
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


def finish(journal, jpath, reason=None, complete=False):
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
    try:
        return run_loop(root, tron, args, milestone, jpath, run_id)
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def milestone_evaluation(root, tron, journal, jpath, accepted, start_commit, max_repairs, stop_reason, fin, branch, refs0, run_id, milestone):
    """Evaluator at milestone end; a fail gets repair sessions like a gate fail. Returns an exit code to end the run, None to complete it."""
    repairs, ev = 0, None
    while True:
        print(f"milestone {milestone}: evaluator session")
        ev = evaluate(root, tron, journal, jpath, "milestone", start_commit, None, accepted,
                      f"Milestone {milestone}: all accepted tasks of this run ({', '.join(accepted)}) work together as intended.", stop_reason)
        if "unavailable" in ev:
            fin(ev["unavailable"]); print("run ended early; run again to continue", file=sys.stderr); return 0
        if "damage" in ev:
            journal["aborted"] = "gate damage: " + ev["damage"]; journal["damage"] = True; fin(journal["aborted"])
            print(f"run stopped: {ev['damage']}", file=sys.stderr); return 4
        if ev["verdict"] == "pass" and not ev["assumption_flags"]:
            journal["milestone_verdict"] = "pass"; write_journal(jpath, journal)
            print(f"milestone {milestone}: evaluator says pass; {ev['file']}")
            return None
        if repairs >= max_repairs:
            fin(f"milestone evaluation failed after {repairs} repair(s): {ev['file']}")
            print(f"milestone {milestone}: evaluator still says fail; see {ev['file']}", file=sys.stderr)
            return 0
        repairs += 1
        g = verdict_failure(ev)
        base, acs_before = head(root), snapshot_acs(root)
        journal["in_progress"] = {"task": "baseline", "base": base, "acs_before": acs_before}
        prompt = repair_prompt(tron, "the milestone", g, repairs, max_repairs).replace("Work on backlog task the milestone", "Work on the findings of the milestone evaluation")
        entry, up = sessions_with_retry(root, tron, "worker", "milestone", run_id, milestone, journal, jpath, prompt, abort_check=stop_reason)
        if not up:
            fin(entry.get("retry_aborted") or "API unavailable after retries"); return 0
        entry["gate"] = gate(root, tron, None, base, acs_before, start_commit, branch, refs0)
        journal.pop("in_progress", None)
        write_journal(jpath, journal)
        if not entry["gate"]["passed"]:
            stop = sorted({f["check"] for f in entry["gate"]["failures"]} & STOPPING)
            journal["aborted"] = "gate damage: " + ", ".join(stop) if stop else "milestone repair failed the gate"
            journal["damage"] = bool(stop)
            fin(journal["aborted"])
            print(f"milestone repair failed the gate: {journal['aborted']}", file=sys.stderr)
            return 4 if stop else 3


def run_loop(root, tron, args, milestone, jpath, run_id):
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
        resume_ip = recover(root, journal, jpath)
        if tree_dirty(root):
            raise TronError("working tree is not clean; commit or stash first")
        journal["ended"] = None; journal["stop_reason"] = None
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
        finish(journal, jpath, reason, complete)

    def stop_reason(count_tasks=True):
        if stop_path.is_file():
            return "stop file docs/agent/tron/STOP"
        return limit_hit(journal, tron, max_tasks if count_tasks else None, t0)

    def settle(task_id, base, reason, repairs):
        kept = block_task(root, tron, task_id, base, reason, journal, refs0)
        journal["tasks"][task_id] = {"state": "blocked", "reason": reason, "repairs": repairs, "kept": kept}
        journal.pop("blocking", None); journal.pop("in_progress", None)
        write_journal(jpath, journal)
        print(f"{task_id}: BLOCKED ({reason})")

    if journal.get("blocking"):  # the runner was killed while blocking a task: finish that step first
        bl = journal["blocking"]
        settle(bl["task"], bl["base"], bl["reason"], bl.get("repairs", 0))
        resume_ip = None

    while True:
        why = stop_reason()
        if why:
            fin(why)
            print(f"run ended: {why}; run again to continue")
            return 0
        task_resumed = resume_ip is not None and resume_ip.get("task") != "baseline"
        if not task_resumed and verify(root, tron)[0]:  # baseline: a red branch gets a repair session before the next task
            print("baseline verification failed; starting a repair session")
            base, acs_before = head(root), snapshot_acs(root)
            journal["in_progress"] = {"task": "baseline", "base": base, "acs_before": acs_before}
            entry, up = sessions_with_retry(root, tron, "worker", "baseline", run_id, milestone, journal, jpath,
                                            tron.get("baseline_prompt", BASELINE_PROMPT), abort_check=stop_reason)
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
            todo = [t for t in ready_tasks(root, milestone, blocked_status) if t not in journal["tasks"] and t in acs0]
            if not todo:
                accepted = [i for i, v in journal["tasks"].items() if v["state"] == "accepted"]
                if accepted and tron.get("evaluator", "milestone") != "off" and journal.get("milestone_verdict") != "pass":
                    res = milestone_evaluation(root, tron, journal, jpath, accepted, start_commit, max_repairs, stop_reason, fin, branch, refs0, run_id, milestone)
                    if res is not None:
                        return res
                fin("no ready task left", complete=True)
                print(f"run {run_id} complete after {len(journal['tasks'])} task(s)")
                return 0
            task_id = todo[0]
            base, acs_before = head(root), snapshot_acs(root)
            repairs, last_sig = 0, None
        journal["in_progress"] = {"task": task_id, "base": base, "acs_before": acs_before, "repairs": repairs, "last_sig": last_sig}
        prompt = None
        outcome = None
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
                if tf and eval_due(tron, tf.read_text()):
                    print(f"{task_id}: evaluator session")
                    intent = tf.read_text()[:4000]
                    ev = evaluate(root, tron, journal, jpath, task_id, base, g, [task_id], intent, stop_reason)
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
            if fingerprint(root) == before:
                if entry["exit_code"] == 127:  # the agent command does not start: blocking every task would not help
                    fin("worker command could not start (exit 127): fix the config, then run again"); print("worker command could not start", file=sys.stderr); return 0
                outcome = ("blocked", "the session left no diff"); break
            if sig == last_sig:
                outcome = ("blocked", "the same failure twice in a row: " + "; ".join(r for _, r, _ in sig)); break
            last_sig = sig
            repairs += 1
            if repairs > max_repairs:
                outcome = ("blocked", f"still failing after {max_repairs} repair(s): " + "; ".join(r for _, r, _ in sig)); break
            why = stop_reason(count_tasks=False)
            journal["in_progress"].update(repairs=repairs, last_sig=last_sig)
            if why:
                fin(why); print(f"run ended: {why}; run again to continue"); return 0
            prompt = repair_prompt(tron, task_id, g, repairs, max_repairs)
        state, reason = outcome
        if state == "blocked":
            journal["blocking"] = {"task": task_id, "base": base, "reason": reason, "repairs": repairs}
            write_journal(jpath, journal)
            settle(task_id, base, reason, repairs)
            journal["no_diff_blocks"] = journal["no_diff_blocks"] + 1 if "no diff" in reason else 0
            if journal["no_diff_blocks"] >= 2:
                fin("two sessions in a row left no diff: check the agent setup (login, command, permissions), then run again")
                print("two sessions in a row left no diff: run ended", file=sys.stderr)
                return 0
        else:
            journal["no_diff_blocks"] = 0
            journal.pop("in_progress", None)
            journal["tasks"][task_id] = {"state": "accepted", "repairs": repairs}
        write_journal(jpath, journal)
        if state == "accepted" and pause_after == "task" and [t for t in ready_tasks(root, milestone, blocked_status) if t not in journal["tasks"] and t in acs0]:
            fin("pause_after task")
            print(f"paused after {task_id} (pause_after task); review: git log --oneline {start_commit[:8]}..HEAD; run again to continue")
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
    args = p.parse_args(argv)
    try:
        return cmd_run(args)
    except TronError as e:
        print(f"tron: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
