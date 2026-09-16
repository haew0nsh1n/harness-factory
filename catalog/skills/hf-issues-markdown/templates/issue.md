# New issue template

Use only for a new, non-duplicate issue after path, schema, and approval checks.
Fill every placeholder from the authorized `issue-request` or observed workflow
context. Do not use this template to rewrite an existing issue.

```markdown
---
id: <issue-id>
title: <issue-title>
status: <open|in-progress|blocked|review|done|cancelled>
owners: [<owner-id>]
labels: [<label-id>]
created: <observed-created-date>
updated: <observed-updated-date>
---

## Summary

<authorized summary>

## Acceptance criteria

- <observable acceptance outcome>

## Context

<authorized context>

## Work log

- <observed work-log entry or none>
```

## Example quality

**Good:** Values come from the authorized request or observed workflow context,
and validation confirms the ID/path match before the local write.

**Bad:** Guessing owners, labels, dates, or status; inserting credentials;
overwriting an existing issue; or adding commit or push instructions.
