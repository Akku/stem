#!/usr/bin/env python3
"""STEM optional modules (TASK-349): list | enable NAME | disable NAME [--root DIR].

A module is a set of files plus optional reference lines. Its manifest is
docs/agent/modules/<name>/MODULE.md (strict frontmatter, see below); the status
(on|off) lives in docs/agent/modules/INDEX.md, one line per module:
  - <name>: on|off - <purpose>
Off: the files are moved to docs/agent/modules/<name>/files/<target path> (not
scanned by tools, so no start context) and the reference lines are removed.
On: the files are in their target place and the reference lines are present.
Nothing is ever deleted. Manifest frontmatter:
  name, purpose, when_useful, version, files (list of target paths),
  refs (optional list of items: file, after, line; `line` is inserted after the
  line containing `after` when enabled and removed when disabled).
"""
import argparse, pathlib, re, shutil, sys

def parse(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("MODULE.md has no frontmatter")
    d, key, item = {}, None, None
    for raw in m.group(1).split("\n"):
        if not raw.strip():
            continue
        if raw.startswith("  - ") and key:
            item = raw[4:].strip()
            kv = re.match(r"(\w+):\s*(.*)$", item)
            if kv and key == "refs":
                item = {kv.group(1): kv.group(2).strip('"')}
                d[key].append(item)
            else:
                d[key].append(item.strip('"'))
        elif raw.startswith("    ") and isinstance(item, dict):
            kv = re.match(r"(\w+):\s*(.*)$", raw.strip())
            item[kv.group(1)] = kv.group(2).strip('"')
        else:
            kv = re.match(r"(\w+):\s*(.*)$", raw)
            if not kv:
                raise ValueError("bad frontmatter line: " + raw)
            key = kv.group(1)
            d[key] = [] if kv.group(2) == "" else kv.group(2)
    for req in ("name", "purpose", "when_useful", "version", "files"):
        if req not in d:
            raise ValueError("MODULE.md lacks field " + req)
    return d

class Mods:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        self.dir = self.root / "docs/agent/modules"
        self.index = self.dir / "INDEX.md"

    def status(self):
        out = {}
        for ln in self.index.read_text().splitlines() if self.index.exists() else []:
            m = re.match(r"- ([\w-]+): (on|off) - ", ln)
            if m:
                out[m.group(1)] = m.group(2)
        return out

    def manifest(self, name):
        p = self.dir / name / "MODULE.md"
        if not p.exists():
            raise ValueError("unknown module " + name)
        return parse(p.read_text())

    def set_status(self, name, state, purpose):
        lines = self.index.read_text().splitlines() if self.index.exists() else []
        new = f"- {name}: {state} - {purpose}"
        for i, ln in enumerate(lines):
            if ln.startswith(f"- {name}: "):
                lines[i] = new
                break
        else:
            lines.append(new)
        self.index.write_text("\n".join(lines) + "\n")

    def actual(self, man):
        have = [(self.root / f).exists() for f in man["files"]]
        return "on" if all(have) else "off" if not any(have) else "partial"

    def move(self, man, src, dst):
        for f in man["files"]:
            s, t = src(f), dst(f)
            if not s.exists():
                raise ValueError(f"missing {s}")
            if t.exists():
                raise ValueError(f"target exists {t}")
        for f in man["files"]:
            s, t = src(f), dst(f)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(t))
            d = s.parent
            while d.parent != self.root and d.parent.parent != self.root and d.is_dir() and not any(d.iterdir()):
                d.rmdir(); d = d.parent

    def refs(self, man, add):
        for r in man.get("refs", []):
            p = self.root / r["file"]
            lines = p.read_text().split("\n")
            has = r["line"] in lines
            if add and not has:
                i = next((k for k, ln in enumerate(lines) if r["after"] in ln), None)
                if i is None:
                    raise ValueError(f"anchor not found in {r['file']}: {r['after']}")
                lines.insert(i + 1, r["line"])
            elif not add and has:
                lines.remove(r["line"])
            else:
                continue
            p.write_text("\n".join(lines))

    def change(self, name, enable):
        man = self.manifest(name)
        state = self.actual(man)
        if state == "partial":
            raise ValueError(f"{name}: only part of its files exist; ask the user")
        if state == ("on" if enable else "off"):
            self.set_status(name, state, man["purpose"])
            print(f"{name}: already {state}")
            return
        arch = lambda f: self.dir / name / "files" / f
        act = lambda f: self.root / f
        if enable:
            self.move(man, arch, act)
        else:
            self.move(man, act, arch)
        self.refs(man, enable)
        self.set_status(name, "on" if enable else "off", man["purpose"])
        print(f"{name}: {'on' if enable else 'off'}")

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["list", "enable", "disable"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent))
    a = ap.parse_args(argv)
    m = Mods(a.root)
    try:
        if a.cmd == "list":
            st = m.status()
            for p in sorted(m.dir.glob("*/MODULE.md")):
                man = parse(p.read_text())
                act = m.actual(man)
                note = "" if st.get(man["name"]) == act else f"  (INDEX says {st.get(man['name'], '-')}, files say {act})"
                print(f"{man['name']}: {act} - {man['purpose']}{note}")
        else:
            if not a.name:
                ap.error("module name required")
            m.change(a.name, a.cmd == "enable")
    except ValueError as e:
        print("module.py: " + str(e), file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
