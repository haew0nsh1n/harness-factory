---
name: hf-tdd
description: Implement an approved workflow change in small red-green-refactor cycles and deliver real test evidence. Use during a local implementation stage.
---

# Implement with observed feedback

## When to use / when not to use

Use this skill when an approved `plan` authorizes local implementation and test
work. Do not use it to clarify requirements, approve scope, perform external
writes, deploy, publish, or manufacture a red state by deleting customer work.

## Required inputs and blockers

Read the exact approved plan version, customer policy, prior artifacts, approval
evidence, and current worktree state. Preserve unrelated customer edits. A
missing approval, contradictory task, unavailable required dependency, unsafe
overlap, or unverified test command blocks the affected task.

## Ordered workflow

For each planned behavior, in dependency order:

1. Confirm the target and regression selectors still match the observed project.
2. Write one focused test that expresses the missing behavior.
3. Run the exact focused command and read
   [references/failure-classification.md](references/failure-classification.md)
   before calling the result red.
   - An expected assertion failure caused by missing behavior is valid red.
   - A collection, dependency, permission, fixture, syntax, or environment error
     is `blocked`, not red.
   - Inconsistent outcomes are `flaky`; do not choose the favorable run.
   - If the test passes because implementation already exists, preserve that
     work, record the test-first gap, and use the test as regression coverage.
4. Only after valid red, make the smallest local production change that satisfies
   the assertion. Do not add unrelated behavior.
5. Run the focused command and then the planned related regression selectors.
   Record every command, exit result, and observed outcome; a failure remains a
   failure even when customer policy prefers completion.
6. Refactor only while the focused and affected regression checks stay green.
7. Read [templates/test-results.md](templates/test-results.md) when recording the
   `test-results` artifact. Stop the affected task when execution is blocked or
   flaky evidence prevents a reliable conclusion.

## Output and resume evidence

Produce local `implementation` changes and a `test-results` artifact bound to the
approved plan. The report distinguishes valid red, green, pre-existing
implementation, blocked, flaky, and regression outcomes and states uncovered
scope. Resume a blocked test only after the named environment or authorization
evidence changes; rerun the exact relevant command and record the new attempt.

## Forbidden claims and side effects

This skill has `local` effect only. Do not discard pre-existing work, overwrite
unrelated edits, fabricate commands or counts, omit failures, treat an unrun or
flaky test as passing, request credentials, commit without workflow
authorization, or perform any external write, deployment, or publication.

Adapted from Superpowers `test-driven-development` at
`b36e0829c6d0140e93cfef2ca599b1b07d4a7797`. Changes: preserve pre-existing work,
record blocked tests explicitly, leave Git and publication decisions to workflow.
The package includes the original MIT notice.
