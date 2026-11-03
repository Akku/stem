---
name: testing-practices
description: Practical test-quality lessons (isolation, realistic fixtures, deterministic time, real integrations, proof boundaries). Use when designing a test strategy, adding test infrastructure, or interpreting what a green result proves.
---

# Testing practices

Rule: `R-VERIFY`. Every check has a proof boundary; keep it visible in the task evidence.

- **Isolation:** each test gets its own instance (DOM/app/DB) and mandatory cleanup of timers, listeners, shared state; otherwise later tests are influenced.
- **Fixtures mirror reality:** include real load order and lifecycle (e.g. a harness providing a component earlier than the server does can hide bugs).
- **Determinism:** fake time and deliberately held-back responses make double clicks, races and stale polling reproducible.
- **Fakes drift:** a fake server needs maintenance together with the real API contract (shared schema/contract test).
- **Real integrations where behavior matters:** SQL and framework behavior with a real database; mocks mostly confirm expected calls.
- **TDD for logic-heavy code:** write the test and see it fail for the right reason (the missing behavior, not a typo or setup error), make it pass, refactor, in small steps; the unit scope, what to mock and which behavior to test are one decision. Skip for throwaway UI or prototypes. Deep modules (simple interface, much behavior behind it) are easier to test from outside.
- **Characterization + mutation:** characterization tests pin existing behavior before refactoring; targeted mutations show that tests detect relevant faults.
- **Layers complement each other:** unit/DOM, integration, browser, manual. A11y tools and green CI do not prove real screen reader announcements; if required, keep a manual check open.
- **Performance:** measure only under exclusive conditions (no parallel checks).
- **Repeated manual checks:** a browser or UI check done by hand a second time is the signal to propose a test framework (e.g. Playwright), see `R-DESIGN` "Propose missing tools".
- **Browser tests (Playwright):** the default desktop viewport may open a two-pane layout; run the main flows in a phone viewport. `getByText` matches substrings case-insensitively; give indicators their own element or use `exact`. A shared e2e database makes names collide: use unique ones per test.
- **Unparsable input must fail:** a check that cannot parse its input (a computed value is NaN, a file is empty) fails instead of passing silently; assert the input is valid first.
- Run suites via `scripts/run.sh`; load only failing sections of a log.

If a step did not fit or you deviated from it: `Learning: skill testing-practices: <what> -> <change>` in the task notes (`R-LEARNING`).
