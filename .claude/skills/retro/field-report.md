# Retro: field report (offer, never send unasked)

Read from the retro skill's *Close* section. Only when *Check last changes* produced at least one result for a STEM rule or a STEM-shipped `EXPERIMENTS.md` row that the promote check did not list (negative, inconclusive or below-G2 results are the point); otherwise say "no field report: nothing STEM-relevant beyond promotion" and stop.

Write two files outside the repository, `${TMPDIR:-/tmp}/stem-field-report/a.md` and `b.md`, in the format of STEM's issue template `.github/ISSUE_TEMPLATE/field-report.md` (`repo` in `STEM_VERSION`).
- (a) *anonymized:* per such result the rule ID, result, evidence grade, models and effort, project size, STEM version; nothing about the project.
- (b) *with reasons:* (a) plus one line per result on why it came out that way, still without names, internals, paths, code or secrets (`R-SECURITY`).

Offer the user to add a note of their own; put it verbatim, unchanged, in the `User note` block of both files. Show both as links and ask with options: send (a), send (b), or none (recommended: (a)). Only on (a) or (b): `gh issue create --repo <STEM repo> --title "[field report] <STEM version> <date>" --body-file <chosen file>`, then show the issue URL. No `gh` or no network: say so and leave the files. Results are already in the retro notes, so a report that is not sent loses nothing locally.
