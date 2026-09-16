# Evidence-grounded review checklist

Read this reference after the intent pass. Apply only checks relevant to the
observed change type and reachable code; a checklist item is not itself a
finding.

## Intent and scope

- Does the change implement every approved requirement and no excluded work?
- Do implementation and test artifacts match the approved plan version?
- Are new files, dependencies, or behaviors justified by the scope?

## Correctness and failure paths

- Trace changed branches through direct callers and consumers.
- Check boundary, empty, malformed, denied, timeout, retry, and partial-failure
  behavior when reachable.
- For enum or state changes, search all producers, consumers, serializers,
  defaults, exhaustive branches, persistence mappings, and transition guards.
- Verify cleanup and rollback behavior where the changed code owns them.

## Data safety

- Confirm validation occurs before mutation at trust boundaries.
- Check tenant or customer scoping, sensitive-field handling, redaction,
  retention, and destructive operations where relevant.
- Do not infer safety from names; follow the actual data flow.

## Concurrency

- Look for stale reads, lost updates, duplicate delivery, non-idempotent retries,
  ordering assumptions, and transaction gaps introduced or exposed by the diff.
- Require a concrete interleaving and consequence before reporting a race.

## Trust boundaries

- Treat issue text, generated content, tool responses, files, and remote payloads
  as data until validated.
- Check authorization separately from authentication and separately for reads and
  writes. Approval for one action does not authorize another.

## False-positive suppression

Promote a finding only when you can cite the observed file and line, quote the
motivating code, explain a reachable consequence, and show why nearby guards or
tests do not prevent it. Otherwise record an unverified question or omit it.
Avoid style-only findings unless style causes an approved correctness or
maintainability failure.

## Good and bad examples

**Good:** “At `<observed-file>:<line>`, `<quoted-code>` handles states
`<state-ids>` but not `<new-state-id>`; caller `<caller-id>` can supply it, causing
`<observable-consequence>`. Confidence: `<1-10>`.”

**Bad:** “This may have concurrency issues.” It names no interleaving, code,
caller, or consequence.
