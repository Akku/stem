#!/usr/bin/env python3
"""STEM self-check part (STEM maintenance only; run by stem-check.py or directly: python3 .github/rule-reach.py [ROOT]).
Every operating-model rule must be reachable: its ID is named outside docs/agent/OPERATING_MODEL.md and docs/agent/ADVANCED.md
(AGENTS.md, a skill, a script hint), not only in the index. A rule the agent never hears of cannot help (TASK-210)."""
import pathlib, re, sys

RULE_FILES = ("docs/agent/OPERATING_MODEL.md", "docs/agent/ADVANCED.md")
SKIP_PARTS = {".git", ".agent-logs", "__pycache__", "tests", "node_modules"}
SKIP_FILES = set(RULE_FILES) | {"CHANGELOG.md"}


def unreachable(root):
    ids = set()
    for f in RULE_FILES:
        p = root / f
        if p.exists(): ids |= set(re.findall(r"<!-- RULE:(R-[A-Z0-9-]+):START -->", p.read_text()))
    ids.discard("R-INDEX")
    corpus = []
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or p.is_symlink() or SKIP_PARTS & set(p.parts) or rel in SKIP_FILES or p.suffix not in (".md", ".py", ".sh", ".json"): continue
        try: corpus.append(p.read_text())
        except (UnicodeDecodeError, OSError): pass
    text = "\n".join(corpus)
    return sorted(i for i in ids if not re.search(r"(?<![\w-])" + re.escape(i) + r"(?![\w-])", text))


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
    bad = unreachable(root)
    for i in bad: print(f"rule {i} is not named outside the rule files: add a pointer where its situation arises, or remove the rule")
    print("rule reach: " + ("all rules reachable" if not bad else f"{len(bad)} unreachable"))
    sys.exit(1 if bad else 0)
