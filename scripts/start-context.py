#!/usr/bin/env python3
"""Start context helper (retro): measure it, list what fills it, switch things off with the user's consent.
Usage: scripts/start-context.py <command> [args]
  report [--since TIME] [--compare TIME] [transcript-dir]   start context per session (first assistant call of a main
        session: input + cache_read + cache_creation) and trend; --compare compares sessions before/after TIME (local
        'YYYY-MM-DD[ HH:MM]' or ISO with Z). Numbers only. Headless `claude -p` gives lower absolute numbers than the
        desktop app: compare like with like. Transcripts exist only for recent weeks; unknown format -> "not evaluable".
  mcp                    list configured MCP servers (user/project config files) and the current deny list
  skills                 list project skills with use counts from transcripts and the current skillOverrides
  new [--threshold BYTES] [--line] [--ack]   report skills/MCP servers not in the known-set (.claude/start-context-known.local.json) with sizes
        (project/user SKILL.md bytes; MCP size is "unknown": never 0). Below the threshold (default 250) = not reported; unknown counts as
        relevant. If anything new is relevant: re-offer ALL listed items for switch-off in the dialog. --line = one line for session start
        (silent without a known-set or without relevant news). --ack = write the known-set; only after the user answered the dialog.
  measure                run `claude -p` twice and print the first-call total (before/after method, noise ~0.4k)
  deny-mcp NAME... [--shared]    write deniedMcpServers (default .claude/settings.local.json; --shared: .claude/settings.json,
        which blocks the server for everyone using the committed file). Only after the user's authorization.
  skills-off NAME...     write skillOverrides {NAME: "off"} to .claude/settings.local.json. Only after the user's authorization.
  undo-mcp NAME... [--shared] | skills-on NAME...    remove the entries again
Each server in the context costs its instructions/tool names in every session; each listed skill ~0.1-0.3k tokens."""
import datetime as dt, glob, json, os, pathlib, re, shlex, statistics, subprocess, sys

def utc(t):
    try: d = dt.datetime.fromisoformat(re.sub(r"Z$", "+00:00", t.strip()))
    except ValueError: sys.exit("start-context: cannot parse time %r" % t)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def tdir():
    return os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", os.getcwd()))

def sessions(d, since=""):
    """[(start timestamp, start context, model)] for main sessions; first non-sidechain assistant record with usage."""
    out = []
    for f in sorted(glob.glob(d + "/*.jsonl")):  # top level only: subagent transcripts live in subfolders
        try:
            for line in open(f):
                try: r = json.loads(line)
                except ValueError: continue
                m = r.get("message") if isinstance(r, dict) else None
                if r.get("type") != "assistant" or r.get("isSidechain") or not isinstance(m, dict) or not isinstance(m.get("usage"), dict): continue
                u = m["usage"]; ts = str(r.get("timestamp", ""))[:19]
                ctx = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                if ctx and ts >= since: out.append((ts, ctx, m.get("model", "?")))
                break
        except OSError: pass
    return sorted(out)

def k(n): return "%.1fk" % (n / 1000)

def report(args):
    since = utc(args[args.index("--since") + 1]) if "--since" in args else ""
    cmp_ = utc(args[args.index("--compare") + 1]) if "--compare" in args else ""
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--since", "--compare"))]
    d = pos[0] if pos else tdir()
    s = sessions(d, since)
    if not s: print("not evaluable: no sessions with usage in", d); return
    print("start context per session (UTC start | tokens | model):")
    for ts, c, m in s[-15:]: print("  %s | %s | %s" % (ts, k(c), m))
    med = lambda x: k(statistics.median(x))
    print("sessions: %d, median %s, min %s, max %s" % (len(s), med([c for _, c, _ in s]), k(min(c for _, c, _ in s)), k(max(c for _, c, _ in s))))
    if cmp_:
        b, a = [c for t, c, _ in s if t < cmp_], [c for t, c, _ in s if t >= cmp_]
        if b and a: print("before %s (n=%d) median %s | after (n=%d) median %s | delta %s" % (cmp_, len(b), med(b), len(a), med(a), k(statistics.median(a) - statistics.median(b))))
        else: print("compare: need sessions on both sides (before %d, after %d)" % (len(b), len(a)))
        print("note: models/effort and app updates also change the number; compare sessions of the same model")

def jload(p):
    try: return json.loads(pathlib.Path(p).read_text())
    except (OSError, ValueError): return {}

def settings_paths(shared):
    return pathlib.Path(".claude/settings.json" if shared else ".claude/settings.local.json")

def mcp():
    print("Every connected MCP server adds its instructions and tool names to the start context of EVERY session (often 0.2-3k tokens each; deferred tools still list names).")
    home, here = jload(os.path.expanduser("~/.claude.json")), os.getcwd()
    found = {}
    for n in home.get("mcpServers", {}): found[n] = "user (~/.claude.json)"
    proj = (home.get("projects") or {}).get(here, {})
    for n in proj.get("mcpServers", {}): found[n] = "local (~/.claude.json, this project)"
    for n in jload(".mcp.json").get("mcpServers", {}): found[n] = "project (.mcp.json)"
    deny = set()
    for p in (".claude/settings.json", ".claude/settings.local.json", os.path.expanduser("~/.claude/settings.json")):
        for e in jload(p).get("deniedMcpServers", []): deny.add(e.get("serverName") if isinstance(e, dict) else e)
    print("configured in files (%d):" % len(found))
    for n, w in sorted(found.items()): print("  %s [%s]%s" % (n, w, " DENIED" if n in deny else ""))
    print("denied (settings): %s" % (", ".join(sorted(x for x in deny if x)) or "none"))
    print("Also run `claude mcp list` (adds claude.ai connectors and plugin servers, which these files do not show; connectors are switched off in the app's connector settings or /mcp, not here).")
    print("Fallback when a deny cannot be written: /mcp toggles a server per project; `claude mcp remove <name> --scope user|local|project` in a terminal removes it (the desktop app has no removal UI).")

def skills():
    uses = {}
    for f in glob.glob(tdir() + "/**/*.jsonl", recursive=True):
        try:
            for line in open(f):
                if '"Skill"' not in line: continue
                try: r = json.loads(line)
                except ValueError: continue
                if r.get("type") != "assistant": continue  # request-blob copies would double count
                c = (r.get("message") or {}).get("content")
                for b in c if isinstance(c, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                        n = str((b.get("input") or {}).get("skill", "?")); uses[n] = uses.get(n, 0) + 1
        except OSError: pass
    ov = {}
    for p in (".claude/settings.json", ".claude/settings.local.json"): ov.update(jload(p).get("skillOverrides", {}))
    print("project skills (description start | uses in this project's transcripts | override):")
    for f in sorted(glob.glob(".claude/skills/*/SKILL.md")):
        n = pathlib.Path(f).parent.name
        m = re.search(r"^description:\s*(.+)$", pathlib.Path(f).read_text(), re.M)
        print("  %s | %s | uses=%d | %s" % (n, (m.group(1)[:70] if m else ""), uses.get(n, 0) + uses.get("stem:" + n, 0), ov.get(n, "on")))
    other = sorted(n for n in uses if ":" in n and not n.startswith("stem:"))
    print("other skills used here: %s" % (", ".join("%s(%d)" % (n, uses[n]) for n in other) or "none"))
    print("skills from plugins/connectors (e.g. anthropic-skills:*) are listed in the session's skill list, not in the project; each listed skill costs ~0.1-0.3k tokens per session. Overrides apply only to this environment (settings.local.json); undo: `skills-on NAME` or delete the entry.")

KNOWN = ".claude/start-context-known.local.json"

def inventory():
    """{'skill:NAME' or 'mcp:NAME': size in bytes or None (unknown)}. Plugin/connector skills are not visible as files."""
    inv = {}
    for base in (".claude/skills", os.path.expanduser("~/.claude/skills")):
        for f in glob.glob(base + "/*/SKILL.md"):
            try: inv.setdefault("skill:" + pathlib.Path(f).parent.name, os.path.getsize(f))
            except OSError: pass
    home = jload(os.path.expanduser("~/.claude.json"))
    names = set(home.get("mcpServers", {})) | set(((home.get("projects") or {}).get(os.getcwd()) or {}).get("mcpServers", {})) | set(jload(".mcp.json").get("mcpServers", {}))
    for n in names: inv["mcp:" + n] = None
    return inv

def new_items(thr):
    inv = inventory()
    kn = jload(KNOWN) if pathlib.Path(KNOWN).exists() else None
    new = {n: z for n, z in inv.items() if kn is None or n not in kn.get("items", {})}
    rel = {n: z for n, z in new.items() if z is None or z >= thr}
    return inv, kn is not None, new, rel

def fmt(n, z): return "%s (%s)" % (n, "size unknown" if z is None else "%d B" % z)

def new(args):
    thr = int(args[args.index("--threshold") + 1]) if "--threshold" in args else 250
    inv, has_known, new_, rel = new_items(thr)
    if "--ack" in args:
        p = pathlib.Path(KNOWN); p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps({"items": inv}, indent=2, sort_keys=True) + "\n"); print("known-set written:", p, "(%d items)" % len(inv)); return
    if "--line" in args:
        if has_known and rel: print("new skills/MCP servers since last offer: %s -> offer switch-off again (retro start-context dialog; scripts/start-context.py new)" % ", ".join(sorted(rel)))
        return
    print("%s; threshold %d B; %d items, %d new, %d relevant" % ("known-set found" if has_known else "no known-set yet (all items count as new)", thr, len(inv), len(new_), len(rel)))
    for n, z in sorted(rel.items()): print("  NEW %s" % fmt(n, z))
    small = [n for n in new_ if n not in rel]
    if small: print("  new but below threshold (not reported): %d" % len(small))
    if rel:
        print("re-offer ALL for switch-off in the dialog (old and new):")
        for n, z in sorted(inv.items()): print("  %s%s" % (fmt(n, z), "  NEW" if n in rel else ""))
        print("after the user answered: scripts/start-context.py new --ack")
    print("not visible here: plugin/connector skills and claude.ai connectors (see `skills`, `claude mcp list`).")

def measure():
    tot = []
    for _ in range(2):
        r = subprocess.run(["claude", "-p", "Reply with the single word ok.", "--output-format", "json"], capture_output=True, text=True)
        try: u = json.loads(r.stdout)["usage"]
        except (ValueError, KeyError): sys.exit("measure: claude -p gave no usage: " + (r.stderr or r.stdout)[:200])
        tot.append(sum(int(u.get(x) or 0) for x in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))
    print("first-call total (headless): %s, %s (mean %s)" % (k(tot[0]), k(tot[1]), k(sum(tot) / 2)))

def edit(path, fn):
    p = pathlib.Path(path); d = jload(p) if p.exists() else {}
    fn(d); p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(d, indent=2) + "\n"); print("written:", p)

def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"): print(__doc__); return
    cmd, rest = a[0], a[1:]
    shared = "--shared" in rest; names = [x for x in rest if not x.startswith("--")]
    if cmd == "report": report(rest)
    elif cmd == "mcp": mcp()
    elif cmd == "skills": skills()
    elif cmd == "new": new(rest)
    elif cmd == "measure": measure()
    elif cmd in ("deny-mcp", "undo-mcp") and names:
        def f(d):
            cur = [e for e in d.get("deniedMcpServers", []) if (e.get("serverName") if isinstance(e, dict) else e) not in names]
            d["deniedMcpServers"] = cur + ([{"serverName": n} for n in names] if cmd == "deny-mcp" else [])
            if not d["deniedMcpServers"]: del d["deniedMcpServers"]
        edit(settings_paths(shared), f)
        if shared and cmd == "deny-mcp": print("note: this file is committed; the deny applies to everyone who uses it")
        print("undo: scripts/start-context.py undo-mcp %s%s; takes effect in the next session" % (" ".join(shlex.quote(n) for n in names), " --shared" if shared else ""))
    elif cmd in ("skills-off", "skills-on") and names:
        def f(d):
            o = d.setdefault("skillOverrides", {})
            for n in names:
                if cmd == "skills-off": o[n] = "off"
                else: o.pop(n, None)
            if not o: del d["skillOverrides"]
        edit(".claude/settings.local.json", f)
        print("undo: scripts/start-context.py %s %s; takes effect in the next session" % ("skills-on" if cmd == "skills-off" else "skills-off", " ".join(shlex.quote(n) for n in names)))
    else: sys.exit(__doc__)

if __name__ == "__main__": main()
