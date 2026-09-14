---
name: hf-tdd
description: Implement an approved workflow change in small red-green-refactor cycles and deliver real test evidence. Use during a local implementation stage.
---

# Implement with observed feedback

Read the approved plan and customer rules. Confirm required prior artifacts and
approvals. Preserve unrelated customer edits. Never infer permission to publish
or deploy from permission to edit local code.

For each behavior:

1. Write a focused test expressing the expected behavior.
2. Run it. Confirm it fails because the behavior is missing, not because the
   command, fixture or dependency is broken.
3. Implement the smallest change that satisfies the test.
4. Run that test and the related regression selectors.
5. Refactor only while tests remain green.

For a bug, first reproduce it in a regression test. Do not label a pre-existing
passing test as a red/green cycle. If implementation already exists, do not
delete the customer's work; describe the test-first gap and add a meaningful
regression test. If a test cannot run, report the exact blocker and do not
claim success or complete the implementation stage.

Output implementation changes and a test-results artifact with commands,
observed outcomes, covered requirements and remaining limits. No fabricated
counts, skipped failures, automatic external writes, or commits without the
workflow's authorization. Customer policy cannot turn a failing test into a pass.

Adapted from Superpowers `test-driven-development` at
`b36e0829c6d0140e93cfef2ca599b1b07d4a7797`. Changes: preserve pre-existing work,
record blocked tests explicitly, leave Git and publication decisions to workflow.
The package includes the original MIT notice.
