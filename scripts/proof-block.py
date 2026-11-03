#!/usr/bin/env python3
"""Numbers-only proof block for a learning or field report (promote-learning, retro field report).
Every field is checked against a strict pattern, so free text, paths, names and secrets cannot get in; a bad value aborts with exit 2.
Usage: scripts/proof-block.py --rule R-ID --metric name --before N --after N --n N --models a,b --effort medium --stem-version X.Y.Z --grade G0..G3 [--unit k]"""
import argparse, re, sys

PAT = {
    "rule": r"R-[A-Z][A-Z0-9-]{1,30}",
    "metric": r"[a-z][a-z0-9_]{1,40}",
    "before": r"-?\d{1,9}(\.\d{1,3})?",
    "after": r"-?\d{1,9}(\.\d{1,3})?",
    "n": r"\d{1,6}",
    "models": r"[a-z][a-z0-9.-]{1,30}(,[a-z][a-z0-9.-]{1,30}){0,4}",
    "effort": r"low|medium|high|xhigh|max",
    "stem_version": r"\d{1,3}\.\d{1,3}\.\d{1,3}",
    "grade": r"G[0-3]",
    "unit": r"|k|M|%|s|turns",
}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in PAT:
        ap.add_argument("--" + k.replace("_", "-"), dest=k, default="" if k == "unit" else None)
    a = vars(ap.parse_args(argv))
    bad = [k for k, p in PAT.items() if a[k] is None or not re.fullmatch(p, a[k])]
    if bad:
        print("proof-block: refused, field(s) not matching the allowed pattern (numbers and fixed words only): " + ", ".join(bad), file=sys.stderr)
        return 2
    u = a["unit"]
    print("**Proof (numbers only; no project data)**")
    print("| Rule | Metric | Before | After | N | Models | Effort | STEM | Grade |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    print(f"| {a['rule']} | {a['metric']} | {a['before']}{u} | {a['after']}{u} | {a['n']} | {a['models']} | {a['effort']} | {a['stem_version']} | {a['grade']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
