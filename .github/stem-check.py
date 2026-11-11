#!/usr/bin/env python3
"""STEM self-check (STEM maintenance only; removed from projects by SETUP.md).
Checks rule markers, rule index, script syntax, script fixture tests, skill frontmatter, JSON and version consistency."""
import json, re, subprocess, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
errors = []
def err(m): errors.append(m)

# rules: markers balanced, index covers rules
for f in ("docs/agent/OPERATING_MODEL.md", "docs/agent/ADVANCED.md"):
    t = (root / f).read_text()
    starts = re.findall(r"<!-- RULE:(R-[A-Z-]+):START -->", t)
    ends = re.findall(r"<!-- RULE:(R-[A-Z-]+):END -->", t)
    if starts != ends: err(f"{f}: START/END markers differ")
    if len(set(starts)) != len(starts): err(f"{f}: duplicate rule IDs")
    idx = re.search(r"<!-- RULE:R-INDEX:START -->(.*?)<!-- RULE:R-INDEX:END -->", t, re.S)
    table = idx.group(1) if idx else re.search(r"\| Rule ID.*?\n\n", t, re.S).group(0)
    indexed = set(re.findall(r"\| `(R-[A-Z-]+)` \|", table))
    rules = set(starts) - {"R-INDEX"}
    if indexed != rules: err(f"{f}: index mismatch: {sorted(indexed ^ rules)}")

# shell scripts parse
for s in list((root / "scripts").glob("*.sh")) + [root / "scripts/githooks/pre-commit", root / ".github/bump-version.sh"]:
    if subprocess.run(["bash", "-n", str(s)]).returncode: err(f"{s.name}: bash syntax error")

for s in (root / "scripts").glob("*.py"):
    if subprocess.run([sys.executable, "-m", "py_compile", str(s)]).returncode: err(f"{s.name}: python syntax error")

# JSON
for j in (root / ".claude/settings.json",):
    try: json.loads(j.read_text())
    except Exception as e: err(f"{j.name}: {e}")

# skills/agents frontmatter
for d in (root / ".claude/skills").iterdir():
    m = re.match(r"---\nname: (.+)\ndescription: .+\n---", (d / "SKILL.md").read_text())
    if not m or m.group(1) != d.name: err(f"skill {d.name}: bad frontmatter/name")
for a in (root / ".claude/agents").glob("*.md"):
    if not re.match(r"---\n(?:.*\n)*?name: " + a.stem, a.read_text()): err(f"agent {a.name}: bad frontmatter/name")

# version consistency
v = re.search(r"^version: (\S+)", (root / "STEM_VERSION").read_text(), re.M).group(1)
for f in ("README.md", "README.de.md", "START_HERE.md", "STARTE_HIER.md"):
    if f"**Version {v}**" not in (root / f).read_text(): err(f"{f}: version != {v}")
if not re.search(r"^## " + re.escape(v) + r"$", (root / "CHANGELOG.md").read_text(), re.M): err(f"CHANGELOG.md: no entry for {v}")

# SETUP.md exists and the hidden paths it checks are really in STEM
if not (root / "SETUP.md").exists(): err("SETUP.md missing")
else:  # step 8: the setup commit comes after every final change, so the starting state is fully committed
    s8 = re.search(r"^## 8\..*?(?=^## )", (root / "SETUP.md").read_text(), re.S | re.M)
    s8 = s8.group(0) if s8 else ""
    pos = lambda p: s8.find(p) if p in s8 else -1
    commit = pos('Commit "Set up agentic harness"')
    for p in ("`Model:` line", "to `DONE`", "delete `SETUP.md`"):
        if pos(p) < 0 or commit < 0 or pos(p) > commit: err(f"SETUP.md step 8: '{p}' must come before the setup commit")
for f in ("docs/agent/EXPERIMENTS.md", "docs/agent/NEXT_RETRO.md"):
    if not (root / f).exists(): err(f"{f} missing")
for pth in (".claude/skills", ".claude/settings.json", ".github", ".gitignore", "scripts/githooks/pre-commit", "scripts/githooks/commit-msg"):
    if not (root / pth).exists(): err(f"{pth} missing (SETUP.md step 0 expects it)")

# Codex skill path: link to the Claude skills (one source for skill text); symlink or git's text-file fallback
for rel in (".agents/skills", ".deutschlandgpt/skills"):  # Codex, DeutschlandGPT Code
    link = root / rel
    ok_link = link.is_symlink() and link.resolve() == (root / ".claude/skills").resolve()
    ok_fallback = link.is_file() and link.read_text().strip() == "../.claude/skills"  # git on Windows without symlink support writes the target as text
    if not (ok_link or ok_fallback): err(f"{rel} must be a symlink to ../.claude/skills")
# DeutschlandGPT Code adapter: read every turn, so it stays a pointer to AGENTS.md
dg = root / "dgpt.md"
if not dg.exists() or "`AGENTS.md`" not in dg.read_text() or len(dg.read_bytes()) > 1536: err("dgpt.md must exist, point to AGENTS.md and stay under 1.5 KB")

# AGENTS.md is loaded in every session: keep it within budget; settings deny secrets
if len((root / "AGENTS.md").read_bytes()) > 7680: err("AGENTS.md exceeds the 7.5 KB budget (move rules to OPERATING_MODEL.md)")
handoff = root / "docs/agent/HANDOFF.md"
if handoff.exists() and len(handoff.read_bytes()) > 2048: err("docs/agent/HANDOFF.md exceeds 2 KB (rewrite it, handoff skill)")
st = json.loads((root / ".claude/settings.json").read_text())
if "Read(./.env)" not in st.get("permissions", {}).get("deny", []): err("settings.json: deny rule for .env missing")
for rule in ("Bash(git reset --hard:*)", "Bash(git clean *-f*)", "Bash(git commit *--no-verify*)", "Bash(git push *--no-verify*)"):
    if rule not in st.get("permissions", {}).get("deny", []): err(f"settings.json: deny rule {rule} missing")

# skills listed in AGENTS.md exist
agents = (root / "AGENTS.md").read_text()
for d in (root / ".claude/skills").iterdir():
    if f"`{d.name}`" not in agents: err(f"AGENTS.md does not mention skill {d.name}")

# README inventories list exactly the shipped skills and agents
shipped = {"skills": {d.name for d in (root / ".claude/skills").iterdir() if d.is_dir()},
           "agents": {a.stem for a in (root / ".claude/agents").glob("*.md")}}
for f in ("README.md", "README.de.md"):
    t = (root / f).read_text()
    for kind, names in shipped.items():
        row = re.search(r"^\| `\.claude/" + kind + r"/` \|(.*)$", t, re.M)
        listed = set(re.findall(r"`([a-z0-9-]+)`", row.group(1))) if row else set()
        if listed != names: err(f"{f}: .claude/{kind}/ row differs from shipped files: {sorted(listed ^ names)}")

# retired names (.github/retired-names.py): a rename leaves no old references behind
rn = subprocess.run([sys.executable, str(root / ".github/retired-names.py"), str(root)], capture_output=True, text=True)
if rn.returncode: err(rn.stdout.strip())

# every rule is named outside the rule files (.github/rule-reach.py, TASK-210)
rr = subprocess.run([sys.executable, str(root / ".github/rule-reach.py"), str(root)], capture_output=True, text=True)
if rr.returncode: err(rr.stdout.strip())

# fixture tests for the scripts (.github/tests/test_scripts.py)
tr = subprocess.run([sys.executable, str(root / ".github/tests/test_scripts.py")], capture_output=True, text=True)
if tr.returncode: err("script fixture tests failed:\n" + "\n".join(tr.stderr.strip().splitlines()[-15:]))
rr = subprocess.run([sys.executable, str(root / ".github/tests/test_retro_run.py")], capture_output=True, text=True)
if rr.returncode: err("retro-run fixture tests failed:\n" + "\n".join(rr.stderr.strip().splitlines()[-15:]))

print("\n".join(errors) if errors else f"stem-check OK (version {v})")
sys.exit(1 if errors else 0)
