---
name: hf-review
description: Review implementation against its approved intent and observed test evidence, then hand off a concrete review report. Use before customer acceptance or publication.
---

# Review before handoff

## When to use / when not to use

Use this skill when the workflow supplies `implementation` and `test-results`
artifacts for review before acceptance or publication. Do not use it to repair
the implementation, create missing test evidence, approve a merge, or publish.

## Required inputs and blockers

Read the approved brief and plan linked by the supplied artifacts, the complete
implementation diff, the `test-results`, customer policy, and an explicit
comparison base. Do not fetch or change branches without authorization. Missing
inputs, a stale or ambiguous comparison base, or absent test evidence blocks a
clean handoff; a completion note is not test evidence.

## Ordered workflow

1. Confirm all artifacts refer to the same approved scope and identify unrelated
   or missing changes.
2. Perform the intent pass: compare required behavior, exclusions, acceptance
   criteria, and planned handoffs with the actual diff.
3. Read [references/checklist.md](references/checklist.md) for the correctness
   pass. Follow relevant unchanged callers and check failure paths, data safety,
   concurrency, trust boundaries, and complete enum/state handling.
4. For each candidate finding, identify the exact motivating code, reachable
   consequence, severity, and confidence. Suppress style preferences,
   unsupported speculation, and issues already prevented by surrounding code.
5. Distinguish verified defects from questions requiring additional evidence.
   Important unresolved defects block acceptance; missing tests never become a
   claim that tests passed.
6. Read [templates/review-report.md](templates/review-report.md) only when writing
   the local `review-report` artifact and provide a concrete handoff
   recommendation.

## Output and resume evidence

Produce `review-report` with intent match, evidence-grounded findings, supplied
test evidence, checks not performed, unresolved questions, and recommendation.
Resume a blocked review only when the missing artifact, comparison base, or
authorized evidence is available. A clean report means no supported finding was
found in reviewed scope; it is not customer acceptance or publication approval.

## Forbidden claims and side effects

This skill uses `read` plus `local` effect only for the report. Do not modify
implementation files, auto-fix findings, fetch or change branches, commit, merge,
publish a PR, deploy, use external review services, send customer data to web
search, access browser cookies, or emit telemetry.

Adapted from gstack `review` at
`71f6048e8ada25180e61438abc1d98cb151fe9a7`. Changes: concise local intent/correctness
passes and evidence-based handoff; omit host bootstrap, auto-fix, external tools
and all bundled browser dependencies. Original MIT notice is included.
