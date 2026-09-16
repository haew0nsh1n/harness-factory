# Independently verifiable task sizing

Read this reference after verifying the approved brief and project surfaces.

## Verify before naming

### Observed existing surfaces

Use authorized project reads to identify existing files, symbols, interfaces,
dependencies, placement conventions, and test tooling. Mark these surfaces as
observed and cite the evidence. If a required existing surface cannot be
observed, mark it unresolved. Never replace an unknown with a plausible path or
command.

### Approved proposed paths

A new-file path cannot be observed as existing. Record it separately as proposed
only when the approved brief explicitly authorizes the new artifact and either
supplies the path or permits a path derived from an observed repository placement
convention. Cite both the brief decision and placement evidence. Do not describe
the proposed path as verified or existing. If authorization or placement
evidence is missing, leave the path unresolved and block the affected task.

## Choose task boundaries

A task is the smallest useful unit that ends with an independently reviewable
deliverable. An executable behavior task uses one coherent `test-first` cycle.
A documentation or manual-artifact task with no executable behavior uses a
`validation-only` branch instead. Include setup, configuration, documentation,
and cleanup in the task whose deliverable needs them. Split tasks when either
task could be rejected without rejecting the other, or when they produce
separate handoffs with independent validation.

Do not split solely by file, layer, or role when doing so creates intermediate
states that cannot be tested. Do not combine unrelated behavior merely because
the same file changes.

## Required verification detail

For each `test-first` executable behavior task record:

1. The test and assertion that would fail before the change.
2. The exact observed project command that targets it.
3. The expected failure signature that distinguishes missing behavior from an
   environment or fixture error.
4. The smallest production change needed.
5. The exact green command and observable success criterion.
6. Related regression selectors and why they bound the impact.

These are future evidence requirements. A plan must not report commands as run
or tests as passed.

For each `validation-only` documentation or manual-artifact task record the
smallest authorized artifact change, exact validation command observed in
authorized project tooling, acceptance criterion, and observed validation
evidence fields the executor must record. Do not manufacture a failing test for
prose or a human-only action. If no reliable command is available, block and
name the evidence needed rather than claiming the artifact is valid.

Both modes retain the downstream execution skill's catalog output IDs
`implementation` and `test-results`. For `test-first`, those artifacts contain
the production change and red/green evidence. For `validation-only`, they
contain the exact documentation or manual artifact change and its observed
validation command, exit result, and output, with the red/green cycle marked not
applicable.

## Handoffs and blockers

Every task names semantic input and output artifact IDs and the evidence the next
task needs. A missing command, inaccessible file, unresolved decision, or manual
gate is a blocker with a resume condition, not an invitation to improvise.

## Good and bad examples

**Good:** A `test-first` task names `<verified-test-interface>`, records
`<observed-focused-command>`, and expects `<missing-behavior-assertion>`. A
`validation-only` artifact task names `<artifact-contract-id>` and
`<observed-validation-command>` without inventing red/green results.

**Bad:** “Update the relevant files and run all tests.” It names no verified
surface, verification mode, evidence contract, or consumer handoff.
