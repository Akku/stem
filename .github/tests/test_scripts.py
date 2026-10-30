#!/usr/bin/env python3
"""Fixture tests for STEM scripts (STEM maintenance only; run by stem-check.py or directly: python3 .github/tests/test_scripts.py).
Each test builds its own sandbox repository or transcript folder in a temp dir, so nothing depends on the real project."""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def run(cmd, cwd, env=None, stdin=None):
    e = dict(os.environ, **GIT_ENV, **(env or {}))
    return subprocess.run(cmd, cwd=cwd, env=e, input=stdin, capture_output=True, text=True)


def assistant(model, tokens, sidechain=False, content=None, ts="2026-10-20T10:00:00Z"):
    return {"type": "assistant", "timestamp": ts, "isSidechain": sidechain,
            "message": {"model": model, "content": content or [], "usage": {"input_tokens": tokens, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "output_tokens": 10}}}


def write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class ContextCheck(Sandbox):
    def check(self, records, env=None):
        t = self.tmp / "t.jsonl"; write_jsonl(t, records)
        return run([sys.executable, str(SCRIPTS / "context-check.py"), "--transcript", str(t)], self.tmp, {"TMPDIR": str(self.tmp), **(env or {})})

    def test_silent_below_threshold(self):
        r = self.check([assistant("claude-sonnet-5-5", 10000), assistant("claude-sonnet-5-5", 30000)])
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_notice_above_floor_relative_threshold(self):
        # first turn 10k -> threshold 50k; current 60k
        r = self.check([assistant("claude-sonnet-5-5", 10000), assistant("claude-sonnet-5-5", 60000)])
        self.assertIn("CONTEXT NOTICE", r.stdout)
        self.assertIn("threshold 50k", r.stdout)

    def test_subagent_records_are_ignored(self):
        r = self.check([assistant("claude-sonnet-5-5", 10000), assistant("claude-sonnet-5-5", 190000, sidechain=True)])
        self.assertEqual(r.stdout, "")

    def test_unknown_model_uses_cap(self):
        low = self.check([assistant("other-model", 80000), assistant("other-model", 90000)])
        high = self.check([assistant("other-model", 80000), assistant("other-model", 110000)], env={"CONTEXT_WARN_TOKENS": "100000"})
        self.assertEqual(low.stdout, "")
        self.assertIn("threshold 100k", high.stdout)

    def test_bad_input_is_silent(self):
        r = run([sys.executable, str(SCRIPTS / "context-check.py"), "--transcript", str(self.tmp / "missing.jsonl")], self.tmp, {"TMPDIR": str(self.tmp)})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = run([sys.executable, str(SCRIPTS / "context-check.py")], self.tmp, {"TMPDIR": str(self.tmp)}, stdin="not json")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_hook_mode_repeats_only_after_step(self):
        t = self.tmp / "t.jsonl"; write_jsonl(t, [assistant("claude-sonnet-5-5", 10000), assistant("claude-sonnet-5-5", 60000)])
        hook = lambda: run([sys.executable, str(SCRIPTS / "context-check.py")], self.tmp, {"TMPDIR": str(self.tmp)}, stdin=json.dumps({"transcript_path": str(t), "session_id": "s1"})).stdout
        self.assertIn("CONTEXT NOTICE", hook())
        self.assertEqual(hook(), "")  # same size: no second notice


class ContextReport(Sandbox):
    def report(self, records, *args, cwd=None):
        d = self.tmp / "transcripts"; d.mkdir(exist_ok=True)
        write_jsonl(d / "abcdef12-session.jsonl", records)
        return run([sys.executable, str(SCRIPTS / "context-report.py"), *args, str(d)], cwd or self.tmp)

    def test_empty_folder_not_evaluable(self):
        d = self.tmp / "none"; d.mkdir()
        self.assertIn("not evaluable", run([sys.executable, str(SCRIPTS / "context-report.py"), str(d)], self.tmp).stdout)

    def test_brief_counts_turns_and_models(self):
        r = self.report([assistant("claude-sonnet-5-5", 1000), assistant("claude-sonnet-5-5", 2000)], "--brief")
        self.assertIn("sessions=1 turns=2", r.stdout)
        self.assertIn("models=claude-sonnet-5-5", r.stdout)

    def test_since_filters_old_records(self):
        r = self.report([assistant("claude-sonnet-5-5", 1000, ts="2026-01-01T00:00:00Z")], "--brief", "--since", "2026-06-01")
        self.assertIn("not evaluable", r.stdout)

    def test_rule_load_via_sed_and_skill_read_are_detected(self):
        cmd = "ID=R-VERIFY; sed -n \"/<!-- RULE:${ID}:START -->/,/<!-- RULE:${ID}:END -->/p\" docs/agent/OPERATING_MODEL.md"
        sed_only = "sed -n '/<!-- RULE:R-REVIEW:START -->/,/<!-- RULE:R-REVIEW:END -->/p' docs/agent/OPERATING_MODEL.md"
        recs = [assistant("claude-sonnet-5-5", 1000, content=[
            {"type": "tool_use", "id": "1", "name": "Bash", "input": {"command": cmd}},
            {"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": sed_only}},
            {"type": "tool_use", "id": "3", "name": "Read", "input": {"file_path": "/p/.claude/skills/retro/SKILL.md"}}])]
        r = self.report(recs)
        self.assertIn("'R-VERIFY': 1", r.stdout)
        self.assertIn("'R-REVIEW': 1", r.stdout)
        self.assertIn("'retro': 1", r.stdout)


class SandboxRepo(Sandbox):
    """A project folder with STEM scripts, a git repository and a few backlog tasks."""
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "proj"
        shutil.copytree(SCRIPTS, self.repo / "scripts", ignore=shutil.ignore_patterns("__pycache__", "local"))
        (self.repo / "backlog/tasks").mkdir(parents=True)
        run(["git", "init", "-q", "-b", "main"], self.repo)
        self.nogh = self.tmp / "bin"; self.nogh.mkdir()  # stub: no network calls from tests
        (self.nogh / "gh").write_text("#!/bin/sh\nexit 1\n"); (self.nogh / "gh").chmod(0o755)
        self.env = {"PATH": f"{self.nogh}{os.pathsep}{os.environ['PATH']}", "TMPDIR": str(self.tmp)}

    def task(self, n, status="Done", updated="2026-10-20 10:00", extra=""):
        (self.repo / f"backlog/tasks/task-{n} - T{n}.md").write_text(
            f"---\nid: TASK-{n}\ntitle: T{n}\nstatus: {status}\ncreated_date: '2026-10-01 10:00'\nupdated_date: '{updated}'\nlabels: []\n---\n\n{extra}\n")

    def commit(self, msg):
        run(["git", "add", "-A"], self.repo); return run(["git", "commit", "-qm", msg], self.repo)


class RetroMetrics(SandboxRepo):
    def test_snapshot_never_overwrites_same_day_baseline(self):
        self.task(1); self.commit("TASK-1 done")
        for _ in range(2): run(["bash", "scripts/retro-metrics.sh", "--snapshot", "2000-01-01"], self.repo, self.env)
        self.assertEqual(len(list((self.repo / "docs/agent/baselines").glob("*.txt"))), 2)

    def test_counts_tasks_and_untracked_commits(self):
        self.task(1); self.task(2, status="To Do"); self.commit("TASK-1 done")
        (self.repo / "x.txt").write_text("x"); self.commit("quick fix without id")
        out = run(["bash", "scripts/retro-metrics.sh", "2000-01-01"], self.repo, self.env).stdout
        self.assertIn("tasks: 1 done, 1 open", out)
        self.assertRegex(out, r"this repo: 2 commits, 0 handoff, 1 without task ID \(50 %\)")

    def test_since_time_applies_to_commits_and_accepted_tasks(self):
        self.task(1, updated="2026-10-23 08:00"); self.task(2, updated="2026-10-23 12:00")
        self.commit("TASK-1 done")
        out = run(["bash", "scripts/retro-metrics.sh", "2026-10-23 10:00"], self.repo, self.env).stdout
        self.assertIn("since 2026-10-23 10:00", out)
        self.assertIn("accepted tasks in period (Done, updated since 2026-10-23 10:00): 1", out)

    def test_new_process_lines(self):
        self.task(1, updated="2026-10-23 12:00"); self.task(2, status="In Progress", extra="- [ ] #1 open")
        self.commit("TASK-1/2 combined"); run(["git", "tag", "v1"], self.repo)
        out = run(["bash", "scripts/retro-metrics.sh", "2000-01-01"], self.repo, self.env).stdout
        self.assertIn("this repo: releases (tags) 1, commits with several task IDs 1", out)
        self.assertIn("task intake in period: 2 created, 1 done", out)
        self.assertIn("In Progress with unchecked criteria (possibly waiting on an outside event): TASK-2", out)
        self.assertIn("oldest open task: TASK-2, created 2026-10-01", out)

    def test_repo_option_adds_second_repository(self):
        self.task(1); self.commit("TASK-1 done")
        other = self.tmp / "product"; other.mkdir(); run(["git", "init", "-q", "-b", "main"], other)
        (other / "a").write_text("a"); run(["git", "add", "-A"], other); run(["git", "commit", "-qm", "Handoff update"], other)
        out = run(["bash", "scripts/retro-metrics.sh", "--repo", str(other), "2000-01-01"], self.repo, self.env).stdout
        self.assertRegex(out, r"repo .*product: 1 commits, 1 handoff, 1 without task ID")

    def test_duplicate_ids_reported_by_backlog_check(self):
        self.task(1); (self.repo / "backlog/tasks/task-1 - copy.md").write_text((self.repo / "backlog/tasks/task-1 - T1.md").read_text())
        r = run(["bash", "scripts/check-backlog.sh"], self.repo, self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate task id: task-1", r.stdout)


class SessionStart(SandboxRepo):
    def start(self, extra_env=None):
        return run(["bash", "scripts/session-start.sh"], self.repo, {**self.env, **(extra_env or {})}).stdout

    def test_summary_sections_without_backlog_cli_state(self):
        (self.repo / "STEM_VERSION").write_text("version: 1.0.0\n"); self.commit("init")
        out = self.start()
        for s in ("## git", "branch: main", "stem version: 1.0.0", "WARNING: pre-commit guard inactive", "## handoff", "no HANDOFF.md"):
            self.assertIn(s, out)

    def test_oversized_handoff_warns(self):
        (self.repo / "docs/agent").mkdir(parents=True); (self.repo / "docs/agent/HANDOFF.md").write_text("x" * 3000)
        self.assertIn("HANDOFF.md is over 2 KB", self.start())

    def test_handoff_version_mismatch_warns(self):
        (self.repo / "STEM_VERSION").write_text("version: 1.2.1\n"); (self.repo / "docs/agent").mkdir(parents=True)
        cases = {"State: stem 1.2.0, main @ abc": True, "State: STEM version: 1.2.1": False,
                 "State: main @ abc, no version": False, "system 1.2.0 is not stem": False}
        for text, warns in cases.items():
            (self.repo / "docs/agent/HANDOFF.md").write_text(text + "\n")
            out = self.start({"STEM_OFFLINE": "1"})
            self.assertEqual("WARNING: HANDOFF.md names stem" in out, warns, text)
        (self.repo / "docs/agent/HANDOFF.md").write_text("stem 1.2.0\n")
        self.assertIn("names stem 1.2.0 but STEM_VERSION is 1.2.1", self.start({"STEM_OFFLINE": "1"}))

    def test_retro_due_after_threshold_and_cleared_by_retro_notes(self):
        for n in (1, 2, 3): self.task(n)
        self.assertIn("RETRO DUE: 3 tasks done", self.start({"RETRO_DUE_AFTER": "3"}))
        self.assertNotIn("RETRO DUE", self.start({"RETRO_DUE_AFTER": "4"}))
        (self.repo / "docs/agent/retros").mkdir(parents=True); (self.repo / "docs/agent/retros/2026-10-25.md").write_text("retro\n")
        self.assertNotIn("RETRO DUE", self.start({"RETRO_DUE_AFTER": "3"}))  # all tasks older than the retro

    def test_first_retro_section_left_after_retro_warns(self):
        (self.repo / "docs/agent/retros").mkdir(parents=True); (self.repo / "docs/agent/NEXT_RETRO.md").write_text("# Next retro\n\n## First retro\n\n- item\n")
        self.assertNotIn("RETRO OPEN ITEMS", self.start())  # no retro notes yet: section is expected
        (self.repo / "docs/agent/retros/2026-10-25.md").write_text("retro\n")
        self.assertIn("RETRO OPEN ITEMS", self.start())
        (self.repo / "docs/agent/NEXT_RETRO.md").write_text("# Next retro\n\n## Due checks\n")
        self.assertNotIn("RETRO OPEN ITEMS", self.start())

    def test_check_backlog_problem_is_shown(self):
        self.task(1, extra="- [ ] #1 open box")
        self.assertIn("TASK-1: Done with 1 unchecked box", self.start())

    def test_offline_opt_out_skips_version_check(self):
        (self.repo / "STEM_VERSION").write_text("version: 1.0.0\nrepo: https://github.com/x/stem\n")
        marker = self.tmp / "curl-called"
        (self.nogh / "curl").write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n"); (self.nogh / "curl").chmod(0o755)
        self.start({"STEM_OFFLINE": "1"})
        self.assertFalse(marker.exists())
        self.start()
        self.assertTrue(marker.exists())  # the stub is reached without the opt-out


class PromoteCheck(SandboxRepo):
    HEAD = "| Rule / change | Hypothesis | Metric | Baseline | Check by | Confounders | Result | Grade |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n"

    def check(self, experiments, learnings=""):
        (self.repo / "docs/agent").mkdir(parents=True, exist_ok=True)
        (self.repo / "docs/agent/EXPERIMENTS.md").write_text(self.HEAD + experiments)
        (self.repo / "docs/agent/NEXT_RETRO.md").write_text(learnings)
        return run(["bash", "scripts/promote-check.sh"], self.repo, self.env)

    def test_nothing_to_promote_prints_nothing(self):
        r = self.check("| A | h | m | b | c | x | open | G0 |\n| B | h | m | b | c | x | not effective | G2 |\n| C | h | m | b | c | x | effective, promoted #12 | G2 |\n| D | h | m | b | c | x | indication | G1 |\n",
                       "- [TASK-1 / 2026-10-01] effective at G1 only\n")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_effective_g2_items_are_listed(self):
        r = self.check("| Rule E | h | m | b | c | x | effective | G2 (two projects) |\n", "- [TASK-2 / 2026-10-02] batching effective, G3 → promote\n")
        self.assertIn("promote candidate: EXPERIMENTS.md: Rule E", r.stdout)
        self.assertIn("promote candidate: NEXT_RETRO.md: - [TASK-2", r.stdout)


class PreCommit(SandboxRepo):
    def test_rename_into_blocked_file_is_rejected(self):
        run(["git", "config", "core.hooksPath", "scripts/githooks"], self.repo)
        (self.repo / "notes.txt").write_text("confidential\n" * 20); self.assertEqual(self.commit("init").returncode, 0)
        run(["git", "mv", "notes.txt", "notes.pdf"], self.repo)
        r = run(["git", "commit", "-qm", "rename"], self.repo, self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("notes.pdf", r.stderr)


    def test_secret_files_and_stripe_keys_are_rejected(self):
        run(["git", "config", "core.hooksPath", "scripts/githooks"], self.repo)
        self.assertEqual(self.commit("init").returncode, 0)
        stripe = "sk_" + "live_" + "a1B2" * 6  # split so this file does not trip the guard
        for name, text in ((".envrc", "export K=x"), ("prod.env", "K=x"), ("cfg/app.env", "K=x"), ("pay.txt", "k=" + stripe)):
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True); (self.repo / name).write_text(text + "\n")
            r = self.commit(name)
            self.assertNotEqual(r.returncode, 0, name); self.assertIn(name, r.stderr)
            run(["git", "reset", "-q"], self.repo); (self.repo / name).unlink()
        (self.repo / "prod.env.example").write_text("K=\n")
        self.assertEqual(self.commit("example").returncode, 0)

class RunWrapper(Sandbox):
    def test_python_compile_from_readonly_source_uses_log_cache(self):
        source = self.tmp / "external product"
        source.mkdir()
        module = source / "sample.py"
        module.write_text("VALUE = 42\n")
        source.chmod(0o555)
        env = dict(os.environ, PYTHONPYCACHEPREFIX="")
        env["AGENT_LOG_DIR"] = str(self.tmp / "logs with spaces")
        try:
            with self.assertRaises(PermissionError):
                (source / "write-probe").write_text("must fail")
            r = run(["bash", str(SCRIPTS / "run.sh"), "compile", sys.executable,
                     "-m", "py_compile", str(module)], self.tmp, env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(list(source.rglob("*.pyc")))
            self.assertTrue(list((self.tmp / "logs with spaces/python-cache").rglob("sample*.pyc")))
        finally:
            source.chmod(0o755)

    def test_python_cache_override_is_preserved(self):
        module = self.tmp / "custom.py"
        module.write_text("VALUE = 42\n")
        cache = self.tmp / "explicit cache"
        logs = self.tmp / "logs"
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(cache), AGENT_LOG_DIR=str(logs))
        r = run(["bash", str(SCRIPTS / "run.sh"), "compile", sys.executable,
                 "-m", "py_compile", str(module)], self.tmp, env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(list(cache.rglob("custom*.pyc")))
        self.assertFalse((logs / "python-cache").exists())

    def test_parallel_runs_with_same_label_get_own_logs(self):
        env = dict(os.environ, AGENT_LOG_DIR=str(self.tmp / "logs"))
        procs = [subprocess.Popen(["bash", str(SCRIPTS / "run.sh"), "same", "true"], env=env, stdout=subprocess.DEVNULL) for _ in range(3)]
        for p in procs: p.wait()
        self.assertEqual(len(list((self.tmp / "logs").glob("*-same-*.log"))), 3)

    def test_default_log_is_durable_ignored_and_cited(self):
        run(["git", "init", "-q"], self.tmp)
        env = {k: v for k, v in os.environ.items() if k != "AGENT_LOG_DIR"}
        r = run(["bash", str(SCRIPTS / "run.sh"), "chk", "false"], self.tmp, env)
        self.assertEqual(r.returncode, 1)
        ptr = re.search(r"^evidence: run.sh chk FAIL (\.agent-logs/\S+-chk-\d+\.log)$", r.stdout, re.M)
        self.assertTrue(ptr and (self.tmp / ptr.group(1)).is_file(), r.stdout)
        self.assertEqual(run(["git", "status", "--porcelain", "--ignored=no"], self.tmp).stdout, "")

    def test_outside_a_repo_falls_back_to_tmpdir(self):
        env = {k: v for k, v in os.environ.items() if k != "AGENT_LOG_DIR"}
        env.update(TMPDIR=str(self.tmp), GIT_CEILING_DIRECTORIES=str(self.tmp.parent))
        r = run(["bash", str(SCRIPTS / "run.sh"), "chk", "true"], self.tmp, env)
        self.assertIn("evidence: run.sh chk PASS %s/agent-logs/" % self.tmp, r.stdout)


class RetroTopics(Sandbox):
    """scripts/retro-topics.py: selection order, rotation, resumability, local overrides, bad input."""
    def setUp(self):
        super().setUp()
        run(["git", "init", "-q", "-b", "main"], self.tmp)
        (self.tmp / "docs/agent").mkdir(parents=True)
        (self.tmp / "backlog/tasks").mkdir(parents=True)
        self.topics = [
            {"id": "once-a", "kind": "once", "title": "Once A", "ask": "qa"},
            {"id": "rep-b", "kind": "repeatable", "title": "Rep B", "ask": "qb"},
            {"id": "rep-c", "kind": "repeatable", "title": "Rep C", "ask": "qc"},
            {"id": "wip", "kind": "repeatable", "title": "WIP", "ask": "qw", "signal": {"type": "status_count", "status": "In Progress", "min": 2}},
            {"id": "due12", "kind": "once", "title": "Due", "ask": "qd", "trigger": {"type": "done_total", "min": 3}},
        ]

    def catalog(self, topics=None, local=None):
        (self.tmp / "docs/agent/retro-topics.json").write_text(json.dumps({"topics": topics or self.topics}))
        if local is not None:
            (self.tmp / "docs/agent/retro-topics.local.json").write_text(json.dumps({"topics": local}))

    def task(self, n, status, updated="2026-10-20 10:00"):
        (self.tmp / f"backlog/tasks/task-{n} - x.md").write_text(f"---\nid: TASK-{n}\ntitle: x\nstatus: {status}\nupdated_date: '{updated}'\n---\n")

    def topics_of(self, *args, **kw):
        r = run([sys.executable, str(SCRIPTS / "retro-topics.py"), "--root", str(self.tmp), "--now", kw.get("now", "2026-10-30"), *args], self.tmp)
        return r, re.findall(r"^TOPIC (\S+) \[(\S+)\]", r.stdout, re.M)

    def state(self):
        return json.loads((self.tmp / "docs/agent/retro-topics-state.json").read_text())

    def test_signal_and_due_come_first_without_cap_then_fill_once(self):
        self.catalog()
        for n in (1, 2, 3): self.task(n, "Done")
        for n in (4, 5, 6): self.task(n, "In Progress")
        r, got = self.topics_of()
        self.assertEqual(got, [("due12", "due"), ("wip", "signal")])  # two forced topics, already at the fill target
        self.assertIn("3 Done tasks in total", r.stdout)
        self.assertIn("3 tasks 'In Progress'", r.stdout)

    def test_once_is_given_once_and_repeatable_waits_for_all_once(self):
        self.catalog([t for t in self.topics if t["id"] in ("once-a", "rep-b", "rep-c")])
        _, got = self.topics_of("--retro", "r1")
        self.assertEqual(got, [("once-a", "once")])  # repeatable topics wait while a once topic was not yet given
        _, got = self.topics_of("--retro", "r2", now="2026-10-31")
        self.assertEqual(got, [("rep-b", "rotation"), ("rep-c", "rotation")])
        _, got = self.topics_of("--retro", "r3", now="2026-11-01")
        self.assertNotIn("once-a", [g[0] for g in got])  # never again
        self.assertEqual(len(self.state()["runs"]), 3)

    def test_rotation_prefers_longest_ago(self):
        self.catalog([t for t in self.topics if t["id"] in ("rep-b", "rep-c")])
        self.topics_of("--retro", "r1", "--fill", "1")
        _, got = self.topics_of("--retro", "r2", "--fill", "1", now="2026-10-31")
        self.assertEqual(got, [("rep-c", "rotation")])  # rep-b ran first, so rep-c is next
        _, got = self.topics_of("--retro", "r3", "--fill", "1", now="2026-11-01")
        self.assertEqual(got, [("rep-b", "rotation")])

    def test_same_retro_label_repeats_the_answer(self):
        self.catalog()
        _, first = self.topics_of("--retro", "r1")
        r, again = self.topics_of("--retro", "r1")
        self.assertEqual([g[0] for g in first], [g[0] for g in again])
        self.assertIn("already given", r.stdout)
        self.assertEqual(len(self.state()["runs"]), 1)

    def test_dry_run_records_nothing(self):
        self.catalog()
        self.topics_of("--dry-run")
        self.assertFalse((self.tmp / "docs/agent/retro-topics-state.json").exists())

    def test_signal_not_repeated_in_consecutive_retros(self):
        self.catalog([t for t in self.topics if t["id"] == "wip"])
        for n in (4, 5, 6): self.task(n, "In Progress")
        self.assertEqual(self.topics_of("--retro", "r1")[1], [("wip", "signal")])
        self.assertEqual(self.topics_of("--retro", "r2", now="2026-10-31")[1], [])  # cooldown of one retro
        self.assertEqual(self.topics_of("--retro", "r3", now="2026-11-01")[1], [("wip", "signal")])

    def test_below_threshold_gives_no_signal(self):
        self.catalog([t for t in self.topics if t["id"] == "wip"])
        self.task(4, "In Progress"); self.task(5, "In Progress")  # exactly the threshold: not "more than"
        r, got = self.topics_of()
        self.assertEqual(got, [("wip", "rotation")])  # only as rotation filler
        self.assertIn("rotation", r.stdout)

    def test_local_catalog_adds_replaces_and_disables(self):
        self.catalog(local=[{"id": "rep-b", "disabled": True},
                            {"id": "wip", "kind": "repeatable", "title": "WIP local", "ask": "q", "signal": {"type": "status_count", "status": "In Progress", "min": 0}},
                            {"id": "mine", "kind": "once", "title": "Mine", "ask": "q", "trigger": {"type": "done_total", "min": 1}}])
        self.task(1, "Done"); self.task(2, "In Progress")
        r, got = self.topics_of("--fill", "0")
        self.assertEqual({g[0] for g in got}, {"due12", "mine", "wip"} - {"due12"})
        self.assertIn("WIP local", r.stdout)
        self.assertNotIn("rep-b", r.stdout)

    def test_done_since_commit_trigger(self):
        self.catalog([{"id": "audit", "kind": "once", "title": "Audit", "ask": "q", "trigger": {"type": "done_since_commit", "commit": "HEAD", "min": 2}}])
        (self.tmp / "f").write_text("x"); run(["git", "add", "."], self.tmp)
        run(["git", "commit", "-qm", "base"], self.tmp, {"GIT_COMMITTER_DATE": "2026-10-10T10:00:00", "GIT_AUTHOR_DATE": "2026-10-10T10:00:00"})
        self.task(1, "Done", "2026-10-09 10:00")  # before the commit: not counted
        self.task(2, "Done", "2026-10-12 10:00")
        self.assertEqual(self.topics_of("--dry-run")[1], [])
        self.task(3, "Done", "2026-10-13 10:00")
        self.assertEqual(self.topics_of("--dry-run")[1], [("audit", "due")])

    def test_file_pct_and_growth_signals(self):
        (self.tmp / "AGENTS.md").write_text("x" * 95)
        self.catalog([{"id": "dup", "kind": "repeatable", "title": "Dup", "ask": "q", "signal": {"type": "file_pct", "path": "AGENTS.md", "limit_bytes": 100, "min_pct": 90}},
                      {"id": "grow", "kind": "repeatable", "title": "Grow", "ask": "q", "signal": {"type": "files_growth", "paths": ["AGENTS.md"], "min_pct": 20}}])
        r, got = self.topics_of("--retro", "r1", "--fill", "0")
        self.assertEqual(got, [("dup", "signal")])  # growth has no earlier record, so no signal
        (self.tmp / "AGENTS.md").write_text("x" * 130)
        self.state_sizes = self.topics_of("--retro", "r2", "--fill", "2", now="2026-10-31")  # records sizes of rotation picks
        self.assertEqual(self.state()["sizes"].get("grow", {}).get("AGENTS.md"), 130)
        (self.tmp / "AGENTS.md").write_text("x" * 200)
        self.topics_of("--retro", "r3", "--fill", "0", now="2026-11-01")  # cooldown retro: grow was given in r2
        _, got = self.topics_of("--retro", "r4", "--fill", "0", now="2026-11-02")
        self.assertIn(("grow", "signal"), got)

    def test_bad_catalog_and_state_fail_with_exit_2(self):
        r, _ = self.topics_of()
        self.assertEqual((r.returncode, "catalog missing" in r.stderr), (2, True))
        self.catalog([{"id": "x", "kind": "sometimes", "title": "t", "ask": "q"}])
        self.assertIn("kind must be", self.topics_of()[0].stderr)
        self.catalog([{"id": "x", "kind": "once", "title": "t", "ask": "q", "signal": {"type": "nope"}}])
        self.assertIn("unknown signal type", self.topics_of()[0].stderr)
        self.catalog()
        (self.tmp / "docs/agent/retro-topics-state.json").write_text("{broken")
        r = self.topics_of()[0]
        self.assertEqual((r.returncode, "not valid JSON" in r.stderr), (2, True))

    def test_days_signal_needs_a_first_run_and_finished_milestones_are_not_starved(self):
        self.catalog([{"id": "d", "kind": "repeatable", "title": "D", "ask": "q", "signal": {"type": "days_since_topic", "min": 5}},
                      {"id": "vis", "kind": "repeatable", "title": "V", "ask": "q", "signal": {"type": "vision", "max_age_days": 9999}}])
        (self.tmp / "backlog/docs").mkdir(); (self.tmp / "backlog/docs/doc-1 - Vision.md").write_text("v")
        (self.tmp / "backlog/milestones").mkdir()
        (self.tmp / "backlog/milestones/m-0.md").write_text("---\nid: m-0\n---\n")
        (self.tmp / "backlog/milestones/m-1.md").write_text("---\nid: m-1\n---\n")
        for n, st, ms in ((1, "Done", "m-0"), (2, "In Progress", "m-1")):
            (self.tmp / f"backlog/tasks/task-{n} - x.md").write_text(f"---\nid: TASK-{n}\nstatus: {st}\nmilestone: {ms}\nupdated_date: '2026-10-01 10:00'\n---\n")
        run(["git", "add", "."], self.tmp); run(["git", "commit", "-qm", "v"], self.tmp)
        r, got = self.topics_of("--retro", "r1", "--fill", "0")
        self.assertEqual(got, [("vis", "signal")])  # d has no clock yet; only m-1 lacks To Do tasks
        self.assertIn("m-1", r.stdout); self.assertNotIn("m-0", r.stdout)
        _, got = self.topics_of("--retro", "r2", "--fill", "0", now="2026-10-31")
        self.assertEqual(got, [])
        _, got = self.topics_of("--retro", "r3", "--fill", "2", now="2026-11-01")
        self.assertEqual(got, [("vis", "signal"), ("d", "rotation")])  # signal first, then the never-given topic by rotation

    def test_shipped_catalog_is_valid_and_has_reasons(self):
        shutil.copy(ROOT / "docs/agent/retro-topics.json", self.tmp / "docs/agent/retro-topics.json")
        r, got = self.topics_of("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((ROOT / "docs/agent/retro-topics.json").read_text())["topics"]
        self.assertGreaterEqual(len(data), 10)
        self.assertTrue(all(t.get("why") for t in data), "every threshold needs a documented reason")


class RetiredNames(Sandbox):
    def check(self, root):
        return run([sys.executable, str(ROOT / ".github/retired-names.py"), str(root)], self.tmp)

    def test_current_product_passes(self):
        self.assertEqual(self.check(ROOT).returncode, 0)

    def test_planted_reference_fails_with_file_line(self):
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs/a.md").write_text("ok\nsee LEARNINGS.md and kit-update\n")
        (self.tmp / "CHANGELOG.md").write_text("renamed KIT_VERSION\n")  # history may keep old names
        (self.tmp / "b.md").write_text("design-alignments and my-kit-check-x are other words\n")
        r = self.check(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("docs/a.md:2: LEARNINGS.md", r.stdout)
        self.assertIn("docs/a.md:2: kit-update", r.stdout)
        self.assertNotIn("CHANGELOG", r.stdout)
        self.assertNotIn("b.md", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
