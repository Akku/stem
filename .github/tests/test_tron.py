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
if sys.argv[1:3] == ["task", "list"] and "--ready" in sys.argv:
    print("To Do:")
    for t in st["tasks"]:
        done = {x["id"] for x in st["tasks"] if x["status"] == "Done"}
        if t["status"] == "To Do" and all(d in done for d in t.get("deps", [])):
            print("  [feature] %s - %s (ac: 0/1)" % (t["id"], t["title"]))
'''
FAKE_AGENT = '''#!/usr/bin/env python3
import glob, json, os, re, subprocess, sys
task, sid = sys.argv[1], sys.argv[2]
td = os.environ["TRON_TEST_DIR"]
open(td + "/calls.log", "a").write(json.dumps({"task": task, "stem_tron": os.environ.get("STEM_TRON"), "sid": sid}) + "\\n")
beh = json.load(open(td + "/behavior.json")).get(task, "ok")
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
if beh == "dirty":
    open("junk.txt", "w").write("x")
run("git", "add", "-A", ":!junk.txt")
run("git", "commit", "-qm", task + ": work")
print(json.dumps({"session_id": sid, "total_cost_usd": 0.25, "modelUsage": {"fake-model": {}}}))
'''
FAKE_VERIFY = '''#!/bin/sh
[ -e "$TRON_TEST_DIR/verify_fail" ] && exit 1
exit 0
'''
TASK_MD = """---
id: {id}
title: t{id}
status: To Do
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
        for name, body in (("backlog", FAKE_BACKLOG), ("agent", FAKE_AGENT), ("verify", FAKE_VERIFY)):
            (self.bin / name).write_text(body); (self.bin / name).chmod(0o755)
        self.behavior({})
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

    def calls(self):
        return [json.loads(l) for l in (self.td / "calls.log").read_text().splitlines()]

    def state(self, tasks):
        (self.proj / "state.json").write_text(json.dumps({"tasks": [{"id": i, "title": "t" + i, "status": "To Do", "deps": d} for i, d in tasks]}))
        (self.proj / "backlog/tasks").mkdir(parents=True, exist_ok=True)
        for i, _ in tasks:
            (self.proj / f"backlog/tasks/task-{i.split('-')[1]} - x.md").write_text(TASK_MD.format(id=i))

    def config(self, extra):
        (self.proj / "docs/agent").mkdir(parents=True, exist_ok=True)
        cfg = {"worker_cmd": [str(self.bin / "agent"), "{task_id}", "{session_id}", "{prompt}"], "verify_cmd": [str(self.bin / "verify")]}
        (self.proj / "docs/agent/stem-config.json").write_text(json.dumps({"tron": dict(cfg, **extra)}))

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

    def test_role_commands_fall_back_to_worker(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import tron
        cfg = {"worker_cmd": ["w"], "evaluator_cmd": ["e"]}
        self.assertEqual(tron.command_for(cfg, "evaluator"), ["e"])
        for role in ("doctor", "planner", "retro", "worker"):
            self.assertEqual(tron.command_for(cfg, role), ["w"])

    def test_runner_never_publishes(self):
        src = TRON.read_text()
        self.assertIsNone(re.search(r"""["'](push|tag|merge)["']|git\s+(push|tag|merge)\b""", src))


if __name__ == "__main__":
    unittest.main()
