---
name: hf-manual
description: Hand a workflow stage to an authorized human with exact prerequisites and resume evidence. Use when an integration is missing or a step is deliberately human-only.
---

# Explicit human handoff

## When to use / when not to use

Use this skill when the workflow supplies a `review-report` and the next action is
deliberately human-only or lacks an authorized integration. Do not use it to
perform the external write, obtain secrets, infer approval, or bypass a missing
owner or procedure.

## Required inputs and blockers

Read the active stage, `review-report`, manual owner, instructions, required
artifacts, approval timing, and resume condition. Missing any of these blocks the
handoff. A plan approval does not authorize a later publication. Never invent a
dashboard path, command, connector, account, permission, or completion evidence.

## Ordered workflow

1. Confirm the named owner is authorized for this exact action and that required
   inputs identify the reviewed version to act on.
2. If approval is required before the action, wait for an explicit decision from
   the named role. Denial records `cancelled`; silence records
   `awaiting-approval`.
3. Define the ordered human procedure from verified customer instructions. Name
   each prerequisite, human action, produced value, and safe evidence to return.
   If a step is unknown, say so and request verification instead of inventing it.
4. Read [templates/handoff.md](templates/handoff.md), write the handoff, record
   `awaiting-manual`, and stop. Do not perform the action on the human's behalf.
5. If a prior write timed out or its result is unknown, read
   [references/uncertain-writes.md](references/uncertain-writes.md). Record
   `uncertain`, do not retry, and reconcile the original operation through an
   authorized read or human confirmation.
6. Resume only when the specified completion evidence is returned and checked to
   the extent authorized. Report anything that could not be verified.

## Output and resume evidence

Produce the `pr-url` artifact only after the authorized human supplies the real
PR URL and confirmation required by the stage. Bind it to the reviewed input and
approval evidence. A request sent, intent to publish, or unverified URL is not
completion. Until then, output the handoff state and exact resume condition
without fabricating `pr-url`.

## Forbidden claims and side effects

This skill has `manual` effect: the agent performs no external write. Do not open
browsers, run publication commands, capture or store credentials, mutate secret
files, auto-approve, retry an uncertain write, commit, push, create a PR, deploy,
or claim completion without verified evidence.

Adapted from Matt Pocock's `wizard` at
`3cca18b368ae95cdbdebbff572ccafa662551015`. Changes: explicit human procedure,
no generated shell wizard, no secret capture, no automatic URL opening or writes.
The package includes the original MIT notice.
