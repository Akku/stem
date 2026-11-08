# Advanced rules (load only when needed)

Same ID mechanism as `OPERATING_MODEL.md`: `sed -n "/<!-- RULE:${ID}:START -->/,/<!-- RULE:${ID}:END -->/p" docs/agent/ADVANCED.md`

| Rule ID | Load when |
| --- | --- |
| `R-PARALLEL` | running coding agents in parallel |
| `R-MEASUREMENT` | measuring process cost/effectiveness |
| `R-ROUTING` | choosing provider/model or local worker |

<!-- RULE:R-PARALLEL:START -->
## 14. Parallelism and worktrees

Use multiple coding agents only when there are genuinely independent workstreams.

When parallel coding is justified, isolate workers with Git worktrees or equivalent checkouts.

Do not parallelize tasks that heavily overlap in files, state, or architectural decisions. The coordination and merge cost usually cancels the apparent speedup.
<!-- RULE:R-PARALLEL:END -->

<!-- RULE:R-MEASUREMENT:START -->
## 17. Measurement: use an evidence ladder, not telemetry by default

Continuous per-task measurement can easily cost more attention and infrastructure than it saves.

Use the lightest evidence source that can answer the current process question.

### Level 0 — no extra measurement

Use existing build/test results, Backlog.md history, commits, CI, and normal task evidence.

### Level 1 — cheap process observations

Capture notable learning points when they occur. Examples of observable efficiency evidence include avoided full-log loads, fewer repeated file reads, shorter handoffs, successful session continuation, or removal of duplicated rules.

These are indicators, not proof of token savings.

### Level 2 — retrospective sampling

At retro time, inspect a representative sample of recent tasks/batches plus already-available usage/session data. Do not require agents to manually transcribe telemetry.

### Level 3 — targeted experiment

When there is a concrete unresolved question, measure just what is needed for a limited period.

Examples:

- Does batching related tasks reduce tokens/cost per accepted task?
- Does independent Codex review catch enough material issues to justify its cost?
- Does compact log summarization materially reduce context usage without harming diagnosis?
- Is a full verification command too slow for the inner loop?

### Level 4 — continuous telemetry

Introduce persistent metrics only after recurring decisions would benefit from them and collection can be mostly automatic.

The principle is:

> Save cheap evidence continuously; measure continuously only when the economics justify it.

Plausible savings should be described as hypotheses until measured.

### Standard for cost-carrying rules

Rules that cost context in every session or change every session's behavior (content of `AGENTS.md`, default model and effort, session-length threshold, communication standard) deserve more than plausibility. Other changes keep the lighter ladder above. Observational data from small projects cannot prove cause and effect; this standard makes weak evidence visible and cheap to improve:

1. **Before the change** write an entry in `docs/agent/EXPERIMENTS.md`: hypothesis, metric and expected direction, threshold, check date, confounders to note (model, effort, task size, other changes at the same time). Decide threshold and metric *before* looking at the result.
2. **Baseline:** `scripts/retro-metrics.sh --snapshot` before the change; compare later per accepted task (absolute sums mislead when the amount of work differs).
3. **One cost-carrying change at a time** where practical; otherwise name the bundle and do not attribute the effect to one part. Per-task switchable rules can alternate between tasks (A/B).
4. **Metrics inform, they are not targets** (a number that becomes a goal stops measuring). Use a second view (quality: rework, failed checks, user feedback) next to cost.
5. **Evidence grades** in every statement and entry: **G0** anecdote; **G1** observed (data, no baseline); **G2** measured before/after with preset threshold, normalised, confounders noted, one project; **G3** replicated (G2 in two or more projects, or a real A/B). Say "effective" only from G2 (and treat one project as local); recommend to other projects (`promote-learning`) only from G2; make something a STEM default only with G3 or a clear mechanical reason. Below G2 write "indication".
<!-- RULE:R-MEASUREMENT:END -->

<!-- RULE:R-ROUTING:START -->
## 18. Provider/model routing and minimal local-worker preparation

Do not build routing infrastructure before there is enough volume to justify it. Roles are provider-neutral: Claude Code, Codex, and future agents can be swapped according to capability, cost, availability, and task risk.

**Default for newcomers and small/medium projects:** a mid-tier model at medium effort (observed in the maintainer's small to medium projects: sufficient and clearly cheaper than the largest model; anecdotal, to be checked in the retro). Escalate model or effort only for a concrete reason and de-escalate afterwards; lower effort is fine for mechanical tasks. Name the reason in the task notes when escalating. Cost grows with model size, effort and session length (see `R-BATCHING`). Handing a complex task, batch or milestone to a larger model with more autonomy in its own session and branch: `handoff` skill step 6.

Use stronger hosted models for ambiguity, architecture, high-risk changes, difficult debugging, or review where subtle reasoning matters. Use normal coding models for routine implementation. Cheap or local models are candidates only for bounded low-risk work.

### Local-worker eligibility

A local model is a good candidate when the work is:

- bounded in input and expected output;
- reversible;
- low-risk;
- free of architectural/product decisions;
- free of secrets or data that should not enter that runtime;
- either read-only or protected by deterministic validation before acceptance.

Useful examples include:

- classify a bounded list of files/symbols by likely relevance to a task;
- summarize a supplied diff, commit range, or selected log excerpt without deciding pass/fail;
- cluster already-captured test failures into likely duplicate/root-cause groups;
- draft release notes, changelog text, or documentation from supplied verified facts;
- propose candidate test cases from acceptance criteria for a stronger agent/human to select;
- perform tightly bounded mechanical documentation or test-fixture edits when an exact lint/test command validates the result;
- extract structured metadata from local documents for an indexing/RAG pipeline when schema validation exists.

Prefer a deterministic script instead of a local LLM when the transformation can be expressed reliably without inference.

Do not delegate by default:

- authentication/authorization/security decisions;
- migrations, destructive operations, persistence integrity;
- public API or compatibility decisions;
- architecture or product behavior decisions;
- final task acceptance, merge authority, or interpretation of ambiguous evidence.

### Minimal preparation

Start with policy, not a router. A project only needs a short local-worker section in this file describing eligibility, exclusions, the available local runtime(s), and a simple delegation contract:

```text
purpose/question
bounded inputs
allowed outputs/files
deterministic verification
stop/escalation condition
```

Do not add task labels, queues, model routers, or automation until repeated usage proves they would reduce total cost. If the existing Backlog.md setup already has suitable labels/metadata, they may be reused rather than inventing a new scheme.

Cross-model or cross-provider review is one optional way to reduce correlated mistakes, not a mandatory workflow.
<!-- RULE:R-ROUTING:END -->


---

## Local worker policy (minimal template)

Purpose: allow cheap/local models to perform bounded low-risk work without creating a routing platform.

## Eligibility

Delegate only when the task is bounded, reversible, low-risk, contains no prohibited secrets for the local runtime, and is either read-only or has deterministic validation before acceptance.

Good starter tasks:

- classify a supplied list of files/symbols by likely relevance;
- summarize a supplied diff/commit range/log excerpt;
- cluster already-recorded test failures;
- draft release notes/changelog/docs from verified facts;
- propose test cases from acceptance criteria;
- mechanical documentation/test-fixture edits with exact lint/test verification;
- extract structured document metadata where schema validation exists.

Use a deterministic script instead if inference is unnecessary.

Do not delegate security decisions, migrations/destructive actions, public API compatibility, architecture/product decisions, final acceptance, or merge authority.

## Delegation contract

```text
PURPOSE / QUESTION:
BOUNDED INPUTS:
ALLOWED OUTPUTS / FILES:
REQUIRED DETERMINISTIC VERIFICATION:
STOP / ESCALATE WHEN:
```

## Integration rule

Start manually. Do not add routers, queues, labels, or automated model selection until repeated use demonstrates a payoff. Reuse existing Backlog.md metadata if suitable instead of creating a parallel task taxonomy.
