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
if sys.argv[1:3] == ["task", "create"]:
    import os
    a = sys.argv
    n = max(int(x["id"].split("-")[1]) for x in st["tasks"]) + 1
    acs = [a[i + 1] for i, x in enumerate(a) if x == "--ac"]
    labels = a[a.index("-l") + 1].split(",") if "-l" in a else []
    body = "---\\nid: TASK-%d\\ntitle: %s\\nstatus: To Do\\nmilestone: %s\\nlabels:\\n%s---\\n\\n<!-- AC:BEGIN -->\\n%s\\n<!-- AC:END -->\\n\\n<!-- SECTION:NOTES:BEGIN -->\\n<!-- SECTION:NOTES:END -->\\n" % (
        n, a[2], a[a.index("-m") + 1], "".join("  - %s\\n" % l for l in labels), "\\n".join("- [ ] #%d %s" % (k + 1, t) for k, t in enumerate(acs)))
    open("backlog/tasks/task-%d - sub.md" % n, "w").write(body)
    st["tasks"].append({"id": "TASK-%d" % n, "title": a[2], "status": "To Do", "deps": []})
    json.dump(st, open("state.json", "w"))
    print("Created task TASK-%d" % n); sys.exit(0)
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
if task == "milestone":
    if beh != "noop":
        n = sum(1 for l in open(td + "/calls.log") if json.loads(l)["task"] == "milestone")
        open("m_%d.txt" % n, "w").write("fix"); run("git", "add", "-A"); run("git", "commit", "-qm", "milestone fix")
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
if beh == "draft_block":
    os.makedirs("backlog/drafts", exist_ok=True)
    open("backlog/drafts/draft-1 - Decide-x.md", "w").write("---\\nid: DRAFT-1\\ntitle: Decide x\\n---\\n")
    s3 = open(f).read(); open(f, "w").write(s3.replace("<!-- SECTION:NOTES:END -->", "BLOCKED: need a decision on x\\n<!-- SECTION:NOTES:END -->"))
    open("junk.txt", "w").write("half done")
if beh == "note_only":
    s3 = open(f).read(); open(f, "w").write(s3.replace("status: Done", "status: To Do").replace("- [x] #1", "- [ ] #1").replace("AC#1: E2 fake evidence\\n", "").replace("<!-- SECTION:NOTES:END -->", "BLOCKED: need a decision\\n<!-- SECTION:NOTES:END -->"))
if beh == "extrapolated":
    s3 = open(f).read(); open(f, "w").write(s3.replace("AC#1: E2 fake evidence", "AC#1: E2 extrapolated from 52 MB"))
if beh == "assume_nobasis":
    s3 = open(f).read(); open(f, "w").write(s3.replace("AC#1: E2 fake evidence\\n", "AC#1: E2 fake evidence\\nAssumption: CSV is fine\\nAssumption: sep is comma (basis: P-3)\\n"))
if beh == "overwrite_notes":
    s3 = open(f).read(); open(f, "w").write(re.sub(r"(?s)<!-- SECTION:NOTES:BEGIN -->.*<!-- SECTION:NOTES:END -->", "<!-- SECTION:NOTES:BEGIN -->\\nAC#1: E2 fake evidence\\n<!-- SECTION:NOTES:END -->", s3))
if beh == "protected":
    open("scripts/tron.py", "a").write("# tampered\\n")
if beh == "verify_fail":
    open(td + "/verify_fail", "w").write("x")
if beh == "placeholder":
    os.makedirs("src", exist_ok=True)
    open("src/a.py", "w").write("def f():\\n    pass\\n# TODO later\\n")
if beh == "unlabel":
    s2 = open(f).read(); open(f, "w").write(s2.replace("  - review\\n", ""))
if beh == "edit_scenario":
    open("docs/agent/tron/ACCEPTANCE-m-1.md", "a").write("weakened")
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
    s2 = open(f).read(); open(f, "w").write(s2.replace("works", "works differently"))
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
if v == "write_tracked":
    open("scripts/t.py", "a").write("# tampered\\n")
if v == "none":
    print("I looked at it and it seems fine."); sys.exit(0)
if v == "risk":
    j = {"verdict": "fail", "findings": [{"ac": "-", "location": "x", "scenario": "1 GB input with one 4 MB word", "kind": "risk"}], "assumption_flags": [], "checked": [{"ac": "AC#1"}]}
elif v == "bad_kind":
    j = {"verdict": "pass", "findings": [{"ac": "AC#1", "kind": "whatever"}], "assumption_flags": [], "checked": [{"ac": "AC#1"}]}
elif v == "flag":
    j = {"verdict": "pass", "findings": [], "checked": [{"ac": "AC#1"}], "assumption_flags": [{"assumption": "uses cloud", "conflict": "invariant: no external data"}]}
elif v == "unverifiable":
    j = {"verdict": "fail", "findings": [{"ac": "AC#1", "location": "x", "scenario": "no start command", "kind": "not_verifiable"}], "assumption_flags": []}
elif v == "fail":
    j = {"verdict": "fail", "findings": [{"ac": "AC#1", "location": "src/a.py:1", "scenario": "run x, expected 1, got 2", "kind": "defect"}], "assumption_flags": []}
else:
    j = {"verdict": "pass", "findings": [], "assumption_flags": [], "checked": [{"ac": "AC#1", "how": "ran it", "observed": "ok"}]}
print(json.dumps({"session_id": sid, "total_cost_usd": 0.05, "result": "ran it\\n```json\\n" + json.dumps(j) + "\\n```"}))
'''
FAKE_DOCTOR = '''#!/usr/bin/env python3
import json, os, re, sys
target, sid, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
td = os.environ["TRON_TEST_DIR"]
open(td + "/doctor_calls.log", "a").write(target + "\\n")
n = sum(1 for l in open(td + "/doctor_calls.log") if l.strip() == target)
plan = json.load(open(td + "/doctor.json")).get(target, ["none"])
v = plan[min(n, len(plan)) - 1]
brief = re.search(r"brief is (\\S+)\\.", prompt).group(1)
open(td + "/doctor_brief.txt", "w").write(open(brief).read())
if v == "none":
    print(json.dumps({"session_id": sid, "result": "no idea"})); sys.exit(0)
if v == "write":
    open("doctor_wrote.txt", "w").write("x")
    v = {"verdict": "needs_user", "diagnosis": "d", "question": "q?"}
print(json.dumps({"session_id": sid, "total_cost_usd": 0.07, "result": "diagnosis\\n```json\\n" + json.dumps(v) + "\\n```"}))
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
        for name, body in (("backlog", FAKE_BACKLOG), ("agent", FAKE_AGENT), ("verify", FAKE_VERIFY), ("evaluator", FAKE_EVALUATOR), ("doctor", FAKE_DOCTOR)):
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

    def with_doctor(self, plan, **extra):
        (self.td / "doctor.json").write_text(json.dumps(plan))
        self.config(dict({"doctor_cmd": [str(self.bin / "doctor"), "{task_id}", "{session_id}", "{prompt}"]}, **extra))

    def two_acs(self, tid="1"):
        f = self.proj / f"backlog/tasks/task-{tid} - x.md"
        f.write_text(f.read_text().replace("- [ ] #1 it works\n", "- [ ] #1 it works\n- [ ] #2 it also works\n"))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "two acs")

    def doctor_calls(self):
        p = self.td / "doctor_calls.log"
        return p.read_text().split() if p.exists() else []

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
               "pause_after": "milestone", "backoff_base": 0, "evaluator": "off", "sweep": False}
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

    def test_gate_fails_on_extrapolated_figure_graded_e2(self):
        self.config({"max_repairs": 0})
        self.behavior({"TASK-1": "extrapolated"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        r = self.journal()["tasks"]["TASK-1"]
        self.assertEqual(r["state"], "blocked"); self.assertIn("extrapolated", r["reason"])

    def test_gate_fails_when_a_note_line_from_before_the_task_is_missing(self):
        f = self.proj / "backlog/tasks/task-1 - x.md"
        f.write_text(f.read_text().replace("<!-- SECTION:NOTES:BEGIN -->\n", "<!-- SECTION:NOTES:BEGIN -->\nUser decision: keep the CSV format\n"))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "user note")
        self.config({"max_repairs": 0})
        self.behavior({"TASK-1": "overwrite_notes"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        r = self.journal()["tasks"]["TASK-1"]
        self.assertEqual(r["state"], "blocked"); self.assertIn("User decision: keep the CSV format", r["reason"])

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

    def test_blocked_task_keeps_draft_and_worker_notes(self):
        self.config({"max_repairs": 0})
        self.behavior({"TASK-1": ["draft_block"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.journal()["tasks"]["TASK-1"]["state"], "blocked")
        self.assertTrue((self.proj / "backlog/drafts/draft-1 - Decide-x.md").exists())
        text = (self.proj / "backlog/tasks/task-1 - x.md").read_text()
        self.assertIn("status: Blocked", text); self.assertIn("need a decision on x", text)
        self.assertNotIn("[x]", text)
        self.assertFalse((self.proj / "junk.txt").exists())  # code changes still reset
        self.assertIn("Decide x", (self.proj / "docs/agent/tron" / next((self.proj / "docs/agent/tron").glob("REPORT-*")).name).read_text())

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

    def test_doctor_retry_with_hint_then_accepted(self):
        self.with_doctor({"TASK-1": [{"verdict": "retry_with_hint", "diagnosis": "wrong file", "hint": "evidence line missing"}]})
        self.behavior({"TASK-1": ["no_evidence", "no_evidence", "ok"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        t = self.journal()["tasks"]["TASK-1"]
        self.assertEqual((t["state"], t["repairs"]), ("accepted", 2))
        self.assertEqual([x["result"] for x in t["ladder"] if x["step"] == "doctor"], ["retry_with_hint"])
        self.assertEqual(self.doctor_calls(), ["TASK-1"])
        self.assertIn("## Attempts", (self.td / "doctor_brief.txt").read_text())

    def test_doctor_runs_once_then_the_task_blocks(self):
        self.with_doctor({"TASK-1": [{"verdict": "retry_with_hint", "diagnosis": "x", "hint": "y"}]})
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.doctor_calls(), ["TASK-1"])
        self.assertEqual(self.journal()["tasks"]["TASK-1"]["state"], "blocked")

    def test_doctor_environment_problem_runs_one_baseline_repair_then_repair(self):
        self.with_doctor({"TASK-1": [{"verdict": "environment_problem", "diagnosis": "verify tool missing"}]})
        self.behavior({"TASK-1": ["no_evidence", "no_evidence", "ok"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        t = self.journal()["tasks"]["TASK-1"]
        self.assertEqual(t["state"], "accepted", t)
        self.assertEqual([(x["step"], x["result"]) for x in t["ladder"]][:2], [("doctor", "environment_problem"), ("baseline repair", "passed")])
        self.assertEqual([c["task"] for c in self.calls()].count("baseline"), 1)

    def test_doctor_needs_user_writes_a_draft_and_blocks(self):
        self.with_doctor({"TASK-1": [{"verdict": "needs_user", "diagnosis": "conflict", "question": "csv or json?"}]})
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        t = self.journal()["tasks"]["TASK-1"]
        self.assertEqual(t["state"], "blocked"); self.assertIn("the Doctor needs the user", t["reason"])
        drafts = list((self.proj / "backlog/drafts").glob("draft-*"))
        self.assertEqual(len(drafts), 1); self.assertIn("csv or json?", drafts[0].read_text())
        self.assertIn("draft question", [x["step"] for x in t["ladder"]])
        rep = (self.proj / "docs/agent/tron" / next((self.proj / "docs/agent/tron").glob("REPORT-*.md")).name).read_text()
        self.assertIn("ladder: doctor: needs_user", rep)

    def split_plan(self, acs_a=("it works",), acs_b=("it also works",)):
        return {"verdict": "split_task", "diagnosis": "too big", "subtasks": [{"title": "part a", "acs": list(acs_a)}, {"title": "part b", "acs": list(acs_b)}]}

    def test_doctor_split_creates_subtasks_and_parent_closes_when_they_pass(self):
        self.two_acs()
        self.with_doctor({"TASK-1": [self.split_plan()]})
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1")
        j = self.journal()
        t = j["tasks"]["TASK-1"]
        self.assertEqual(t["closed_by"], ["TASK-4", "TASK-5"]); self.assertEqual(t["state"], "accepted")
        self.assertEqual([j["tasks"][i]["state"] for i in ("TASK-4", "TASK-5")], ["accepted", "accepted"])
        self.assertIn("status: Done", (self.proj / "backlog/tasks/task-1 - x.md").read_text())
        self.assertIn("TASK-3", j["tasks"])  # the dependent became ready when the parent closed
        sub = (self.proj / "backlog/tasks/task-4 - sub.md").read_text()
        self.assertIn("- #1 it works".replace("- #1", "#1"), sub); self.assertIn("milestone: m-1", sub)
        self.assertIn("split", [x["step"] for x in t["ladder"]])

    def test_doctor_split_that_drops_an_ac_is_refused(self):
        self.two_acs()
        self.with_doctor({"TASK-1": [self.split_plan(acs_b=("something new",))]})
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        t = self.journal()["tasks"]["TASK-1"]
        self.assertEqual(t["state"], "blocked"); self.assertIn("invalid", t["reason"])
        self.assertFalse(list((self.proj / "backlog/tasks").glob("task-4*")))

    def test_doctor_session_that_writes_a_file_stops_the_run(self):
        self.with_doctor({"TASK-1": ["write"]})
        self.behavior({"TASK-1": "no_evidence"})
        r = self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("doctor session", self.journal()["aborted"])

    def test_doctor_without_verdict_leaves_the_old_blocking(self):
        self.with_doctor({"TASK-1": ["none"]})
        self.behavior({"TASK-1": "no_evidence"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        t = self.journal()["tasks"]["TASK-1"]
        self.assertEqual(t["state"], "blocked"); self.assertEqual(t["ladder"][0]["result"], "no verdict")

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

    def test_risk_finding_passes_the_verdict_and_becomes_a_draft_without_repair(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["risk"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.journal()["tasks"]["TASK-1"], {"state": "accepted", "repairs": 0})
        self.assertEqual(self.eval_calls(), ["TASK-1"])
        drafts = list((self.proj / "backlog/drafts").glob("draft-*"))
        self.assertEqual(len(drafts), 1); self.assertIn("1 GB input", drafts[0].read_text())
        self.tron("report", "--run-id", self.journal()["run_id"])
        self.assertIn("1 GB input", (self.proj / "docs/agent/tron" / f"REPORT-{self.journal()['run_id']}.md").read_text())

    def test_same_risk_reported_again_makes_one_draft(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["risk"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        j = self.journal(); (self.proj / "docs/agent/tron/x").mkdir(exist_ok=True)
        m = __import__("importlib.util").util.spec_from_file_location("t2", pathlib.Path(__file__).resolve().parents[2] / "scripts/tron.py")
        mod = __import__("importlib.util").util.module_from_spec(m); m.loader.exec_module(mod)
        mod.write_risk_drafts(self.proj, "TASK-1", [{"scenario": "1 GB input with one 4 MB word"}], j)
        self.assertEqual(len(list((self.proj / "backlog/drafts").glob("draft-*"))), 1)

    def test_parser_rejects_unknown_kinds_and_defect_still_fails(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("tron_mod", pathlib.Path(__file__).resolve().parents[2] / "scripts/tron.py")
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        blk = lambda d: "```json\n" + json.dumps(d) + "\n```"
        self.assertIsNone(m.parse_verdict(blk({"verdict": "pass", "findings": [{"kind": "whatever"}]}), None))
        v = m.parse_verdict(blk({"verdict": "fail", "findings": [{"kind": "risk", "scenario": "x"}]}), None)
        self.assertEqual((v["verdict"], len(v["risks"])), ("pass", 1))
        self.assertIsNone(m.parse_verdict(blk({"verdict": "fail", "findings": [{"kind": "bug"}]}) + blk({"verdict": "pass"}), None))
        v = m.parse_verdict(blk({"verdict": "fail", "findings": [{"ac": "invariant: no network", "kind": "risk"}]}), None)
        self.assertEqual((v["verdict"], v["findings"][0]["kind"]), ("fail", "invariant"))
        v = m.parse_verdict(blk({"verdict": "fail", "findings": [{"ac": "AC#1", "kind": "Risk"}]}), None)
        self.assertEqual((v["verdict"], v["findings"][0]["kind"]), ("fail", "defect"))
        v = m.parse_verdict(blk({"verdict": "pass", "findings": [{"scenario": "x"}]}), None)
        self.assertEqual((v["verdict"], v["findings"][0]["kind"]), ("fail", "defect"))
        v = m.parse_verdict(blk({"verdict": "fail", "findings": [{"kind": "risk"}, {"kind": "defect"}]}), None)
        self.assertEqual((v["verdict"], len(v["findings"]), len(v["risks"])), ("fail", 1, 1))

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

    def test_evaluator_artifacts_are_set_aside_in_a_stash_and_the_run_goes_on(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["write"]})
        r = self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        ev = [s for s in self.journal()["sessions"] if s["role"] == "evaluator"][0]["evaluator"]
        self.assertIn("artifacts_stash", ev)
        self.assertFalse((self.proj / "evaluator_wrote.txt").exists())
        self.assertEqual(self.journal()["tasks"]["TASK-1"]["state"], "accepted")

    def test_evaluator_that_changes_tracked_files_stops_the_run(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["write_tracked"]})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 4); self.assertIn("evaluator", self.journal()["aborted"])

    def test_review_parse_verdict_is_fail_closed(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import tron
        blk = lambda d: "```json\n" + json.dumps(d) + "\n```\n"
        ok = {"verdict": "pass", "findings": [], "assumption_flags": [], "checked": [{"ac": "AC#1"}]}
        self.assertEqual(tron.parse_verdict(blk(ok), ["AC#1"])["verdict"], "pass")
        self.assertEqual(tron.parse_verdict(blk(dict(ok, findings=[{"ac": "AC#1"}])))["verdict"], "fail")  # pass with findings
        self.assertIsNone(tron.parse_verdict(blk(dict(ok, findings="none"))))  # sloppy shape is no verdict
        self.assertEqual(tron.parse_verdict(blk(dict(ok, verdict="fail")) + blk(ok))["verdict"], "fail")  # a later quoted pass does not win
        self.assertEqual(tron.parse_verdict(blk(dict(ok, checked=[])), ["AC#1"])["verdict"], "fail")  # AC not checked
        self.assertEqual(tron.parse_verdict("```JSON\n" + json.dumps(ok) + "\n```")["verdict"], "pass")  # tag is optional and case-insensitive

    def test_review_label_cannot_be_removed_by_the_session_to_skip_the_evaluator(self):
        self.with_evaluator("milestone")
        f = self.proj / "backlog/tasks/task-1 - x.md"
        f.write_text(f.read_text().replace("  - size-S", "  - size-S\n  - review"))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "label")
        self.behavior({"TASK-1": "unlabel"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("TASK-1", self.eval_calls())

    def test_review_milestone_evaluation_runs_even_when_max_tasks_is_reached(self):
        self.with_evaluator("milestone")
        self.state([("TASK-1", [])]); git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "one task")
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.eval_calls(), ["milestone"]); self.assertTrue(self.journal()["complete"])

    def test_review_acceptance_scenario_is_protected(self):
        self.with_evaluator("milestone")
        (self.proj / "docs/agent/tron").mkdir(parents=True, exist_ok=True)
        (self.proj / "docs/agent/tron/ACCEPTANCE-m-1.md").write_text("scenario")
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "scenario")
        self.behavior({"TASK-1": "edit_scenario"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertIn("protected", self.checks())

    def test_review_not_verifiable_blocks_at_once_without_repairs(self):
        self.with_evaluator("task")
        self.evaluator_plan({"TASK-1": ["unverifiable"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertEqual(self.journal()["tasks"]["TASK-1"]["state"], "blocked")
        self.assertEqual(self.eval_calls(), ["TASK-1"])
        self.assertEqual(sum(1 for c in self.calls() if c["task"] == "TASK-1"), 1)

    def test_review_brief_leaves_out_implementer_notes(self):
        self.with_evaluator("task")
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        self.assertNotIn("fake evidence", (self.td / "brief_copy.txt").read_text())

    def test_review_evaluator_role_line_at_session_start(self):
        r = subprocess.run(["bash", str(ROOT / "scripts/session-start.sh")], cwd=self.tmp, capture_output=True, text=True,
                           env=dict(os.environ, STEM_OFFLINE="1", STEM_TRON="1", STEM_TRON_ROLE="evaluator"))
        self.assertIn("TRON MODE evaluator", r.stdout); self.assertNotIn("one task per session", r.stdout)

    def test_review_invalid_evaluator_config_is_rejected(self):
        self.config({"evaluator": "Task"})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 2); self.assertIn("evaluator", r.stderr)

    def test_milestone_evaluator_fail_gets_repair_sessions(self):
        self.with_evaluator("milestone", max_repairs=1)
        self.evaluator_plan({"milestone": ["fail", "fail"]})
        r = self.tron("run", "--milestone", "m-1")
        j = self.journal()
        self.assertFalse(j["complete"]); self.assertIn("milestone evaluation failed", j["stop_reason"])
        self.assertEqual(self.eval_calls(), ["milestone", "milestone"])

    def test_review_milestone_repair_that_changes_nothing_ends_the_run(self):
        self.with_evaluator("milestone", max_repairs=2)
        self.evaluator_plan({"milestone": ["fail"]}); self.behavior({"milestone": "noop"})
        r = self.tron("run", "--milestone", "m-1")
        self.assertEqual(r.returncode, 3); self.assertIn("no diff", self.journal()["aborted"])

    def sample_journal(self):
        d = self.proj / "docs/agent/tron"; d.mkdir(parents=True, exist_ok=True)
        sha = git(self.proj, "rev-parse", "HEAD").stdout.strip()
        s = lambda task, role, cost, model, repair=0: {"task": task, "role": role, "start": "2026-11-17T10:00:00Z", "end": "2026-11-17T10:05:00Z",
                                                          "exit_code": 0, "cost_usd": cost, "model": model, "repair": repair}
        j = {"run_id": "s1", "milestone": "m-1", "branch": "tron/m-1", "started": "2026-11-17T10:00:00Z", "ended": None, "complete": True,
             "stop_reason": "no ready task left", "start_commit": sha, "wall_seconds": 5400, "ac_hashes": {},
             "tasks": {"TASK-1": {"state": "accepted", "repairs": 1}, "TASK-2": {"state": "blocked", "reason": "still failing", "repairs": 2, "kept": {"branch": "tron/blocked-task-2-s1"}}},
             "sessions": [s("TASK-1", "worker", 0.4, "sonnet"), s("TASK-1", "worker", 0.3, "sonnet", 1), s("TASK-1", "evaluator", None, "opus"), s("TASK-2", "worker", 0.2, "sonnet")]}
        (d / "run-s1.json").write_text(json.dumps(j))
        (d / "verdict-s1-TASK-1-1.json").write_text(json.dumps({"target": "TASK-1", "verdict": "fail", "findings": [{"ac": "AC#1", "location": "a.py:1", "scenario": "x"}], "assumption_flags": []}))
        f = self.proj / "backlog/tasks/task-1 - x.md"
        f.write_text(f.read_text().replace("- [ ] #1", "- [x] #1").replace("<!-- SECTION:NOTES:BEGIN -->\n", "<!-- SECTION:NOTES:BEGIN -->\nAC#1: E2 test_a passes\nAssumption: CSV is fine\n"))
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "sample")

    def test_report_from_a_sample_journal(self):
        self.sample_journal()
        r = self.tron("report", "--run-id", "s1")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = (self.proj / "docs/agent/tron/REPORT-s1.md").read_text()
        for section in ("Look at this first", "Accepted tasks", "Evaluator findings", "Assumptions made", "Blocked tasks", "Open questions", "Cost and time", "Metrics"):
            self.assertIn(section, rep)
        self.assertIn("AC#1 it works (evidence: E2 test_a passes)", rep)
        self.assertIn("TASK-2: still failing", rep); self.assertIn("TASK-1: CSV is fine".replace("TASK-1: ", "TASK-1: Assumption: "), rep)
        self.assertIn("a.py:1", rep)

    def test_report_groups_assumptions_by_basis_none_first(self):
        self.sample_journal()
        f = self.proj / "backlog/tasks/task-1 - x.md"
        f.write_text(f.read_text().replace("Assumption: CSV is fine\n", "Assumption: CSV is fine (basis: none)\nAssumption: comma (basis: P-3)\nAssumption: naming (basis: frame: naming)\nAssumption: no basis at all\n"))
        self.tron("report", "--run-id", "s1")
        rep = (self.proj / "docs/agent/tron/REPORT-s1.md").read_text()
        i_none, i_p3, i_fr = rep.index("Basis: none"), rep.index("Basis: P-3"), rep.index("Basis: frame: naming")
        self.assertLess(i_none, i_p3); self.assertLess(i_none, i_fr)
        self.assertIn("needs your ruling", rep)
        self.assertLess(rep.index("CSV is fine"), i_p3); self.assertLess(rep.index("no basis at all  [no basis named]"), i_p3)

    def test_assumption_without_basis_is_a_journal_warning(self):
        self.behavior({"TASK-1": "assume_nobasis"})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        j = json.loads(next((self.proj / "docs/agent/tron").glob("run-*.json")).read_text())
        w = j["tasks"]["TASK-1"].get("warnings", [])
        self.assertEqual(len(w), 1); self.assertIn("CSV is fine", w[0]); self.assertNotIn("P-3", w[0])

    def test_report_shows_unknown_cost_never_zero_and_cost_per_role_with_models(self):
        self.sample_journal()
        self.tron("report", "--run-id", "s1")
        rep = (self.proj / "docs/agent/tron/REPORT-s1.md").read_text()
        self.assertIn("| evaluator | 1 | unknown | opus |", rep)
        self.assertIn("| worker | 3 | 0.90 USD | sonnet |", rep)
        self.assertIn("Total cost: at least 0.90 USD", rep)
        self.assertIn("Cost per accepted task: at least 0.90 USD", rep)
        self.assertIn("Blocked rate: 1 of 2", rep); self.assertIn("Repair rate: 1 repair session(s) in 3 worker session(s)", rep)

    def test_report_shows_smoke_cmd_when_preview_cmd_is_unset(self):
        self.config({"smoke_cmd": ["python3", "app.py", "--smoke"]})
        self.sample_journal()
        self.tron("report", "--run-id", "s1")
        self.assertIn("Preview start command: `python3 app.py --smoke`", (self.proj / "docs/agent/tron/REPORT-s1.md").read_text())

    def test_report_milestone_row_sums_evaluator_and_repair_sessions(self):
        self.sample_journal()
        p = self.proj / "docs/agent/tron/run-s1.json"; j = json.loads(p.read_text())
        base = j["sessions"][0]
        j["sessions"] += [dict(base, task="milestone", role="evaluator", cost_usd=0.5, model="opus"), dict(base, task="milestone", role="worker", cost_usd=0.25, model="sonnet", repair=1)]
        p.write_text(json.dumps(j))
        self.tron("report", "--run-id", "s1")
        self.assertIn("| milestone | 2 | - | 0.75 USD |", (self.proj / "docs/agent/tron/REPORT-s1.md").read_text())

    def test_worker_that_stops_without_a_diff_shows_its_own_reason(self):
        self.config({"max_repairs": 0})
        self.behavior({"TASK-1": ["note_only"]})
        self.tron("run", "--milestone", "m-1", "--max-tasks", "1")
        r = self.journal()["tasks"]["TASK-1"]["reason"]
        self.assertIn("on purpose", r); self.assertIn("need a decision", r); self.assertNotIn("no diff", r)

    def test_report_is_written_when_a_run_stops(self):
        self.tron("run", "--milestone", "m-1", "--run-id", "auto")
        self.assertTrue((self.proj / "docs/agent/tron/REPORT-auto.md").is_file())
        self.assertEqual(git(self.proj, "status", "--porcelain", "--", ".", ":!docs/agent/tron").stdout.strip(), "")

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


class Check(unittest.TestCase):
    """Readiness check: each failure on its own, plus the ready case."""
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = self.tmp / "proj"; self.proj.mkdir()
        (self.proj / "docs/agent/tron").mkdir(parents=True)
        (self.proj / "backlog/tasks").mkdir(parents=True)
        (self.proj / "docs/agent/DECISION_FRAME.md").write_text("frame\n")
        (self.proj / "docs/agent/INVARIANTS.md").write_text("inv\n")
        (self.proj / "docs/agent/tron/ACCEPTANCE-m-9.md").write_text("scenario\n")
        self.task("TASK-1")
        self.cfg()
        git(self.proj, "init", "-q", "-b", "main")
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "init")

    def task(self, tid, labels="  - size-S\n", acs="- [ ] #1 it works\n"):
        n = tid.split("-")[1]
        (self.proj / f"backlog/tasks/task-{n} - x.md").write_text(
            f"---\nid: {tid}\ntitle: t\nstatus: To Do\nlabels:\n{labels}milestone: m-9\n---\n\n<!-- AC:BEGIN -->\n{acs}<!-- AC:END -->\n")

    def cfg(self, **over):
        c = {"worker_cmd": ["claude", "--allowedTools", "Bash"], "verify_cmd": ["scripts/run.sh", "v"], "smoke_cmd": ["true"],
             "max_cost": 5, "evaluator": "off", "sweep": False}
        c.update(over)
        c = {k: v for k, v in c.items() if v is not None}
        (self.proj / "docs/agent/stem-config.json").write_text(json.dumps({"tron": c}))

    def check(self, env=None):
        e = {k: v for k, v in os.environ.items() if k not in ("IS_SANDBOX", "STEM_SANDBOX", "CLAUDE_CODE_EFFORT_LEVEL")}
        e.update(env or {})
        return subprocess.run([sys.executable, str(TRON), "check", "--milestone", "m-9", "--root", str(self.proj)], capture_output=True, text=True, env=e)

    def commit(self):
        git(self.proj, "add", "-A"); git(self.proj, "commit", "-qm", "x")

    def fails_with(self, needle, **kw):
        r = self.check(**kw)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stdout)

    def test_ready(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("READY", r.stdout); self.assertIn("start: scripts/tron.py run --milestone m-9", r.stdout)

    def test_task_without_acs(self):
        self.task("TASK-2", acs=""); self.commit(); self.fails_with("TASK-2: no acceptance criteria")

    def test_task_without_size(self):
        self.task("TASK-2", labels="  - x\n"); self.commit(); self.fails_with("TASK-2: no size label")

    def test_verify_unset(self):
        self.cfg(verify_cmd=None); self.commit(); self.fails_with("verify_cmd")

    def test_frame_and_invariants_missing(self):
        (self.proj / "docs/agent/DECISION_FRAME.md").unlink(); (self.proj / "docs/agent/INVARIANTS.md").write_text("")
        self.commit(); r = self.check()
        self.assertIn("DECISION_FRAME.md is missing", r.stdout); self.assertIn("INVARIANTS.md is missing", r.stdout)

    def test_no_limit(self):
        self.cfg(max_cost=None); self.commit(); self.fails_with("no limit configured")

    def test_no_scenario(self):
        (self.proj / "docs/agent/tron/ACCEPTANCE-m-9.md").unlink(); self.commit(); self.fails_with("acceptance scenario missing")

    def test_dirty_tree(self):
        (self.proj / "junk.txt").write_text("x"); self.fails_with("working tree is not clean")

    def test_no_sandbox_no_allowlist(self):
        if os.path.exists("/.dockerenv"):
            self.skipTest("host is a container")
        self.cfg(worker_cmd=["claude"]); self.commit(); self.fails_with("neither a sandbox nor a permission allowlist")
        r = self.check(env={"IS_SANDBOX": "1"}); self.assertEqual(r.returncode, 0, r.stdout)

    def test_no_smoke_command(self):
        self.cfg(smoke_cmd=None); self.commit(); self.fails_with("start-and-smoke")

    def sweep(self, text):
        planner = self.tmp / "planner.py"
        planner.write_text("import json, sys\nprint(json.dumps({'session_id': sys.argv[1], 'total_cost_usd': 0.2, 'result': " + json.dumps(text) + "}))\n")
        self.cfg(sweep=True, planner_cmd=[sys.executable, str(planner), "{session_id}", "{prompt}"]); self.commit()
        return subprocess.run([sys.executable, str(TRON), "sweep", "--milestone", "m-9", "--root", str(self.proj)], capture_output=True, text=True)

    def test_check_fails_while_sweep_is_missing(self):
        self.cfg(sweep=True); self.commit(); self.fails_with("question sweep missing")

    def test_sweep_writes_file_and_check_follows_open_questions(self):
        r = self.sweep("# Sweep: m-9\n## Questions\n- [ ] Q1 (TASK-1) Which format? a) csv b) json Recommendation: a because simple\n## Draft acceptance scenario\nrun it\n## Too large or not testable\n- none\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        f = self.proj / "docs/agent/tron/SWEEP-m-9.md"
        self.assertIn("Q1 (TASK-1)", f.read_text())
        self.assertIn("brief-sweep-m-9.md", "".join(p.name for p in (self.proj / "docs/agent/tron").iterdir()))
        brief = (self.proj / "docs/agent/tron/brief-sweep-m-9.md").read_text()
        self.assertIn("### TASK-1", brief); self.assertIn("AC#1: it works", brief)
        self.commit(); self.fails_with("1 unanswered question")
        f.write_text(f.read_text().replace("- [ ] Q1", "- [x] Q1") + "Answer: a\n"); self.commit()
        r = self.check(); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_sweep_without_questions_section_is_rejected(self):
        r = self.sweep("I looked and all is fine")
        self.assertEqual(r.returncode, 2); self.assertFalse((self.proj / "docs/agent/tron/SWEEP-m-9.md").exists())

    def test_answer_must_sit_under_its_own_question(self):
        q = "# Sweep: m-9\n## Questions\n- [ ] Q1 (TASK-1) a?\n- [ ] Q2 (TASK-1) b?\n## Draft acceptance scenario\nx\n"
        self.sweep(q); f = self.proj / "docs/agent/tron/SWEEP-m-9.md"
        f.write_text(f.read_text().replace("- [ ] Q1 (TASK-1) a?", "- [x] Q1 (TASK-1) a?\n  Answer: a").replace("- [ ] Q2", "- [x] Q2"))
        self.commit(); self.fails_with("1 unanswered question")  # Q2 ticked but no Answer line
        f.write_text(f.read_text().replace("- [x] Q2 (TASK-1) b?", "- [x] Q2 (TASK-1) b?\n  Answer: b")); self.commit()
        r = self.check(); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_sweep_rejects_malformed_question_line(self):
        r = self.sweep("# Sweep: m-9\n## Questions\n- [] Q1 (TASK-1) a?\n")
        self.assertEqual(r.returncode, 2); self.assertFalse((self.proj / "docs/agent/tron/SWEEP-m-9.md").exists())

    def test_sweep_does_not_overwrite_answers_without_force(self):
        ok = "# Sweep: m-9\n## Questions\n- none\n"
        self.assertEqual(self.sweep(ok).returncode, 0)
        f = self.proj / "docs/agent/tron/SWEEP-m-9.md"; f.write_text(f.read_text() + "KEEP\n")
        r = self.sweep(ok); self.assertEqual(r.returncode, 2); self.assertIn("KEEP", f.read_text())

    def test_check_warns_without_doctor_cmd(self):
        self.commit(); r = self.check()
        self.assertIn("tron.doctor_cmd is missing", r.stdout)

    def test_warnings(self):
        self.cfg(evaluator="milestone"); self.commit()
        r = self.check(env={"CLAUDE_CODE_EFFORT_LEVEL": "high"})
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("CLAUDE_CODE_EFFORT_LEVEL", r.stdout); self.assertIn("evaluator_cmd is missing", r.stdout)


if __name__ == "__main__":
    unittest.main()
