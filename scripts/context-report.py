#!/usr/bin/env python3
"""Where did the context go? Optional retro tool for Claude Code transcripts (R-MEASUREMENT level 2/3).
Usage: scripts/context-report.py [--since TIME] [--until TIME] [--main-only] [--brief|--cost] [transcript-dir]   (default dir: this project's folder under ~/.claude/projects)
--brief prints one key=value line (for retro-metrics.sh): sessions, turns, tokens, longest session, user_msgs (typed user messages, effort proxy), models and effort levels seen (confounders).
--cost prints one key=value line for a window: turns, tool_calls, cache_read, output (retro-run.py finish uses it with --since/--until as UTC "YYYY-MM-DDTHH:MM:SSZ" and --main-only).
--main-only skips subagent transcripts and sidechain records.
TIME: YYYY-MM-DD[ HH:MM] is local time; ISO with Z or offset (2026-11-03T15:10Z) is taken as given. --since limits sessions, totals
and biggest carried results to records at or after it (retro metrics that start after a change); the report prints the UTC window.
Prints numbers only. Labels may contain tool names, file base names and the first two words of a shell command:
review before copying anything into notes. The transcript format is undocumented; unknown format -> "not evaluable".
Estimates are rough (characters / 4; assumes a result stays in context until the session ends, so compaction makes it an upper bound)."""
import collections, datetime as dt, glob, json, os, re, sys

RULE_ID = re.compile(r"\bR-[A-Z][A-Z-]+[A-Z]\b")

def utc_since(since):
    """--since/--until: ISO time; without offset it is local time (date only = local midnight), Z or +HH:MM marks the zone.
    Returns "YYYY-MM-DDTHH:MM:SS" UTC to compare with transcript timestamps; unparsable input stops the run."""
    try: t = dt.datetime.fromisoformat(re.sub(r"Z$", "+00:00", since.strip()))  # Z: Python < 3.11
    except ValueError: sys.exit("context-report: cannot parse time %r (use YYYY-MM-DD[ HH:MM] local or ISO with Z/offset)" % since)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def main():
    args = sys.argv[1:]
    since = utc_since(args[args.index("--since") + 1]) if "--since" in args else ""
    until = utc_since(args[args.index("--until") + 1]) if "--until" in args else ""
    brief, cost, main_only = "--brief" in args, "--cost" in args, "--main-only" in args
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--since", "--until"))]
    d = pos[0] if pos else os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", os.getcwd()))
    files = sorted(glob.glob(d + "/**/*.jsonl", recursive=True))
    if main_only: files = [f for f in files if "/subagents/" not in f]
    if not files:
        print("not evaluable: no transcripts in", d); return 0
    tool_calls = user_msgs = 0
    tot, sess, by_tool, cnt, offenders = collections.Counter(), [], collections.Counter(), collections.Counter(), []
    rules, skills, docs = collections.Counter(), collections.Counter(), collections.Counter()
    models, efforts = collections.Counter(), collections.Counter()
    def size(c):
        if isinstance(c, str): return len(c)
        if isinstance(c, list): return sum(len(x.get("text", "")) if isinstance(x, dict) else len(str(x)) for x in c)
        return len(str(c))
    def label(n, i):
        if n == "Bash": return "Bash:" + " ".join((i.get("command") or "").split()[:2])[:30]
        if n in ("Read", "Edit", "Write"): return n + ":" + os.path.basename(i.get("file_path", ""))
        return n
    for f in files:
        turns, u, pend, items = 0, collections.Counter(), {}, []
        for line in open(f, encoding="utf-8", errors="replace"):
            try: r = json.loads(line)
            except ValueError: continue
            m = r.get("message") if isinstance(r.get("message"), dict) else {}
            ts = str(r.get("timestamp", ""))
            if since and ts[:19] < since: continue
            if until and ts[:19] > until: continue
            if main_only and r.get("isSidechain"): continue
            if r.get("type") == "assistant":
                turns += 1
                models[str(m.get("model", "?"))] += 1
                if r.get("effort"): efforts[str(r.get("effort"))] += 1
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
                    u[k] += (m.get("usage") or {}).get(k, 0)
                for b in m.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        n, i = b.get("name", "?"), b.get("input") or {}
                        tool_calls += 1
                        pend[b.get("id")] = (n, i)
                        cmd = i.get("command") or "" if n == "Bash" else ""
                        if "RULE:" in cmd or "ID=R-" in cmd or ":START" in cmd:
                            rules.update(set(RULE_ID.findall(cmd)) - {"R-INDEX"})
                        if n == "Skill": skills[str(i.get("skill", "?")).split(":")[-1]] += 1
                        p = i.get("file_path", "") if n == "Read" else ""
                        sm = re.search(r"\.claude/skills/([^/]+)/SKILL\.md", p)
                        if sm: skills[sm.group(1)] += 1
                        if re.search(r"(ADVANCED|GLOSSARY|ARCHITECTURE|PITFALLS|NEXT_RETRO|LEARNINGS|HANDOFF)\.md$|docs/agent/stacks/", p): docs[os.path.basename(p)] += 1
            elif r.get("type") == "user" and not r.get("isMeta") and not r.get("isSidechain") and "/subagents/" not in f and (isinstance(m.get("content"), str) or any(isinstance(b, dict) and b.get("type") == "text" for b in m.get("content") or [])):
                user_msgs += 1   # typed by the user (tool results and subagent records excluded); a human-effort proxy
            if r.get("type") == "user" and isinstance(m.get("content"), list):
                for b in m["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        n, i = pend.get(b.get("tool_use_id"), ("?", {}))
                        items.append((turns, size(b.get("content")), label(n, i), n))
        for t, s, lb, n in items:
            by_tool[n] += s; cnt[n] += 1; offenders.append((s / 4 * (turns - t), s, lb, turns - t))
        if turns: sess.append((os.path.basename(f)[:8], turns, u))
        tot.update(u)
    if not sum(tot.values()):
        print("not evaluable: no usage data (format changed?)"); return 0
    if cost:
        print("turns=%d tool_calls=%d cache_read=%d output=%d" % (sum(s[1] for s in sess), tool_calls, tot["cache_read_input_tokens"], tot["output_tokens"]))
        return 0
    if brief:
        print("sessions=%d turns=%d cache_read=%d cache_write=%d output=%d max_session_turns=%d user_msgs=%d models=%s effort=%s" % (len(sess), sum(s[1] for s in sess), tot["cache_read_input_tokens"], tot["cache_creation_input_tokens"], tot["output_tokens"], max([s[1] for s in sess] or [0]), user_msgs, ",".join(k for k, _ in models.most_common(3)) or "?", ",".join(k for k, _ in efforts.most_common(3)) or "?"))
        return 0
    if since or until: print("window (UTC): %s .. %s" % (since or "start", until or "now"))
    print("transcripts: %d, assistant turns: %d" % (len(files), sum(s[1] for s in sess)))
    print("tokens: fresh_in %d | cache_write %d | cache_read %d | output %d" % (tot["input_tokens"], tot["cache_creation_input_tokens"], tot["cache_read_input_tokens"], tot["output_tokens"]))
    turns_all = max(sum(s[1] for s in sess), 1)
    print("avg context carried per turn (cache_read/turn): %dk tokens" % (tot["cache_read_input_tokens"] / turns_all / 1000))
    print("\nlongest sessions by cache_read (session length is usually the biggest lever):")
    for sid, t, u in sorted(sess, key=lambda x: -x[2]["cache_read_input_tokens"])[:5]:
        print("  %s turns %d cache_read %.1fM output %.0fk" % (sid, t, u["cache_read_input_tokens"] / 1e6, u["output_tokens"] / 1e3))
    print("\ntool result volume (chars, count):")
    for n, s in by_tool.most_common(6): print("  %s %d %d" % (n, s, cnt[n]))
    allc = sum(o[0] for o in offenders) or 1
    print("\nbiggest carried tool results (size/4 x later turns); estimated share of all cache_read: %.0f%%" % (100 * allc / max(tot["cache_read_input_tokens"], 1)))
    for e, s, lb, after in sorted(offenders, reverse=True)[:10]:
        print("  %.1fM tok-turns | %d chars | %s | %d turns after" % (e / 1e6, s, lb, after))
    print("\nusage of optional material (retro: use deliberately, keep, or remove):")
    known = set()
    for f in ("docs/agent/OPERATING_MODEL.md", "docs/agent/ADVANCED.md"):
        if os.path.exists(f): known |= set(re.findall(r"<!-- RULE:(R-[A-Z-]+):START -->", open(f, encoding="utf-8").read())) - {"R-INDEX"}
    print("  rules loaded by ID:", dict(rules.most_common()) or "none")
    if known: print("  rules never loaded:", ", ".join(sorted(known - set(rules))) or "none")
    avail = set(os.listdir(".claude/skills")) if os.path.isdir(".claude/skills") else set()
    print("  skills used:", dict(skills.most_common()) or "none")
    if avail: print("  skills never used:", ", ".join(sorted(avail - set(skills))) or "none")
    print("  docs read:", dict(docs.most_common()) or "none")
    return 0

if __name__ == "__main__":
    sys.exit(main())
