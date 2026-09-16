# Independently testable task sizing

Read this reference after verifying the approved brief and project surfaces.

## Verify before naming

Use authorized project reads to identify existing files, symbols, interfaces,
dependencies, and test tooling. If a required surface cannot be observed, mark
it as an unresolved interface with its required evidence. Never replace an
unknown with a plausible path or command.

## Choose task boundaries

A task is the smallest useful unit that carries one coherent red-green cycle and
ends with an independently reviewable deliverable. Include setup, configuration,
documentation, and cleanup in the task whose behavior needs them. Split tasks
when either task could be rejected without rejecting the other, or when they
produce separate handoffs with independent tests.

Do not split solely by file, layer, or role when doing so creates intermediate
states that cannot be tested. Do not combine unrelated behavior merely because
the same file changes.

## Required test-first detail

For each behavior record:

1. The test and assertion that would fail before the change.
2. The exact observed project command that targets it.
3. The expected failure signature that distinguishes missing behavior from an
   environment or fixture error.
4. The smallest production change needed.
5. The exact green command and observable success criterion.
6. Related regression selectors and why they bound the impact.

These are future evidence requirements. A plan must not report commands as run
or tests as passed.

## Handoffs and blockers

Every task names semantic input and output artifact IDs and the evidence the next
task needs. A missing command, inaccessible file, unresolved decision, or manual
gate is a blocker with a resume condition, not an invitation to improvise.

## Good and bad examples

**Good:** A task names `<verified-test-interface>`, records
`<observed-focused-command>`, expects `<missing-behavior-assertion>`, and hands
off `<implementation-artifact-id>` plus `<test-results-artifact-id>`.

**Bad:** “Update the relevant files and run all tests.” It names no verified
surface, testable boundary, expected red evidence, or consumer handoff.
