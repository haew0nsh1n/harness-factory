# Implementation plan artifact

- Artifact ID: `<plan-artifact-id>`
- Approved brief artifact ID: `<brief-artifact-id>`
- Brief approval evidence ID: `<approval-evidence-id>`
- Status: `<draft|awaiting-approval|approved|blocked>`

## Scope and exclusions

- Required outcome: `<approved outcome>`
- Excluded work: `<approved exclusion>`

## Project surfaces

| Surface ID | Disposition | File or interface | Evidence IDs |
| --- | --- | --- | --- |
| `<surface-id>` | `<observed-existing|approved-proposed>` | `<observed or proposed project-relative path or interface>` | `<observation ID and, for a proposal, brief authorization ID>` |

## Tasks

### Task `<task-id>`: `<behavior>`

- Inputs: `<semantic artifact IDs>`
- Depends on: `<task IDs or none>`
- Target surfaces: `<verified surface IDs>`
- Verification mode: `<red-green|validation-only>`
- Red-green branch: `<focused test, exact command, expected missing-behavior
  failure, minimal implementation, green criterion, and regression selectors;
  or not applicable>`
- Validation-only branch: `<artifact contract, exact authorized validation
  command or inspection, acceptance criterion, and evidence; or not applicable>`
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
