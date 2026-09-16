# Manual handoff artifact

- Artifact ID: `<handoff-artifact-id>`
- Review report artifact ID: `<review-report-artifact-id>`
- State: `<awaiting-approval|awaiting-manual|uncertain|cancelled|completed|blocked>`

## Owner and authorization

- Human owner: `<owner-role>`
- Authorized action: `<exact approved action>`
- Approval evidence ID: `<approval-evidence-id or pending>`

## Prerequisites

- `<artifact-id>`: `<verified prerequisite>`

## Human procedure

1. `<verified customer procedure step>`
2. `<verified customer procedure step>`

Unknown procedure detail: `<missing detail and who can verify it or none>`

## Completion evidence

- Required output artifact: `<pr-url-artifact-id>`
- Required proof: `<non-secret evidence tied to the reviewed input>`
- Validation allowed: `<authorized read or human confirmation>`

## Uncertain operation

- Original operation ID: `<operation-id or none>`
- Observed uncertainty: `<timeout or unknown result evidence>`
- Reconciliation evidence required: `<evidence or none>`
- Retry permitted: `no while uncertain`

## Resume condition

`<exact evidence and validation needed before the workflow resumes>`

## Example quality

**Good:** Names the authorized human, exact approved action, verified procedure,
safe completion evidence, and a no-retry rule for uncertainty.

**Bad:** Inventing a console path, asking for credentials, opening a browser,
performing the write, or treating a request sent as completion.
