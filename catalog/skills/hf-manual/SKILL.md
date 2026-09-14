---
name: hf-manual
description: Hand a workflow stage to an authorized human with exact prerequisites and resume evidence. Use when an integration is missing or a step is deliberately human-only.
---

# Explicit human handoff

Read the active stage's manual owner, instructions, required artifacts,
approval gate and resume condition. Missing any of these is a blocked handoff.
Describe the exact action, who performs it, and what result they must provide.
Do not invent a dashboard path, command, connector or permission you have not
verified. Do not ask for a secret or save credentials in the execution record.

If approval is required, wait for an explicit decision by the named role before
the action. Denied approval cancels the action; silence is not approval.
An approved plan is not automatically approval for a later publication step.

Record awaiting-manual and stop. You may explain the procedure, but must not
perform its external write on the human's behalf. Continue only when the human
provides the specified result and it has been checked to the extent authorized.
Report anything that could not be verified.

If a prior action timed out or its result is unknown, record uncertain and do not
retry. First check whether the issue, PR, deployment or other result already
exists through an authorized read or human confirmation. A new run ID is not a
way to evade this check. Bind the confirmation to the original operation.

Output the required evidence artifact (for example a PR URL plus the human's
confirmation). Do not mark completed based only on intent or a request sent.

Adapted from Matt Pocock's `wizard` at
`3cca18b368ae95cdbdebbff572ccafa662551015`. Changes: explicit human procedure,
no generated shell wizard, no secret capture, no automatic URL opening or writes.
The package includes the original MIT notice.
