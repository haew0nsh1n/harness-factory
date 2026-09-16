# Plan artifact

- Artifact ID: `<plan-artifact-id>`
- Approved brief artifact ID: `<brief-artifact-id>`
- Brief approval evidence ID: `<approval-evidence-id>`
- Status: `<draft|awaiting-approval|approved|blocked>`

## Scope and exclusions

- Required outcome: `<approved outcome>`
- Excluded work: `<approved exclusion>`

## Observed existing surfaces

| Existing surface ID | Observed file or interface | Observation evidence ID |
| --- | --- | --- |
| `<existing-surface-id>` | `<observed project-relative path or interface>` | `<observation-evidence-id>` |

## Brief-authorized proposed paths

| Proposed path ID | Proposed path | Brief authorization ID | Placement evidence ID |
| --- | --- | --- | --- |
| `<proposed-path-id>` | `<brief-supplied path or path grounded in an observed placement convention>` | `<brief-decision-id>` | `<placement-evidence-id>` |

## Tasks

### Task `<task-id>`: `<approved outcome>`

- Inputs: `<semantic artifact IDs>`
- Depends on: `<task IDs or none>`
- Existing target surfaces: `<observed existing surface IDs or none>`
- New target paths: `<brief-authorized proposed path IDs or none>`
- Downstream mode: `<test-first|validation-only>`
- Test-first branch: `<focused test, exact command, expected missing-behavior
  failure, minimal implementation, green criterion, and regression selectors;
  or not applicable>`
- Validation-only branch: `<smallest documentation or manual-artifact change,
  exact observed validation command, acceptance criterion, and observed evidence
  fields to record; or not applicable>`
- Downstream output IDs fixed by the catalog: `implementation`, `test-results`
- Output interpretation: `<test-first production change and red/green evidence,
  or validation-only artifact change and observed validation evidence with no
  red/green cycle>`
- Failure or manual gate: `<blocker and resume evidence or none>`

## Final handoff

- Downstream consumer: `<workflow step ID>`
- Required artifacts: `<semantic artifact IDs>`
- Remaining blockers: `<blocker IDs or none>`

## Example quality

**Good:** Existing surfaces cite project observations, proposed paths cite the
brief and placement evidence, and each task defines one mode with the exact
command and evidence that mode requires.

**Bad:** Inventing a likely file or command, claiming an unrun test passed, or
adding automatic approval, commit, deployment, or publication steps.
