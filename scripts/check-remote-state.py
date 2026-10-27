#!/usr/bin/env python3
"""Show cached remote context without fetching or changing the checkout."""
import subprocess


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def main():
    refs = git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/")
    if refs.returncode:
        return
    names = [n for n in refs.stdout.splitlines() if n != "origin/HEAD"]
    if not names:
        print("remote context: no cached origin branches; live state not checked")
    else:
        tip = git("rev-parse", "--short", "origin/main")
        print("remote context (cached, not a live check): origin/main " +
              (tip.stdout.strip() if tip.returncode == 0 else "unknown"))
    fetch = git("config", "--get-all", "remote.origin.fetch")
    full = {"+refs/heads/*:refs/remotes/origin/*",
            "refs/heads/*:refs/remotes/origin/*"}
    if fetch.returncode == 0 and not full.intersection(fetch.stdout.splitlines()):
        print("WARNING: origin fetch is restricted; list live branches with "
              "git ls-remote --heads origin before assuming main is complete")
    pending = [n for n in names
               if git("merge-base", "--is-ancestor", n, "HEAD").returncode != 0]
    if pending:
        print("WARNING: cached branches contain work outside HEAD: " +
              ", ".join(pending[:3]) +
              (f" (+{len(pending) - 3} more)" if len(pending) > 3 else ""))


if __name__ == "__main__":
    main()
