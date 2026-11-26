#!/usr/bin/env python3
"""Retro helper (topic 'memories'): reports what the user's auto-memory of THIS project costs and which entries are
candidates for keep/merge/delete. Numbers and file names only; the memory text is not printed.
Scope: Claude Code only (its auto-memory under ~/.claude/projects). Codex has no auto-memory: there the script finds no
folder, prints that and exits 2; skip the topic.
Usage: scripts/memory-report.py [--dir MEMORY_DIR] [--stale-days N] [--now YYYY-MM-DD]
Default dir: ~/.claude/projects/<project path, every non-alphanumeric character replaced by ->/memory. Per session only MEMORY.md is loaded; the
other files are read when relevant. Candidates (suggestions, the user decides every deletion):
  stale     file not modified for more than --stale-days (default 60)
  dangling  [[link]] to a memory that does not exist
  orphan    memory file that MEMORY.md does not list, or an index line whose file is missing
  similar   two memories whose description words overlap by 60 % or more (possible duplicate)
  repo      description mentions a path that exists in this repository (possible duplicate of repo content)
Exit 0 always (report only); exit 2 if the memory folder is missing."""
import argparse, datetime as dt, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parents[1]


def words(text):
    return {w for w in re.findall(r"[a-zäöüß]{4,}", text.lower())}


def front(path):
    t = path.read_text(errors="replace")
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    head = m.group(1) if m else t[:600]
    d = re.search(r"^description:\s*(.*)$", head, re.M)
    return (d.group(1).strip().strip('"') if d else ""), t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir"); ap.add_argument("--stale-days", type=int, default=60); ap.add_argument("--now")
    a = ap.parse_args()
    d = pathlib.Path(a.dir) if a.dir else pathlib.Path.home() / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(HERE)) / "memory"
    if not d.is_dir():
        print(f"memory-report: no memory folder {d} (Claude Code only; Codex has no auto-memory)", file=sys.stderr); return 2
    now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now()
    index = d / "MEMORY.md"
    files = sorted(p for p in d.glob("*.md") if p.name != "MEMORY.md")
    idx_text = index.read_text(errors="replace") if index.exists() else ""
    idx_bytes = index.stat().st_size if index.exists() else 0
    total = idx_bytes + sum(p.stat().st_size for p in files)
    print(f"memory folder: {len(files)} memories, index {idx_bytes} bytes ({idx_bytes / 1000:.1f} kB loaded every session), all files {total / 1000:.1f} kB")
    names = {p.stem for p in files}
    info = {}
    for p in files:
        desc, text = front(p)
        info[p.stem] = (desc, text, (now - dt.datetime.fromtimestamp(p.stat().st_mtime)).days, p.stat().st_size)
    cand = []
    listed = set(re.findall(r"\(([^)]+?\.md)\)", idx_text))
    for n, (desc, text, age, size) in sorted(info.items()):
        if age > a.stale_days: cand.append(("stale", n, f"{age} days since last change"))
        for l in sorted(set(re.findall(r"\[\[([^\]]+)\]\]", text))):
            if l not in names: cand.append(("dangling", n, f"[[{l}]] has no memory file"))
        if f"{n}.md" not in listed: cand.append(("orphan", n, "not listed in MEMORY.md"))
        for tok in sorted(set(re.findall(r"(?<![\w/.-])((?:docs|scripts|\.claude)/[\w./-]+)", desc))):
            if (HERE / tok).exists(): cand.append(("repo", n, f"description names {tok}, which exists in the repository"))
    for f in sorted(listed - {f"{n}.md" for n in names}): cand.append(("orphan", f, "index line without a file"))
    ns = sorted(info)
    for i, x in enumerate(ns):
        for y in ns[i + 1:]:
            wx, wy = words(info[x][0]), words(info[y][0])
            if wx and wy and len(wx & wy) / min(len(wx), len(wy)) >= 0.6: cand.append(("similar", f"{x} / {y}", "description words overlap"))
    print("files (bytes, age in days):", "; ".join(f"{n} {v[3]}B {v[2]}d" for n, v in sorted(info.items())) or "none")
    if cand:
        print(f"candidates: {len(cand)}")
        for kind, n, why in cand: print(f"  {kind}: {n}: {why}")
    else:
        print("candidates: none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
