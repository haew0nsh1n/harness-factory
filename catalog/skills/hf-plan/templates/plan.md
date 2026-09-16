# Implementation plan artifact

- Artifact ID: `<plan-artifact-id>`
- Approved brief artifact ID: `<brief-artifact-id>`
- Brief approval evidence ID: `<approval-evidence-id>`
- Status: `<draft|awaiting-approval|approved|blocked>`

## Scope and exclusions

- Required outcome: `<approved outcome>`
- Excluded work: `<approved exclusion>`

## Verified project surfaces

| Surface ID | Observed file or interface | Evidence ID |
| --- | --- | --- |
| `<surface-id>` | `<observed project-relative path or interface>` | `<evidence-id>` |

## Tasks

### Task `<task-id>`: `<behavior>`

- Inputs: `<semantic artifact IDs>`
- Depends on: `<task IDs or none>`
- Target surfaces: `<verified surface IDs>`
- Write the focused test: `<assertion and fixture derived from the brief>`
- Red command: `<exact command observed in project tooling>`
- Expected red evidence: `<missing-behavior failure signature>`
- Minimal implementation: `<bounded change>`
- Green command: `<exact focused command>`
- Green criterion: `<observable successful outcome>`
- Regression selectors: `<exact observed selectors and rationale>`
- Outputs: `<implementation artifact ID>, <test-results artifact ID>`
- Failure or manual gate: `<blocker and resume evidence or none>`

## Final handoff

- Implementation consumer: `<workflow step ID>`
- Required artifacts: `<semantic artifact IDs>`
- Remaining blockers: `<blocker IDs or none>`

## Example quality

**Good:** Commands, paths, and interfaces are copied from authorized project
observations, while results remain stated as evidence to collect.

**Bad:** Inventing a likely file or command, claiming an unrun test passed, or
adding automatic approval, commit, deployment, or publication steps.
