# Review report artifact

- Artifact ID: `<review-report-artifact-id>`
- Implementation artifact ID: `<implementation-artifact-id>`
- Test results artifact ID: `<test-results-artifact-id>`
- Approved plan artifact ID: `<plan-artifact-id>`
- Comparison base evidence ID: `<comparison-base-evidence-id>`
- Status: `<ready|changes-requested|blocked>`

## Input completeness

- `<artifact or evidence check and observed result>`

## Intent match

- Required behavior: `<matched, missing, or unverified with evidence>`
- Exclusions: `<respected or violated with evidence>`
- Unrelated changes: `<observed changes or none>`

## Findings

### Finding `<finding-id>` — `<severity>`

- Location: `<observed project-relative file and line>`
- Motivating code: `<verbatim observed code>`
- Consequence: `<reachable observable failure>`
- Confidence: `<1-10>`
- Smallest corrective action: `<bounded action>`

## Test evidence supplied

- `<test evidence ID>`: `<observed status and limits>`

## Unresolved checks

- `<question, missing evidence, and resume condition or none>`

## Recommendation

`<ready for authorized acceptance|changes requested|blocked pending evidence>`

## Example quality

**Good:** Findings cite observed code and consequences; missing evidence stays
blocked and a no-finding report states the reviewed scope.

**Bad:** Reporting speculative defects, inventing test results, auto-fixing code,
or treating review completion as merge or publication approval.
