# DeutschlandGPT Code adapter

This project's rules are in `AGENTS.md`. Read it completely before any other work in a new conversation and again after a compaction, then follow it. Shared rules stay there; add only DeutschlandGPT-specific mechanics here.

- No STEM hooks run in this app. At the start of a conversation run `bash scripts/session-start.sh` from the project root once and read the output (`AGENTS.md`, "Session start").
- No large-read warning: read files over 8 KB in parts (search, line ranges), not whole.
- No context warning: after a finished task batch, or when the user reports a large context (`/context`), offer the `handoff` skill and a new conversation (core rule 9).
- Skills: `.deutschlandgpt/skills` links to `.claude/skills`.
