#!/usr/bin/env python3
"""Fixture tests of scripts/retro-run.py (guided retro run: step sets per stage, evidence checks, waivers, resume). Run: python3 .github/tests/test_retro_run.py"""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def run(cmd, cwd, env=None, stdin=None):
    e = dict(os.environ, **GIT_ENV, **(env or {}))
    return subprocess.run(cmd, cwd=cwd, env=e, input=stdin, capture_output=True, text=True)


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class RetroRun(Sandbox):
    """scripts/retro-run.py: step sets per stage, version evidence, evidence checks, waivers, resume with changed requirements."""
    def setUp(self):
        super().setUp()
        for rel in ("docs/agent/retro-steps.json",):
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        steps = {"steps": [
            {"id": "v", "title": "version", "stage": "base", "kind": "version", "skill": ["retro/SKILL.md"]},
            {"id": "t", "title": "tech", "stage": "base", "kind": "tech", "command": ["python3", "-c", "print('metrics ok')"]},
            {"id": "a", "title": "analysis", "stage": "base", "kind": "analysis", "skill": ["retro/SKILL.md"]},
            {"id": "f", "title": "full only", "stage": "full", "kind": "analysis"},
            {"id": "m", "title": "milestone", "stage": "full", "when": "milestone-completed", "kind": "analysis"},
            {"id": "x", "title": "first only", "stage": "first", "kind": "analysis"}]}
        (self.tmp / "docs/agent/retro-steps.json").write_text(json.dumps(steps))
        (self.tmp / ".claude/skills/retro").mkdir(parents=True)
        (self.tmp / ".claude/skills/retro/SKILL.md").write_text("v1")
        (self.tmp / "STEM_VERSION").write_text("version: 1.0.0\nrepo: https://example.invalid/stem\n")
        (self.tmp / "remote").write_text("version: 1.0.0\n")
        self.env = {"STEM_RETRO_VERSION_URL": (self.tmp / "remote").as_uri(), "AGENT_LOG_DIR": str(self.tmp / "logs")}
        self.env.pop("STEM_OFFLINE", None)

    def rr(self, *args, env=None, stdin=None, now="2026-10-30T10:00:00Z"):
        e = {**self.env, **(env or {})}
        return run([sys.executable, str(SCRIPTS / "retro-run.py"), "--root", str(self.tmp), "--now", now, *args], self.tmp, e, stdin)

    def data(self):
        return json.loads((self.tmp / "docs/agent/retro-runs/2026-10-30.json").read_text())["steps"]

    def data_of(self, label):
        return json.loads((self.tmp / f"docs/agent/retro-runs/{label}.json").read_text())["steps"]

    def finish_all(self):
        self.assertEqual(self.rr("version-check").returncode, 0)
        self.assertEqual(self.rr("run", "t").returncode, 0)
        self.assertEqual(self.rr("done", "a", "--evidence", "three silent inefficiencies found, see task", "--ref", "TASK-1").returncode, 0)

    def test_light_full_first_step_sets(self):
        self.rr("start", "--not-first")
        self.assertEqual({k for k, s in self.data().items() if s["applies"]}, {"v", "t", "a"})
        self.assertIn("light stage", self.data()["f"]["reason"])
        self.rr("start", "--stage", "full", "--first", "--label", "b")
        d = json.loads((self.tmp / "docs/agent/retro-runs/b.json").read_text())["steps"]
        self.assertEqual({k for k, s in d.items() if s["applies"]}, {"v", "t", "a", "f", "x"})
        self.assertEqual(d["m"]["status"], "not-applicable")  # rule-based, not a waiver
        self.rr("start", "--stage", "full", "--not-first", "--flag", "milestone-completed", "--label", "c")
        d = json.loads((self.tmp / "docs/agent/retro-runs/c.json").read_text())["steps"]
        self.assertTrue(d["m"]["applies"] and not d["x"]["applies"])

    def test_first_is_detected_from_missing_retro_notes(self):
        self.rr("start")
        self.assertTrue(self.data()["x"]["applies"])

    def test_skipped_version_check_blocks_finish(self):
        self.rr("start", "--not-first")
        self.assertEqual(self.rr("run", "t").returncode, 0)
        self.rr("done", "a", "--evidence", "three silent inefficiencies found, see task", "--ref", "TASK-1")
        r = self.rr("finish")
        self.assertEqual(r.returncode, 1); self.assertIn("v=open", r.stdout)

    def test_offline_is_blocked_not_current(self):
        self.rr("start", "--not-first")
        r = self.rr("version-check", env={"STEM_OFFLINE": "1"})
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.data()["v"]["status"], "blocked")
        self.assertIn("not current", self.data()["v"]["evidence"] + r.stdout)
        self.assertEqual(self.rr("finish").returncode, 1)

    def test_unreachable_source_is_blocked_with_error_state(self):
        self.rr("start", "--not-first")
        r = self.rr("version-check", env={"STEM_RETRO_VERSION_URL": (self.tmp / "nope").as_uri()})
        self.assertEqual(r.returncode, 1)
        rec = json.loads((self.tmp / "docs/agent/retro-runs/2026-10-30.json").read_text())["version_check"]
        self.assertEqual(rec["status"], "blocked"); self.assertTrue(rec["error"]); self.assertTrue(rec["source"])

    def test_newer_version_needs_author_choice_and_updates_nothing(self):
        (self.tmp / "remote").write_text("version: 1.1.0\n")
        self.rr("start", "--not-first")
        self.assertEqual(self.rr("version-check").returncode, 0)
        self.assertEqual(self.data()["v"]["status"], "needs-decision")
        self.rr("run", "t"); self.rr("done", "a", "--evidence", "three silent inefficiencies found, see task", "--ref", "T")
        self.assertEqual(self.rr("finish").returncode, 1)
        self.assertEqual(self.rr("decide", "--choice", "keep").returncode, 2)  # a note is required
        self.assertEqual(self.rr("decide", "--choice", "keep", "--note", "author: finish retro first").returncode, 0)
        self.assertEqual(self.rr("finish").returncode, 0)
        self.assertEqual((self.tmp / "STEM_VERSION").read_text(), "version: 1.0.0\nrepo: https://example.invalid/stem\n")

    def test_complete_run_and_weak_evidence_rejected(self):
        self.rr("start", "--not-first")
        self.assertEqual(self.rr("done", "a", "--evidence", "ja", "--ref", "x").returncode, 2)
        self.assertEqual(self.rr("done", "a", "--evidence", "three silent inefficiencies found, see task").returncode, 2)  # no ref
        self.assertEqual(self.rr("done", "t", "--evidence", "all fine here, honestly yes", "--ref", "x").returncode, 2)  # tech must run
        self.finish_all()
        r = self.rr("finish")
        self.assertEqual(r.returncode, 0); self.assertIn("COMPLETE", r.stdout); self.assertNotIn("EXCEPTIONS", r.stdout)

    def test_failing_tech_step_is_blocked(self):
        steps = json.loads((self.tmp / "docs/agent/retro-steps.json").read_text())
        steps["steps"][1]["command"] = ["python3", "-c", "import sys; sys.exit(3)"]
        (self.tmp / "docs/agent/retro-steps.json").write_text(json.dumps(steps))
        self.rr("start", "--not-first")
        self.assertEqual(self.rr("run", "t").returncode, 1)
        self.assertEqual(self.data()["t"]["status"], "blocked"); self.assertEqual(self.data()["t"]["exit"], 3)

    def transcripts(self):
        d = self.tmp / "tr"; (d / "s1" / "subagents").mkdir(parents=True)
        def turn(ts, tools=0):
            return {"type": "assistant", "timestamp": ts, "isSidechain": False, "message": {"model": "m", "usage": {"cache_read_input_tokens": 100, "output_tokens": 7},
                    "content": [{"type": "tool_use", "id": str(i), "name": "Read", "input": {}} for i in range(tools)]}}
        (d / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in (turn("2026-10-30T09:59:00Z", 1), turn("2026-10-30T10:10:00Z", 2), turn("2026-10-30T10:20:00Z"), turn("2026-10-30T10:31:00Z", 1))) + "\n")
        (d / "s1" / "subagents" / "agent-1.jsonl").write_text(json.dumps(turn("2026-10-30T10:15:00Z", 5)) + "\n")
        return d

    def test_finish_stores_cost_of_the_run_window_and_result(self):
        self.rr("start", "--not-first"); self.finish_all()
        r = self.rr("finish", "--adopted", "0", "--signals", "0", now="2026-10-30T10:30:00Z", env={"RETRO_TRANSCRIPT_DIR": str(self.transcripts())})
        self.assertEqual(r.returncode, 0)
        self.assertIn("cost: stage=light turns=2 tool_calls=2 cache_read=200 output=14 (window 2026-10-30T10:00:00Z .. 2026-10-30T10:30:00Z)", r.stdout)
        self.assertIn("result: adopted=0 open_signals=0", r.stdout)
        run_json = json.loads((self.tmp / "docs/agent/retro-runs/2026-10-30.json").read_text())
        self.assertEqual(run_json["cost"], {"stage": "light", "turns": 2, "tool_calls": 2, "cache_read": 200, "output": 14})
        self.assertEqual((run_json["created"], run_json["finished"], run_json["result"]), ("2026-10-30T10:00:00Z", "2026-10-30T10:30:00Z", {"adopted": 0, "open_signals": 0}))

    def test_finish_without_result_or_transcripts_says_so(self):
        self.rr("start", "--not-first"); self.finish_all()
        r = self.rr("finish", env={"RETRO_TRANSCRIPT_DIR": str(self.tmp / "none")})
        self.assertEqual(r.returncode, 0)
        self.assertIn("cost: stage=light not evaluable", r.stdout); self.assertIn("result: not recorded", r.stdout)
        self.assertNotIn("result", json.loads((self.tmp / "docs/agent/retro-runs/2026-10-30.json").read_text()))

    def test_waive_needs_the_authors_words(self):
        self.rr("start", "--not-first"); self.rr("start", "--stage", "full", "--not-first", "--label", "w")
        self.assertEqual(self.rr("waive", "f", "--reason", "no time", "--label", "w").returncode, 2)  # no author quote
        self.assertEqual(self.rr("waive", "f", "--author-said", "no", "--label", "w").returncode, 2)  # no reason
        self.assertEqual(self.rr("waive", "f", "--reason", "no time", "--author-said", "a) skip it", "--label", "w").returncode, 0)
        w = self.data_of("w")["f"]["waiver"]
        self.assertEqual((w["author_said"], w["reason"]), ("a) skip it", "no time"))
        self.rr("version-check", "--label", "w"); self.rr("run", "t", "--label", "w")
        self.rr("done", "a", "--label", "w", "--evidence", "three silent inefficiencies found, see task", "--ref", "T")
        r = self.rr("finish", "--label", "w")
        self.assertEqual(r.returncode, 0); self.assertIn("COMPLETE-WITH-EXCEPTIONS", r.stdout)

    def test_resume_keeps_progress_and_detects_changed_skill(self):
        self.rr("start", "--not-first"); self.finish_all()
        r = self.rr("status")
        self.assertIn("next: finish", r.stdout); self.assertNotIn("CHANGED", r.stdout)
        (self.tmp / ".claude/skills/retro/SKILL.md").write_text("v2 changed")
        r = self.rr("status")
        self.assertIn("CHANGED REQUIREMENTS", r.stdout)
        d = self.data()
        self.assertEqual({k for k, s in d.items() if s["status"] == "stale"}, {"v", "a"})  # steps naming the skill; t keeps its evidence
        self.assertEqual(d["t"]["status"], "done"); self.assertEqual(d["a"]["previous"]["status"], "done")
        self.assertEqual(self.rr("finish").returncode, 1)
        self.assertEqual(self.rr("revalidate", "--note", "wording only").returncode, 2)  # needs the author's words
        self.assertEqual(self.rr("revalidate", "--note", "wording only", "--author-said", "ok, still valid").returncode, 0)
        self.assertEqual(self.data()["a"]["revalidated"]["author_said"], "ok, still valid")
        self.assertEqual(self.rr("finish").returncode, 0)

    def test_only_the_referenced_skill_section_invalidates_evidence(self):
        steps = json.loads((self.tmp / "docs/agent/retro-steps.json").read_text())
        for st in steps["steps"]:
            if st["id"] in ("v", "a"): st["ref"] = "retro#" + ("alpha" if st["id"] == "v" else "beta-part")
        (self.tmp / "docs/agent/retro-steps.json").write_text(json.dumps(steps))
        skill = self.tmp / ".claude/skills/retro/SKILL.md"
        skill.write_text("intro\n## Alpha\nfirst\n## Beta part\nsecond\n## Gamma\nthird\n")
        self.rr("start", "--not-first"); self.finish_all()
        skill.write_text("intro changed\n## Alpha\nfirst\n## Beta part\nsecond\n## Gamma\nthird changed\n")
        self.rr("status")
        self.assertEqual({k for k, s in self.data().items() if s["status"] == "stale"}, set())  # preamble and unrelated section
        skill.write_text("intro changed\n## Alpha\nfirst edited\n## Beta part\nsecond\n## Gamma\nthird changed\n")
        self.rr("status")
        self.assertEqual({k for k, s in self.data().items() if s["status"] == "stale"}, {"v"})  # only the step referencing Alpha
        skill.write_text("intro\n## Alpha renamed\nfirst edited\n## Beta part\nsecond\n")
        self.rr("status")
        self.assertIn("a", {k for k, s in self.data().items() if s["status"] == "done"})
        self.assertEqual(self.data()["v"]["files"]["retro/SKILL.md"], "nosection")  # a vanished section never looks unchanged

    def test_shipped_steps_are_valid_and_cover_skill_stage_files(self):
        shutil.copy(ROOT / "docs/agent/retro-steps.json", self.tmp / "docs/agent/retro-steps.json")
        shutil.copytree(ROOT / ".claude/skills/retro", self.tmp / ".claude/skills/retro", dirs_exist_ok=True)
        shutil.copytree(ROOT / ".claude/skills/stem-update", self.tmp / ".claude/skills/stem-update")
        self.assertEqual(self.rr("start", "--stage", "full", "--first").returncode, 0)
        d = self.data()
        self.assertTrue(d["stem-version"]["applies"])  # the version check is a base step, so light retros include it
        self.assertEqual(sum(s["status"] == "not-applicable" for s in d.values()), 1)  # milestone-check without its flag
        for s in json.loads((ROOT / "docs/agent/retro-steps.json").read_text())["steps"]:  # every ref names a real heading
            f, _, anchor = s["ref"].partition("#")
            text = (ROOT / ".claude/skills/retro" / (f + ".md" if f != "retro" else "SKILL.md")).read_text()
            slugs = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}
            self.assertIn(anchor, slugs, s["id"])
        self.assertTrue(all(s["files"] and not {"missing", "nosection"} & set(s["files"].values()) for s in d.values() if s["files"] != {}))




class RetroRunSince(Sandbox):
    """TASK-114: the metrics step gets the newest retro notes' commit time as since-time."""
    def setUp(self):
        super().setUp()
        (self.tmp / "docs/agent/retros").mkdir(parents=True)
        steps = {"steps": [{"id": "m", "title": "metrics", "stage": "base", "kind": "tech", "since": "last-retro", "value_flags": ["--repo"],
                            "command": ["python3", "-c", "import sys; print('ARGS', sys.argv[1:])"]}]}
        (self.tmp / "docs/agent/retro-steps.json").write_text(json.dumps(steps))
        (self.tmp / "STEM_VERSION").write_text("version: 1.0.0\n")
        run(["git", "init", "-q", "-b", "main"], self.tmp)
        self.env = {"AGENT_LOG_DIR": str(self.tmp / "logs"), "TZ": "Europe/Berlin", "STEM_OFFLINE": "1"}

    def rr(self, *args):
        return run([sys.executable, str(SCRIPTS / "retro-run.py"), "--root", str(self.tmp), "--now", "2026-11-01T10:00:00Z", *args], self.tmp, self.env)

    def commit_notes(self, name, date):
        (self.tmp / f"docs/agent/retros/{name}").write_text("notes\n")
        run(["git", "add", "-A"], self.tmp)
        run(["git", "commit", "-qm", name], self.tmp, {**self.env, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date})

    def test_first_retro_keeps_command_default(self):
        self.rr("start", "--first")
        self.assertIn("ARGS []", self.rr("run", "m").stdout)

    def test_newest_retro_commit_time_is_passed_in_local_time(self):
        self.commit_notes("2026-10-25.md", "2026-10-25T20:00:00Z")
        self.commit_notes("2026-10-30.md", "2026-10-30T22:57:00Z")  # 23:57 in Berlin (CET)
        (self.tmp / "docs/agent/retros/2026-11-01.md").write_text("current, not committed\n")
        self.rr("start", "--not-first")
        out = self.rr("run", "m", "--arg=--repo", "--arg", "../stem").stdout
        self.assertIn("ARGS ['--repo', '../stem', '2026-10-30 23:57']", out)

    def test_explicit_since_wins(self):
        self.commit_notes("2026-10-30.md", "2026-10-30T22:57:00Z")
        self.rr("start", "--not-first")
        self.assertIn("ARGS ['2026-10-31']", self.rr("run", "m", "--arg", "2026-10-31").stdout)

if __name__ == "__main__":
    unittest.main()
