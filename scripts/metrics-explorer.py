#!/usr/bin/env python3
"""Interactive metrics explorer for a retro (TASK-311): one self-contained offline HTML file from this project's current data.
Usage: scripts/metrics-explorer.py [--out FILE] [--json] [--now ISO] [transcript-dir ...]
  default out: .agent-logs/metrics-explorer.html (git-ignored, local only); --json prints the collected data instead of writing HTML.
  default transcript dirs: this project's folders under ~/.claude/projects (main checkout and its worktrees, as context-report.py).
Sources (numbers and IDs only, never message text): transcripts (time, turns, tool calls, tokens per model, compactions, context size),
backlog task files (id, title, status, size label, milestone, dates, Outcome line, evidence levels, Learning count),
retro run files docs/agent/retro-runs/*.json (stage, result, cost line), git commit subjects (task IDs and times only).
Cost: estimate from the price table in context-report.py (one source; a model without a price shows n/a, never 0).
Known limits: a session is linked to the tasks named in commits made during its time window; active time sums gaps under 5 minutes;
cycle time = created to last update of a Done task; transcripts exist only for recent weeks."""
import collections, datetime as dt, glob, importlib.util, json, os, pathlib, re, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "metrics-explorer.html"
KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
TASK = re.compile(r"\bTASK-(\d+)\b", re.I)
IDLE = 300  # seconds: longer gaps between records count as idle, not active time

def load_context_report():
    spec = importlib.util.spec_from_file_location("context_report", HERE / "context-report.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

def ts(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError: return None

def local_ts(v):
    """Backlog.md dates are local 'YYYY-MM-DD HH:MM'; ISO with Z or offset is taken as given."""
    try: t = dt.datetime.fromisoformat(str(v or "").strip().replace("Z", "+00:00"))
    except ValueError: return None
    return (t if t.tzinfo else t.astimezone()).astimezone(dt.timezone.utc)

def iso(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None

def parse_session(path, cr):
    """Numbers of one transcript's main thread plus its subagents' tokens (<session>/subagents/*.jsonl, counted in models and cost,
    not in turns or time); None without assistant turns. Assistant records are deduplicated by message id."""
    seen, times, models = {}, [], {}
    sub_turns = 0
    for sp in glob.glob(glob.escape(path[:-6]) + "/subagents/*.jsonl"):
        for line in open(sp, encoding="utf-8", errors="replace"):
            try: r = json.loads(line)
            except ValueError: continue
            m = r.get("message") if isinstance(r.get("message"), dict) else {}
            if r.get("type") == "assistant" and str(m.get("model")) != "<synthetic>": seen[m.get("id") or r.get("uuid") or "%s-%d" % (sp, len(seen))] = (str(m.get("model") or "unknown"), m.get("usage") or {})
    for name, u in seen.values():
        sub_turns += 1
        pm = models.setdefault(name, collections.Counter())
        for k in KEYS: pm[k] += u.get(k, 0) or 0
        pm["turns"] += 1
    turns = tools = users = compactions = 0
    start_ctx = peak_ctx = 0
    usage, order = {}, []
    for line in open(path, encoding="utf-8", errors="replace"):
        try: r = json.loads(line)
        except ValueError: continue
        if r.get("isSidechain"): continue
        if r.get("subtype") == "compact_boundary" or r.get("isCompactSummary"): compactions += 1
        t = ts(r.get("timestamp"))
        if t: times.append(t)
        m = r.get("message") if isinstance(r.get("message"), dict) else {}
        if r.get("type") == "assistant":
            # one record per content block, all sharing the message id: tool_use blocks count in every record, usage once per id (last record)
            mid = m.get("id") or r.get("uuid") or "line-%d" % len(times)
            if mid not in usage: order.append(mid)
            usage[mid] = (str(m.get("model") or "unknown"), m.get("usage") or {})
            tools += sum(1 for b in (m.get("content") if isinstance(m.get("content"), list) else []) if isinstance(b, dict) and b.get("type") == "tool_use")
        elif r.get("type") == "user" and not r.get("isMeta") and (isinstance(m.get("content"), str) or any(isinstance(b, dict) and b.get("type") == "text" for b in m.get("content") or [])):
            users += 1
    for mid in order:
        name, u = usage[mid]
        if name == "<synthetic>": continue  # client-made records without tokens; would void the cost as an unpriced model
        if name == "?": name = "unknown"
        turns += 1
        pm = models.setdefault(name, collections.Counter())
        for k in KEYS: pm[k] += u.get(k, 0) or 0
        pm["turns"] += 1
        ctx = sum((u.get(k, 0) or 0) for k in KEYS[:3])
        if ctx and not start_ctx: start_ctx = ctx
        peak_ctx = max(peak_ctx, ctx)
    if not turns or not times: return None
    times.sort()
    active = sum(min((b - a).total_seconds(), IDLE) for a, b in zip(times, times[1:]) if (b - a).total_seconds() < IDLE)
    out_models = {}
    for name, c in models.items():
        p = cr.price_of(name)
        cost = sum(c[k] * x for k, x in zip(KEYS, p)) / 1e6 if p else None
        out_models[name] = {"turns": c["turns"], "input": c[KEYS[0]], "cache_write": c[KEYS[1]], "cache_read": c[KEYS[2]], "output": c[KEYS[3]],
                            "cost": round(cost, 4) if cost is not None else None}
    costs = [m["cost"] for m in out_models.values()]
    return {"id": os.path.basename(path)[:8], "start": iso(times[0]), "end": iso(times[-1]),
            "wall_min": round((times[-1] - times[0]).total_seconds() / 60, 1), "active_min": round(active / 60, 1),
            "turns": turns, "subagent_turns": sub_turns, "tool_calls": tools, "user_msgs": users, "compactions": compactions,
            "start_ctx": start_ctx, "peak_ctx": peak_ctx, "models": out_models,
            "cost": round(sum(costs), 4) if costs and None not in costs else None, "tasks": []}

def commits():
    """(time, [task ids]) per commit of this repository; subjects are reduced to task IDs."""
    try: out = subprocess.run(["git", "log", "--format=%cI%x09%s"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError): return []
    res = []
    for line in out.splitlines():
        t, _, s = line.partition("\t")
        ids = sorted({"TASK-%s" % n for n in TASK.findall(s)})
        if ts(t): res.append((ts(t), ids))
    return res

def unquote(v):
    """YAML scalar quotes: 'it''s' -> it's, "a" -> a."""
    if len(v) > 1 and v[0] == v[-1] == "'": return v[1:-1].replace("''", "'")
    return v.strip("'\"")

def front(text):
    """Minimal frontmatter reader for Backlog.md task files: scalars, folded scalars and simple lists."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    data, key = {}, None
    for line in (m.group(1).splitlines() if m else []):
        if re.match(r"^[A-Za-z_]+:", line):
            key, _, v = line.partition(":"); v = v.strip()
            data[key] = [] if v == "" else (" " if v in (">-", ">", "|", "|-") else unquote(v))
        elif key and line.strip().startswith("- ") and isinstance(data.get(key), list):
            data[key].append(line.strip()[2:].strip("'\""))
        elif key and isinstance(data.get(key), str):
            data[key] = (data[key] + " " + line.strip()).strip()
    return data, text[m.end():] if m else text

def parse_task(path):
    text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    f, body = front(text)
    labels = f.get("labels") if isinstance(f.get("labels"), list) else []
    size = next((l[5:] for l in labels if l.startswith("size-")), None)
    oc = re.findall(r"^Outcome:\s*(.+)$", body, re.M)
    outcome = None
    if oc and "pending" not in oc[-1]:
        g = lambda k: (re.search(r"\b%s=(\d+)" % k, oc[-1]) or [None, None])[1]
        outcome = {"corrections": int(g("corrections")) if g("corrections") else None, "rework_min": int(g("rework")) if g("rework") else None,
                   "defects": int(g("defects")) if g("defects") else None}
    acs = re.findall(r"^- \[([ x])\] #\d+", body.split("## Definition of Done")[0], re.M)
    created, updated = local_ts(f.get("created_date")), local_ts(f.get("updated_date"))
    status = f.get("status", "")
    return {"id": f.get("id", ""), "title": f.get("title", ""), "status": status, "size": size,
            "milestone": f.get("milestone") or None, "created": iso(created), "updated": iso(updated),
            "cycle_h": round((updated - created).total_seconds() / 3600, 1) if status == "Done" and created and updated else None,
            "outcome": outcome, "e1": len(re.findall(r"\bAC#\d+:\s*E1\b", body)), "e2": len(re.findall(r"\bAC#\d+:\s*E2\b", body)),
            "ac_total": len(acs), "ac_done": acs.count("x"), "learnings": len(re.findall(r"^Learning:", body, re.M)),
            "blocked": bool(re.search(r"\bBLOCKED\b", body))}

def milestones():
    res = {}
    for p in glob.glob("backlog/milestones/*.md"):
        f, _ = front(pathlib.Path(p).read_text(encoding="utf-8", errors="replace"))
        if f.get("id"): res[f["id"]] = f.get("title", f["id"])
    return res

def retros():
    res = []
    for p in sorted(glob.glob("docs/agent/retro-runs/*.json")):
        try: d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError): continue
        c, r = d.get("cost") or {}, d.get("result") or {}
        res.append({"label": d.get("label") or pathlib.Path(p).stem, "created": d.get("created"), "finished": d.get("finished"),
                    "stage": d.get("stage"), "outcome": d.get("outcome"), "adopted": r.get("adopted"), "open_signals": r.get("open_signals"),
                    "turns": c.get("turns"), "tool_calls": c.get("tool_calls"), "cache_read": c.get("cache_read"), "output": c.get("output"),
                    "cost": c.get("est_cost_usd")})
    return res

def collect(dirs, now):
    cr = load_context_report()
    files = sorted(f for d in dirs for f in glob.glob(glob.escape(d) + "/*.jsonl"))
    sessions = [s for s in (parse_session(f, cr) for f in files) if s]
    cs = commits()
    for s in sessions:
        a, b = ts(s["start"]), ts(s["end"]) + dt.timedelta(minutes=10)
        s["tasks"] = sorted({i for t, ids in cs if a <= t <= b for i in ids}, key=lambda x: int(x[5:]))
        s["commits"] = sum(1 for t, _ in cs if a <= t <= b)
    paths = glob.glob("backlog/tasks/*.md") + glob.glob("backlog/completed/*.md") + glob.glob("backlog/archive/tasks/*.md")
    tasks = [t for t in (dict(parse_task(p), archived="/archive/" in p) for p in sorted(paths)) if t["id"]]
    return {"meta": {"generated": iso(now), "prices_date": cr.PRICES_DATE, "transcripts": len(files), "idle_gap_s": IDLE,
                     "note": "Numbers and IDs only; estimates, not invoices."},
            "milestones": milestones(), "sessions": sessions, "tasks": tasks, "retros": retros()}

def main(argv):
    args = list(argv)
    def opt(name):
        if name in args:
            i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
        return None
    out = os.path.abspath(opt("--out")) if "--out" in args else ".agent-logs/metrics-explorer.html"
    now = ts(opt("--now") or "") or dt.datetime.now(dt.timezone.utc)
    as_json = "--json" in args
    try: os.chdir(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10).stdout.strip() or ".")
    except (OSError, subprocess.SubprocessError): pass
    dirs = [os.path.abspath(a) for a in args if not a.startswith("--")] or load_context_report().project_dirs()
    data = collect(dirs, now)
    if as_json:
        print(json.dumps(data, indent=1)); return 0
    if not TEMPLATE.exists(): sys.exit("metrics-explorer: template missing: %s" % TEMPLATE)
    blob = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__STEM_DATA__*/null", blob, 1)
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(html, encoding="utf-8")
    print("metrics-explorer: wrote %s (%d sessions, %d tasks, %d retros; open it in a browser, works offline)" % (out, len(data["sessions"]), len(data["tasks"]), len(data["retros"])))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
