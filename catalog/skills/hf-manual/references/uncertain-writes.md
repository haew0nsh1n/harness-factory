# Reconcile uncertain external writes

Read this reference when an authorized human reports a timeout, lost response,
interruption, or any other case where an external write may already have
happened.

## Safety rule

Unknown outcome is `uncertain`, not failed. Do not retry, generate a replacement,
or use a new run ID until the original operation is reconciled. Retrying can
create duplicate issues, PRs, deployments, or other irreversible side effects.

## Reconciliation sequence

1. Record the original operation ID, intended effect, reviewed input artifact,
   authorized owner, approval evidence, attempt time, and observed uncertainty.
2. Identify an authorized, read-only lookup keyed to the original operation. If
   no such lookup is verified, ask the human owner to inspect the system.
3. Accept only evidence that distinguishes the original operation from a similar
   one. Do not ask for credentials or secret values.
4. If the original effect exists, validate the required completion evidence and
   resume without another write.
5. If authorized evidence proves the original effect did not occur, return to
   the workflow's approval gate. Previous approval remains valid only if policy
   explicitly binds it to the retried action and unchanged input.
6. If existence remains unknown, stay `uncertain` and state the exact evidence
   needed to resume.

## Good and bad examples

**Good:** “Operation `<operation-id>` is uncertain. Do not retry. Resume when
`<authorized-owner>` returns evidence that uniquely identifies whether the
original operation exists.”

**Bad:** “The timeout probably means failure, so submit again with a new ID.”
This risks a duplicate external write and evades reconciliation.
