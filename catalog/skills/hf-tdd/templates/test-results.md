# Test results artifact

- Artifact ID: `<test-results-artifact-id>`
- Plan artifact ID: `<plan-artifact-id>`
- Implementation artifact ID: `<implementation-artifact-id>`
- Status: `<passed|failed|blocked|flaky>`

## Behavior cycles

### Behavior `<behavior-id>`

- Test evidence ID: `<test-evidence-id>`
- Red command: `<exact observed command>`
- Red outcome: `<exit result and relevant observed output>`
- Red classification: `<valid-red|environment-blocked|pre-existing|flaky|unrelated-regression>`
- Production change: `<observed changed surfaces or none>`
- Green command: `<exact observed command or not-run>`
- Green outcome: `<exit result and relevant observed output or blocker>`
- Refactor evidence: `<command and outcome or not-performed>`

## Regression evidence

- Selector `<selector-id>`: `<exact command>` — Outcome: `<observed result>`
- Scope not run: `<uncovered scope and reason or none>`

## Failures and blockers

- `<attempt-id>`: `<classification, blocker, and exact resume evidence or none>`

## Handoff

- Covered requirements: `<brief requirement IDs>`
- Remaining limits: `<observed limits or none>`
- Review inputs: `<implementation-artifact-id>, <test-results-artifact-id>`

## Example quality

**Good:** Every result is tied to an exact observed command and attempt; blocked,
flaky, and not-run checks remain visibly non-passing.

**Bad:** Adding invented counts, omitting failed attempts, converting an import
error into valid red, or claiming tests that were never run.
