"""Maps changed files to the fixture test files stem-check must run (TASK-374). Imported by stem-check.py.
select(changed) -> set of test file names, or None = run everything (unsure). A file in no rule (text, docs) selects no test."""
import fnmatch

ALL = ("test_scripts.py", "test_retro_run.py", "test_tron.py")
TRON = ("scripts/tron.py", ".github/tests/test_tron.py", ".claude/agents/", ".claude/skills/tron/",
        "docs/agent/DECISION_FRAME.md", "docs/agent/INVARIANTS.md", "docs/agent/PRECEDENTS.md", "docs/agent/TRON.md")
RETRO = ("scripts/retro-run.py", ".github/tests/test_retro_run.py", "docs/agent/retro-topics")
SCRIPTS = ("scripts/", ".github/tests/test_scripts.py", ".github/rule-reach.py", ".github/retired-names.py", ".github/bump-version.sh",
           ".claude/settings.json", ".claude/hooks/", "docs/agent/modules/", "docs/agent/stem-config.json", "docs/agent/model-classes.json", "docker/")
EVERYTHING = (".github/stem-check.py", ".github/check_select.py", ".github/tests/shard.py", ".github/workflows/")


def select(changed):
    if changed is None: return None
    tests = set()
    for f in changed:
        if f.startswith(EVERYTHING): return None
        if f.startswith(TRON): tests.add("test_tron.py")
        if f.startswith(RETRO): tests.add("test_retro_run.py")
        if f.startswith(SCRIPTS): tests.add("test_scripts.py")
        if fnmatch.fnmatch(f, ".claude/skills/*/SKILL.md") and not f.startswith(".claude/skills/tron/"): tests.add("test_scripts.py")
    return tests
