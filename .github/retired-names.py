#!/usr/bin/env python3
"""STEM self-check part (STEM maintenance only; run by stem-check.py or directly: python3 .github/retired-names.py [ROOT]).
Fails with a file:line list when a retired name is still referenced, so a rename is finished in one go.
Add the old name to RETIRED on every rename; history (CHANGELOG.md) and migration notes may keep it."""
import pathlib, re, sys

RETIRED = ["KIT_VERSION", "kit-check", "kit-update", "design-alignment", "LEARNINGS.md", "R-KIT-UPDATE", "R-BOOTSTRAP", "R-BATCH-CONTRACT", "R-AGENT-TOPOLOGY"]
ALLOWED = ["CHANGELOG.md", ".github/retired-names.py", ".github/tests/"]  # add migration notes here
SKIP_PARTS = {".git", "__pycache__", "node_modules"}
pattern = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in RETIRED) + r")(?![\w-])")


def hits(root):
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or p.is_symlink() or SKIP_PARTS & set(p.parts) or any(rel == a or rel.startswith(a) for a in ALLOWED): continue
        try: lines = p.read_text().splitlines()
        except (UnicodeDecodeError, OSError): continue
        out += [f"{rel}:{i}: {m.group(1)}" for i, line in enumerate(lines, 1) for m in pattern.finditer(line)]
    return out


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
    found = hits(root)
    print("\n".join(["retired names still referenced:"] + found) if found else "retired names: none")
    sys.exit(1 if found else 0)
