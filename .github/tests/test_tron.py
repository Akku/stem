#!/usr/bin/env python3
"""Fixture tests for scripts/tron.py (STEM maintenance only; run by stem-check.py or directly).
A fake `backlog` CLI and a fake agent command stand in for the real ones; nothing calls a model."""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TRON = ROOT / "scripts/tron.py"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

FAKE_BACKLOG = '''#!/usr/bin/env python3
import json, sys
st = json.load(open("state.json"))
if sys.argv[1:3] == ["task", "edit"]:
    import glob, re
    n = sys.argv[3].split("-")[1]
    status = sys.argv[sys.argv.index("-s") + 1]
    import os
    if status == "Blocked" and os.path.exists(os.environ["TRON_TEST_DIR"] + "/no_blocked_status"):
        sys.stderr.write("Invalid status: Blocked\\n"); sys.exit(1)
    note = sys.argv[sys.argv.index("--append-notes") + 1] if "--append-notes" in sys.argv else ""
    f = glob.glob("backlog/tasks/task-%s - *.md" % n)[0]
    s = re.sub(r"(?m)^status: .*$", "status: " + status, open(f).read())
    s = s.replace("<!-- SECTION:NOTES:END -->", note + "\\n<!-- SECTION:NOTES:END -->")
    if "--add-label" in sys.argv:
        s = s.replace("labels:\\n", "labels:\\n  - blocked\\n", 1)
    open(f, "w").write(s)
    for x in st["tasks"]:
        if x["id"] == "TASK-" + n: x["status"] = status
    json.dump(st, open("state.json", "w"))
    sys.exit(0)
if sys.argv[1:3] == ["task", "list"] and "--ready" in sys.argv:
    print("To Do:")
    for t in st["tasks"]:
        done = {x["id"] for x in st["tasks"] if x["status"] == "Done"}
        if t["status"] in ("To Do", "In Progress") and all(d in done for d in t.get("deps", [])):
            print("  [feature] %s - %s (ac: 0/1)" % (t["id"], t["title"]))
'''
FAKE_AGENT = '''#!/usr/bin/env python3
import glob, json, os, re, subprocess, sys
task, sid = sys.argv[1], sys.argv[2]
td = os.environ["TRON_TEST_DIR"]
open(td + "/calls.log", "a").write(json.dumps({"task": task, "stem_tron": os.environ.get("STEM_TRON"), "sid": sid}) + "\\n")
beh = json.load(open(td + "/behavior.json")).get(task, "ok")
if isinstance(beh, list):
    n = sum(1 for l in open(td + "/calls.log") if json.loads(l)["task"] == task)
    beh = beh[min(n, len(beh)) - 1]
if beh == "api_error":
    print(json.dumps({"is_error": True, "api_error_status": 529, "session_id": sid})); sys.stderr.write("overloaded\\n"); sys.exit(1)
if beh == "api_error0":
    print(json.dumps({"is_error": True, "api_error_status": 429, "session_id": sid})); sys.exit(0)
if beh == "hang_child":
    import subprocess as sp
    sp.Popen(["sh", "-c", "sleep 3; touch " + td + "/orphan"]); import time; time.sleep(10)
if beh == "hang":
    import time; time.sleep(10)
if beh == "crash":
    open("junk.txt", "w").write("half done"); os.kill(os.getppid(), 9); sys.exit(1)
def run(*a): subprocess.run(a, check=True, capture_output=True)
if task == "baseline":
    if os.path.exists(td + "/verify_fail") and beh != "stay_red": os.remove(td + "/verify_fail")
    print(json.dumps({"session_id": sid, "total_cost_usd": 0.1})); sys.exit(0)
if beh == "noop":
    sys.exit(0)
st = json.load(open("state.json"))
for t in st["tasks"]:
    if t["id"] == task: t["status"] = "Done"
json.dump(st, open("state.json", "w"))
f = glob.glob("backlog/tasks/task-%s - *.md" % task.split("-")[1])[0]
s = open(f).read()
s = s.replace("status: To Do", "status: Done").replace("- [ ] #1", "- [x] #1")
if beh != "no_evidence":
    s = s.replace("<!-- SECTION:NOTES:BEGIN -->\\n", "<!-- SECTION:NOTES:BEGIN -->\\nAC#1: E2 fake evidence\\n")
if beh == "ac_change":
    s = s.replace("works", "works differently")
open(f, "w").write(s)
if beh == "protected":
    open("scripts/tron.py", "a").write("# tampered\\n")
if beh == "verify_fail":
    open(td + "/verify_fail", "w").write("x")
if beh == "placeholder":
    os.makedirs("src", exist_ok=True)
    open("src/a.py", "w").write("def f():\\n    pass\\n# TODO later\\n")
if beh == "rename_protected":
    run("git", "mv", "scripts/tron.py", "scripts/t2.py")
if beh == "edit_runsh":
    open("scripts/run.sh", "a").write("# weakened\\n")
if beh == "leave_branch":
    run("git", "checkout", "-q", "-b", "elsewhere")
if beh == "rewrite_history":
    run("git", "reset", "-q", "--soft", "HEAD~1")
if beh == "new_task":
    open("backlog/tasks/task-9 - new.md", "w").write(open(f).read().replace("TASK-1", "TASK-9"))
    st = json.load(open("state.json")); st["tasks"].append({"id": "TASK-9", "title": "new", "status": "To Do", "deps": []}); json.dump(st, open("state.json", "w"))
if beh == "rename_task":
    run("git", "mv", f, "backlog/tasks/task-%s - renamed.md" % task.split("-")[1])
if beh == "hide":
    run("git", "update-index", "--skip-worktree", "scripts/run.sh"); open("scripts/run.sh", "a").write("# hidden\\n")
if beh == "delete_test":
    os.remove("scripts/t.py")
if beh == "ac_crash":
    open(f, "w").write(open(f).read().replace("works", "works differently"))
    run("git", "add", "-A"); run("git", "commit", "-qm", "sneaky"); os.kill(os.getppid(), 9); sys.exit(1)
if beh == "dirty":
    open("junk.txt", "w").write("x")
run("git", "add", "-A", ":!junk.txt")
run("git", "commit", "-qm", task + ": work")
print(json.dumps({"session_id": sid, "total_cost_usd": 0.25, "modelUsage": {"fake-model": {}}}))
'''
FAKE_EVALUATOR = '''#!/usr/bin/env python3
import json, os, re, sys
target, sid, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
td = os.environ["TRON_TEST_DIR"]
open(td + "/eval_calls.log", "a").write(target + "\\n")
n = sum(1 for l in open(td + "/eval_calls.log") if l.strip() == target)
plan = json.load(open(td + "/evaluator.json")).get(target, ["pass"])
v = plan[min(n, len(plan)) - 1]
brief = re.search(r"brief is (\\S+)\\.", prompt).group(1)
open(td + "/brief_copy.txt", "a").write(open(brief).read())
if v == "write":
    open("evaluator_wrote.txt", "w").write("x")
if v == "none":
    print("I looked at it and it seems fine."); sys.exit(0)
if v == "flag":
    j = {"verdict": "pass", "findings": [], "assumption_flags": [{"assumption": "uses cloud", "conflict": "invariant: no external data"}]}
elif v == "fail":
    j = {"verdict": "fail", "findings": [{"ac": "AC#1", "location": "src/a.py:1", "scenario": "run x, expected 1, got 2", "kind": "defect"}], "assumption_flags": []}
else:
    j = {"verdict": "pass", "findings": [], "assumption_flags": []}
print(json.dumps({"session_id": sid, "total_cost_usd": 0.05, "result": "ran it\\n```json\\n" + json.dumps(j) + "\\n```"}))
'''
FAKE_VERIFY = '''#!/bin/sh
[ -e "$TRON_TEST_DIR/verify_fail" ] && exit 1
exit 0
'''
TASK_MD = """---
id: {id}
title: t{id}
status: To Do
labels:
  - size-S
---

<!-- AC:BEGIN -->
- [ ] #1 it works
<!-- AC:END -->

<!-- SECTION:NOTES:BEGIN -->
<!-- SECTION:NOTES:END -->
"""


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=dict(os.environ, **GIT_ENV))


class Tron(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = self.tmp / "proj"; self.proj.mkdir()
        self.td = self.tmp / "td"; self.td.mkdir()  # fake agent log, behaviours and verify switch live outside the project
        self.bin = self.tmp / "bin"; self.bin.mkdir()
        for name, body in (("backlog", FAKE_BACKLOG), ("agent", FAKE_AGENT), ("verify", FAKE_VERIFY), ("evaluator", FAKE_EVALUATOR)):
            (self.bin / name).write_text(body); (self.bin / name).chmod(0o755)
        self.behavior({})
        self.evaluator_plan({})
        git(self.proj, "init", "-q", "-b", "main")
        (self.proj / "scripts").mkdir()
        (self.proj / "scripts/tron.py").write_text("# original\n")
        (self.proj / "scripts/run.sh").write_text("#!/bin/sh\n")
        (self.proj / "scripts/t.py").write_text("# test\n")
        self.state([("TASK-1", []), ("TASK-2", []), ("TASK-3", ["TASK-1"])])
        self.config({})
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "init")

    def behavior(self, d):
        (self.td / "behavior.json").write_text(json.dumps(d))

    def evaluator_plan(self, d):
        (self.td / "evaluator.json").write_text(json.dumps(d))

    def eval_calls(self):
        f = self.td / "eval_calls.log"
        return f.read_text().split() if f.exists() else []

    def with_evaluator(self, mode, **extra):
        self.config(dict({"evaluator": mode, "evaluator_cmd": [str(self.bin / "evaluator"), "{task_id}", "{session_id}", "{prompt}"]}, **extra))

    def calls(self):
        return [json.loads(l) for l in (self.td / "calls.log").read_text().splitlines()]

    def state(self, tasks):
        (self.proj / "state.json").write_text(json.dumps({"tasks": [{"id": i, "title": "t" + i, "status": "To Do", "deps": d} for i, d in tasks]}))
        (self.proj / "backlog/tasks").mkdir(parents=True, exist_ok=True)
        for i, _ in tasks:
            (self.proj / f"backlog/tasks/task-{i.split('-')[1]} - x.md").write_text(TASK_MD.format(id=i))

    def config(self, extra):
        (self.proj / "docs/agent").mkdir(parents=True, exist_ok=True)
        cfg = {"worker_cmd": [str(self.bin / "agent"), "{task_id}", "{session_id}", "{prompt}"], "verify_cmd": [str(self.bin / "verify")],
               "pause_after": "milestone", "backoff_base": 0, "evaluator": "off"}
        (self.proj / "docs/agent/stem-config.json").write_text(json.dumps({"tron": dict(cfg, **extra)}))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "config")

    def tron(self, *args):
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", **GIT_ENV, HOME=str(self.tmp), TRON_TEST_DIR=str(self.td))
        return subprocess.run([sys.executable, str(TRON), *args, "--root", str(self.proj)], capture_output=True, text=True, env=env)

    def journal(self):
        files = list((self.proj / "docs/agent/tron").glob("run-*.json"))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())

    def gate_of(self, task):
        return [s for s in self.journal()["sessions"] if s["task"] == task][0]["gate"]

    def test_two_tasks_in_order_on_run_branch_with_env(self):
        r = self.tron("run", "--milestone", "m-1", "--run-id", "r1")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual([c["task"] for c in calls], ["TASK-1", "TASK-2", "TASK-3"])  # TASK-3 became ready after TASK-1
        self.assertTrue(all(c["stem_tron"] == "1" for c in calls))
        self.assertEqual(git(self.proj, "branch", "--show-current").stdout.strip(), "tron/m-1")
        j = self.journal()
        self.assertEqual(j["run_id"], "r1"); self.assertIsNotNone(j["ended"])
        s = j["sessions"][0]
        for k in ("start", "end", "exit_code", "session_id", "cost_usd", "transcript", "model", "task", "role"):
            self.assertIn(k, s)
        self.assertEqual((s["exit_code"], s["cost_usd"], s["model"]), (0, 0.25, "fake-model"))
        self.assertTrue(s["transcript"].endswith(s["session_id"] + ".jsonl"))

    def test_second_run_reuses_branch(self):
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1", "--run-id", "a")
        git(self.proj, "checkout", "-q", "main")
        r = self.tron("run", "--milestone", "m-1", "--run-id", "b", "--max-tasks", "1")
        self.assertIn("reused", r.stdout)

    def test_no_ready_task(self):
        self.state([])
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no ready task", r.stdout)
        self.assertFalse((self.proj / "docs/agent/tron").exists())

    def test_missing_config(self):
        (self.proj / "docs/agent/stem-config.json").unlink()
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("config missing", r.stderr)
        (self.proj / "docs/agent/stem-config.json").write_text(json.dumps({"context_warning": False}))
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("worker_cmd", r.stderr)

    def test_dry_run_starts_nothing(self):
        r = self.tron("run", "--milestone", "m-1", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertIn("TASK-1, TASK-2", r.stdout); self.assertIn("STEM_TRON=1", r.stdout)
        self.assertFalse((self.td / "calls.log").exists())
        self.assertFalse((self.proj / "docs/agent/tron").exists())
        self.assertEqual(git(self.proj, "branch", "--show-current").stdout.strip(), "main")

    def test_dirty_tree_refused(self):
        (self.proj / "scripts/other.txt").write_text("changed")
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("not clean", r.stderr)

    def test_gate_pass(self):
        r = self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        g = self.gate_of("TASK-1")
        self.assertTrue(g["passed"], g)

    def test_gate_fails_without_evidence_line(self):
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        g = self.gate_of("TASK-1")
        self.assertFalse(g["passed"]); self.assertEqual([f["check"] for f in g["failures"]], ["evidence"])

    def test_gate_fails_when_session_did_not_finish(self):
        self.behavior({"TASK-1": "noop"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("status", [f["check"] for f in self.gate_of("TASK-1")["failures"]])

    def test_gate_fails_on_red_verification_run_by_the_runner(self):
        self.behavior({"TASK-1": "verify_fail"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual([f["check"] for f in self.gate_of("TASK-1")["failures"]], ["verify"])

    def test_gate_fails_on_dirty_tree(self):
        self.behavior({"TASK-1": "dirty"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual([f["check"] for f in self.gate_of("TASK-1")["failures"]], ["tree"])

    def test_gate_restores_changed_acs(self):
        self.behavior({"TASK-1": "ac_change"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        g = self.gate_of("TASK-1")
        self.assertEqual([f["check"] for f in g["failures"]], ["ac_freeze"])
        self.assertIn("TASK-1", g["failures"][0]["detail"])
        text = (self.proj / "backlog/tasks/task-1 - x.md").read_text()
        self.assertIn("it works\n", text); self.assertNotIn("differently", text)
        self.assertEqual(git(self.proj, "status", "--porcelain", "--", ".", ":!docs/agent/tron").stdout.strip(), "")

    def test_gate_fails_on_protected_file(self):
        self.behavior({"TASK-1": "protected"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        g = self.gate_of("TASK-1")
        self.assertEqual([f["check"] for f in g["failures"]], ["protected"])
        self.assertIn("scripts/tron.py", g["failures"][0]["reason"])

    def test_red_baseline_gets_repair_session_before_next_task(self):
        (self.td / "verify_fail").write_text("x")
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual([c["task"] for c in self.calls()], ["baseline", "TASK-1"])
        self.assertTrue(self.gate_of("baseline")["passed"])

    def test_red_baseline_that_stays_red_stops_the_run(self):
        (self.td / "verify_fail").write_text("x"); self.behavior({"baseline": "stay_red"})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 3)
        self.assertEqual([c["task"] for c in self.calls()], ["baseline"])
        self.assertIn("baseline", self.journal()["aborted"])

    def test_placeholder_scan_lists_hits_in_journal(self):
        self.behavior({"TASK-1": "placeholder"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        kinds = {(h["file"], h["kind"]) for h in self.gate_of("TASK-1")["placeholders"]}
        self.assertIn(("src/a.py", "marker"), kinds); self.assertIn(("src/a.py", "empty body"), kinds)

    def test_missing_verify_cmd_is_an_error(self):
        cfg = json.loads((self.proj / "docs/agent/stem-config.json").read_text()); del cfg["tron"]["verify_cmd"]
        (self.proj / "docs/agent/stem-config.json").write_text(json.dumps(cfg))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "cfg")
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("verify_cmd", r.stderr)

    def checks(self, task="TASK-1"):
        return [f["check"] for f in self.gate_of(task)["failures"]]

    def test_review_rename_of_protected_file_is_caught(self):
        self.behavior({"TASK-1": "rename_protected"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("protected", self.checks())

    def test_review_verdict_files_are_protected(self):
        self.behavior({"TASK-1": "edit_runsh"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("protected", self.checks())

    def test_review_leaving_the_run_branch_is_caught_and_stops_the_run(self):
        self.behavior({"TASK-1": "leave_branch"})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 4)
        self.assertIn("branch", self.checks()); self.assertIn("refs", self.checks())
        self.assertEqual([c["task"] for c in self.calls()], ["TASK-1"])
        self.assertIn("gate damage", self.journal()["aborted"])

    def test_review_rewritten_history_is_caught(self):
        self.behavior({"TASK-1": "rewrite_history"})
        (self.proj / "scripts/extra.txt").write_text("x"); git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "extra")
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("branch", self.checks())

    def test_review_git_failure_is_a_failure_not_a_pass(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import tron
        g = tron.gate(self.proj, {"verify_cmd": [str(self.bin / "verify")]}, "TASK-1", "0" * 40, {}, "0" * 40, "main", {})
        self.assertFalse(g["passed"]); self.assertIn("git", [f["check"] for f in g["failures"]])

    def test_review_tasks_created_by_a_session_are_not_run(self):
        self.behavior({"TASK-1": "new_task"})
        self.tron("run", "--milestone", "m-1")
        self.assertNotIn("TASK-9", [c["task"] for c in self.calls()])

    def test_review_renamed_task_file_is_still_ac_checked_against_run_start(self):
        self.behavior({"TASK-1": "rename_task"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.checks(), [])  # same ACs under a new file name: no false alarm
        self.assertTrue(self.gate_of("TASK-1")["passed"])

    def test_review_hidden_edits_are_caught(self):
        self.behavior({"TASK-1": "hide"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("tree", self.checks())

    def test_review_deleted_files_are_listed_for_the_evaluator(self):
        self.behavior({"TASK-1": "delete_test"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.gate_of("TASK-1")["deleted_files"], ["scripts/t.py"])

    def test_cost_limit_ends_run_after_current_session(self):
        self.config({"max_cost": 0.25})
        self.tron("run", "--milestone", "m-1")
        self.assertEqual([c["task"] for c in self.calls()], ["TASK-1"])
        j = self.journal(); self.assertIn("max_cost", j["stop_reason"]); self.assertFalse(j["complete"])

    def test_repair_then_pass(self):
        self.behavior({"TASK-1": ["no_evidence", "ok"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        s = [x for x in self.journal()["sessions"] if x["task"] == "TASK-1"]
        self.assertEqual([x["gate"]["passed"] for x in s], [False, True])
        self.assertEqual(self.journal()["tasks"]["TASK-1"], {"state": "accepted", "repairs": 1})

    def test_three_fails_then_blocked_and_run_continues(self):
        self.config({"max_repairs": 2})
        self.behavior({"TASK-1": ["no_evidence", "dirty", "no_evidence"]})
        self.tron("run", "--milestone", "m-1")
        j = self.journal()
        self.assertEqual(j["tasks"]["TASK-1"]["state"], "blocked")
        self.assertEqual(sum(1 for c in self.calls() if c["task"] == "TASK-1"), 3)
        self.assertEqual(j["tasks"]["TASK-2"]["state"], "accepted")
        self.assertNotIn("TASK-3", j["tasks"])  # depends on the blocked task
        text = (self.proj / "backlog/tasks/task-1 - x.md").read_text()
        self.assertIn("status: Blocked", text); self.assertIn("Blocked by the Tron runner", text)
        self.assertNotIn("[x]", text)  # files reset to the state before the task
        self.assertFalse((self.proj / "junk.txt").exists())
        self.assertTrue(j["tasks"]["TASK-1"]["kept"])

    def test_stop_file_ends_run(self):
        (self.proj / "docs/agent/tron").mkdir(parents=True, exist_ok=True)
        (self.proj / "docs/agent/tron/STOP").write_text("")
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.td / "calls.log").exists())
        self.assertIn("STOP", self.journal()["stop_reason"])

    def test_pause_after_task_is_default_and_milestone_runs_on(self):
        self.config({"pause_after": "task"})
        self.tron("run", "--milestone", "m-1")
        self.assertEqual([c["task"] for c in self.calls()], ["TASK-1"])
        self.assertIn("pause_after", self.journal()["stop_reason"])
        self.tron("run", "--milestone", "m-1")  # resume: next task, TASK-1 not repeated
        self.assertEqual([c["task"] for c in self.calls()], ["TASK-1", "TASK-2"])

    def test_resume_after_killed_runner(self):
        self.behavior({"TASK-2": ["crash", "ok"]})
        r = self.tron("run", "--milestone", "m-1")
        self.assertNotEqual(r.returncode, 0)  # runner was killed
        self.assertIn("in_progress", self.journal())
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["task"] for c in self.calls()], ["TASK-1", "TASK-2", "TASK-2", "TASK-3"])
        j = self.journal(); self.assertTrue(j["complete"]); self.assertIn("stash", j["recovered"][0])
        self.assertTrue(all(v["state"] == "accepted" for v in j["tasks"].values()))

    def test_session_timeout_kills_hanging_session(self):
        self.config({"session_timeout": 1})
        self.behavior({"TASK-1": "hang"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        s = self.journal()["sessions"][0]
        self.assertTrue(s["timeout"]); self.assertEqual(s["exit_code"], 124)
        self.assertEqual(self.journal()["tasks"]["TASK-1"]["state"], "blocked")  # no diff

    def test_same_failure_twice_blocks_without_using_all_repairs(self):
        self.config({"max_repairs": 5})
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(sum(1 for c in self.calls() if c["task"] == "TASK-1"), 2)
        self.assertIn("same failure", self.journal()["tasks"]["TASK-1"]["reason"])

    def test_session_without_diff_blocks_at_once(self):
        self.behavior({"TASK-1": "noop"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(sum(1 for c in self.calls() if c["task"] == "TASK-1"), 1)
        self.assertIn("no diff", self.journal()["tasks"]["TASK-1"]["reason"])

    def test_api_errors_are_retried_and_not_counted_as_repairs(self):
        self.behavior({"TASK-1": ["api_error", "api_error", "ok"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        j = self.journal()
        self.assertEqual(len([s for s in j["sessions"] if s.get("api_error")]), 2)
        self.assertEqual(j["tasks"]["TASK-1"], {"state": "accepted", "repairs": 0})

    def test_api_unavailable_after_retries_ends_run_resumable(self):
        self.config({"api_retries": 1})
        self.behavior({"TASK-1": "api_error"})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 0)
        j = self.journal(); self.assertIn("API unavailable", j["stop_reason"]); self.assertFalse(j["complete"])
        self.assertNotIn("TASK-1", j["tasks"])

    def test_review_damage_stops_resume_unless_accepted(self):
        self.behavior({"TASK-1": "edit_runsh"})
        self.assertEqual(self.tron("run", "--milestone", "m-1").returncode, 4)
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("--accept-damage", r.stderr)
        self.behavior({})
        r = self.tron("run", "--milestone", "m-1", "--accept-damage")
        self.assertNotEqual(r.returncode, 2, r.stderr)
        self.assertTrue(self.journal()["damage_history"])

    def test_review_commits_of_a_killed_session_stay_under_the_gate(self):
        self.behavior({"TASK-1": "ac_crash"})
        self.tron("run", "--milestone", "m-1")  # runner killed after a sneaky AC commit
        self.behavior({})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("ac_freeze", self.journal()["aborted"])

    def test_review_blocked_task_is_not_offered_again_in_a_new_run(self):
        (self.td / "no_blocked_status").write_text("x")
        self.behavior({"TASK-1": "noop"})
        self.tron("run", "--milestone", "m-1", "--run-id", "one")
        self.assertIn("blocked", (self.proj / "backlog/tasks/task-1 - x.md").read_text())
        calls = len(self.calls())
        r = self.tron("run", "--milestone", "m-1", "--run-id", "two")
        self.assertEqual(len(self.calls()), calls, r.stdout)

    def test_review_fingerprint_sees_content_of_untracked_files(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import tron
        (self.proj / "new.py").write_text("a"); a = tron.fingerprint(self.proj)
        (self.proj / "new.py").write_text("b"); self.assertNotEqual(a, tron.fingerprint(self.proj))

    def test_review_signature_tells_progress_from_repetition(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import tron
        g = lambda d: {"failures": [{"check": "verify", "reason": "verification exited 1", "detail": d}]}
        self.assertNotEqual(tron.signature(g("FAIL test_a\nFAIL test_b")), tron.signature(g("FAIL test_b")))
        self.assertEqual(tron.signature(g("FAIL test_b 12s")), tron.signature(g("FAIL test_b 15s")))

    def test_review_worker_that_cannot_start_ends_run_without_blocking(self):
        self.config({"worker_cmd": [str(self.tmp / "nowhere"), "{task_id}"]})
        r = self.tron("run", "--milestone", "m-1")
        j = self.journal()
        self.assertIn("could not start", j["stop_reason"]); self.assertEqual(j["tasks"], {})

    def test_review_two_dead_sessions_in_a_row_end_the_run(self):
        self.behavior({"TASK-1": "noop", "TASK-2": "noop"})
        self.tron("run", "--milestone", "m-1")
        self.assertIn("two sessions in a row", self.journal()["stop_reason"])

    def test_review_timeout_kills_children_of_the_session(self):
        self.config({"session_timeout": 1})
        self.behavior({"TASK-1": "hang_child"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        import time; time.sleep(4)
        self.assertFalse((self.td / "orphan").exists())

    def test_review_api_error_with_exit_zero_is_retried(self):
        self.behavior({"TASK-1": ["api_error0", "ok"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.journal()["tasks"]["TASK-1"], {"state": "accepted", "repairs": 0})

    def test_review_second_runner_is_refused_while_one_is_active(self):
        (self.proj / "docs/agent/tron").mkdir(parents=True, exist_ok=True)
        (self.proj / "docs/agent/tron/LOCK").write_text(str(os.getpid()))
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("another run", r.stderr)

    def test_evaluator_pass_at_milestone_end_only_by_default(self):
        self.with_evaluator("milestone")
        self.tron("run", "--milestone", "m-1")
        self.assertEqual(self.eval_calls(), ["milestone"])
        j = self.journal(); self.assertEqual(j["milestone_verdict"], "pass"); self.assertTrue(j["complete"])
        self.assertTrue(list((self.proj / "docs/agent/tron").glob("verdict-*-milestone-1.json")))

    def test_evaluator_off_never_runs(self):
        self.with_evaluator("off")
        self.tron("run", "--milestone", "m-1")
        self.assertEqual(self.eval_calls(), []); self.assertTrue(self.journal()["complete"])

    def test_evaluator_runs_per_task_on_review_label(self):
        self.with_evaluator("milestone")
        f = self.proj / "backlog/tasks/task-2 - x.md"
        f.write_text(f.read_text().replace("  - size-S", "  - size-S\n  - review"))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "label")
        self.tron("run", "--milestone", "m-1")
        self.assertEqual(self.eval_calls(), ["TASK-2", "milestone"])

    def test_evaluator_task_mode_runs_for_every_task(self):
        self.with_evaluator("task")
        self.tron("run", "--milestone", "m-1")
        self.assertEqual(self.eval_calls(), ["TASK-1", "TASK-2", "TASK-3", "milestone"])

    def test_evaluator_fail_is_handled_like_a_gate_fail_then_repair_then_pass(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["fail", "pass"]})
        self.behavior({"TASK-1": ["ok", "placeholder"]})  # repair changes something, so it is no stall
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        j = self.journal()
        self.assertEqual(j["tasks"]["TASK-1"], {"state": "accepted", "repairs": 1})
        self.assertEqual(self.eval_calls(), ["TASK-1", "TASK-1"])
        self.assertEqual(len(list((self.proj / "docs/agent/tron").glob("verdict-*-TASK-1-*.json"))), 2)
        brief = (self.td / "brief_copy.txt").read_text()
        self.assertIn("## Acceptance criteria", brief); self.assertIn("## Invariants", brief); self.assertIn("## Diff", brief)

    def test_evaluator_brief_holds_assumptions_and_hints(self):
        self.with_evaluator("task")
        self.behavior({"TASK-1": "placeholder"})
        f = self.proj / "backlog/tasks/task-1 - x.md"
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        brief = (self.td / "brief_copy.txt").read_text()
        self.assertIn("Placeholder hits", brief); self.assertIn("src/a.py", brief)
        self.assertIn("Assumption list", brief)

    def test_evaluator_assumption_conflict_fails_even_with_pass(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["flag"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        s = [x for x in self.journal()["sessions"] if x["role"] == "evaluator"][0]
        self.assertEqual(s["evaluator"]["verdict"], "pass")
        self.assertIn("evaluator", [f["check"] for f in [x for x in self.journal()["sessions"] if x["role"] == "worker"][0]["gate_after_evaluator"]["failures"]])

    def test_evaluator_without_verdict_counts_as_fail(self):
        self.with_evaluator("task", max_repairs=0)
        self.evaluator_plan({"TASK-1": ["none"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.journal()["tasks"]["TASK-1"]["state"], "blocked")
        self.assertEqual(self.eval_calls(), ["TASK-1", "TASK-1"])  # one retry

    def test_evaluator_that_writes_into_the_project_stops_the_run(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["write"]})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 4); self.assertIn("evaluator", self.journal()["aborted"])

    def test_milestone_evaluator_fail_gets_repair_sessions(self):
        self.with_evaluator("milestone", max_repairs=1)
        self.evaluator_plan({"milestone": ["fail", "fail"]})
        r = self.tron("run", "--milestone", "m-1")
        j = self.journal()
        self.assertFalse(j["complete"]); self.assertIn("milestone evaluation failed", j["stop_reason"])
        self.assertEqual(self.eval_calls(), ["milestone", "milestone"])

    def test_role_commands_fall_back_to_worker(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import tron
        cfg = {"worker_cmd": ["w"], "evaluator_cmd": ["e"]}
        self.assertEqual(tron.command_for(cfg, "evaluator"), ["e"])
        for role in ("doctor", "planner", "retro", "worker"):
            self.assertEqual(tron.command_for(cfg, role), ["w"])

    def test_runner_never_publishes(self):
        src = TRON.read_text()
        # 'git stash push' keeps work safe and is the one allowed use of the word
        self.assertIsNone(re.search(r"""(?<!"stash", )["'](push|tag|merge)["']|git\s+(push|tag|merge)\b""", src))


if __name__ == "__main__":
    unittest.main()
