---
name: hf-review
description: Review implementation against its approved intent and observed test evidence, then hand off a concrete review report. Use before customer acceptance or publication.
---

# Review before handoff

Read the approved brief/plan, implementation diff and test-results artifact.
Identify the comparison base explicitly; do not fetch or change branches without
authorization. If inputs or the comparison base are missing, stop and name them.

Review in two passes:

1. Intent: required behavior, exclusions, acceptance criteria, missing or
   unrelated changes.
2. Correctness: concrete defects, failure paths, state/enum coverage, data
   handling and trust boundaries. Follow relevant unchanged callers when needed.

For each finding report severity, file and line, motivating code, consequence,
confidence and the smallest useful corrective action. Suppress unsupported
speculation. Distinguish observed defects from unverified questions.

Output a review-report artifact with intent match, findings, test evidence
actually supplied, unresolved checks and a handoff recommendation. Important
unresolved defects block acceptance. A missing test report is not "tests passed."
Review completion alone is not approval to merge, publish a PR, or deploy.

This is a read-only review discipline: no automatic fixes, commits, external
review services, browser cookies, telemetry or customer data in web searches.

Adapted from gstack `review` at
`71f6048e8ada25180e61438abc1d98cb151fe9a7`. Changes: concise local intent/correctness
passes and evidence-based handoff; omit host bootstrap, auto-fix, external tools
and all bundled browser dependencies. Original MIT notice is included.
