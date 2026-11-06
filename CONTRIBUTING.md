# Contributing to STEM

STEM grows through retros, not by stockpiling (`R-DECISION`). A change belongs in STEM when it is a validated learning from real use, not an idea. This repository is public: no project or company internals, no customer data, no credentials.

## What to contribute

- **A validated learning** (rule, pitfall, procedure): use the `promote-learning` skill in your own project. It strips project details, picks the target file and opens the pull request for you.
- **A bug or gap in STEM itself** (script, setup flow, wrong text): open an issue or a pull request with the problem, the change and how you checked it.

Cost-carrying changes (content of `AGENTS.md`, default model/effort, session-length threshold, communication standard) need an entry in `docs/agent/EXPERIMENTS.md` before the change, and evidence grades follow `R-MEASUREMENT`. A recommendation needs grade G2 (measured before/after), a STEM default needs G3 or a mechanical reason; lower grades go in as labelled hypotheses.

## Pull request checklist

1. Branch `learning/<short-topic>` (learnings) or `fix/<short-topic>`; never push to `main`.
2. `python3 .github/stem-check.py` passes (on Windows: `py -3 .github/stem-check.py`). It checks rule markers, script syntax, the script fixture tests, skill frontmatter, version consistency and the 7.5 KB budget of `AGENTS.md`.
3. New or changed scripts in `scripts/` get a fixture test first in `.github/tests/test_scripts.py` (`retro-run.py`: `.github/tests/test_retro_run.py`) (realistic sample input built in a temp dir); stem-check runs it.
4. One rule per place (`R-INSTRUCTIONS`): reference rule IDs, do not copy rule text. Agent instructions stay in English; human docs exist in English and German.
5. Describe in the PR: problem, change, evidence (anonymised, with model, effort and task size).
6. Add a short `CHANGELOG.md` entry (what changed, who benefits) when users of STEM are affected.

## Maintainers

Versions and tags are set by the maintainer with `.github/bump-version.sh X.Y.Z`; contributors do not bump versions.
