# Test-first outcome classification

Read this reference after every focused red attempt for a `test-first` task and
whenever later test evidence is ambiguous. An approved `validation-only` task
does not enter this classification gate and must not be labeled red or green.

## Classification gate

Classify from the observed command, exit result, and output:

- **Valid red:** the test executes and its assertion fails for the specific
  missing behavior named by the plan.
- **Environment blocked:** collection, import, dependency, service, permission,
  fixture setup, syntax, or command-resolution failure prevents the assertion
  from exercising the behavior.
- **Pre-existing implementation:** the new test passes before a production
  change because the requested behavior already exists.
- **Flaky:** materially identical runs produce inconsistent outcomes, or the
  failure depends on uncontrolled timing or external state.
- **Unrelated regression:** another behavior fails outside the intended red
  assertion. Preserve the evidence and investigate scope; do not relabel it red.
- **Green:** the focused assertion and required setup complete successfully after
  the change. Green does not imply broader regressions were run.

## Branch actions

For valid red, implement the smallest planned change. For environment blocked,
stop and record the exact blocker and resume condition. For pre-existing
implementation, preserve customer code, record that no observed red/green cycle
occurred, and retain a meaningful regression test only when it protects the
approved behavior. For flaky evidence, do not select a passing attempt or claim
completion; isolate the uncontrolled condition within scope or block.

When a regression fails, determine whether the change caused it using observed
evidence. Do not fix unrelated failures without authorization. The regression
scope should cover direct callers, shared interfaces, state or enum consumers,
and failure paths identified by the approved plan—no narrower and no invented
full-suite claim.

For `validation-only`, record the exact approved command, observed exit result,
relevant output, acceptance decision, and any blocker. Mark the red/green cycle
not applicable; do not reinterpret validation output as test-first evidence.

## Blocked-test record

Record the semantic task ID, exact command, observed exit result, relevant output,
classification, why the intended assertion did not run, and the evidence needed
to resume. Never include credentials or secret values from output.

## Good and bad examples

**Good:** “Attempt `<attempt-id>` reached assertion `<assertion-id>` and observed
the planned missing-behavior failure; classification: valid red.”

**Bad:** “The command could not import its dependency, which is close enough to
red; tests pass after the change.” The first result is blocked and the second is
unsupported.
