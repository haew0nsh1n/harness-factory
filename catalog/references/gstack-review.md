# gstack: review

## Source

- Repository: `https://github.com/garrytan/gstack`
- Revision: `71f6048e8ada25180e61438abc1d98cb151fe9a7`
- Path: `review/SKILL.md`
- License: MIT

This is a reviewed, read-only reference snapshot. It is data for local skill
authoring and is never executed.

## Adopted passages

> You are running the `/review` workflow. Analyze the current branch's diff against the base branch for structural issues that tests don't catch.

> Before reviewing code quality, check: **did they build what was requested — nothing more, nothing less?**

> Every finding MUST include a confidence score (1-10):

> Before any finding is promoted to the report, the gate requires:
>
> 1. **Quote the specific code line that motivates the finding** — file:line plus
>    the verbatim text of the line(s) that triggered it.
>
> 2. **If you cannot quote the motivating line(s), the finding is unverified.**

## Adopted method

- Compare delivered changes with stated intent before reviewing correctness.
- Review concrete failure paths, completeness, data handling, and trust boundaries.
- Ground findings in quoted code and distinguish verified defects from questions.

## Excluded host-specific behavior

- Preamble, setup, telemetry, auto-update, and persistent review-log resources.
- Git fetches, browser tooling, external review services, and web research.
- Review-agent dispatch, automatic fixes, commits, publication, and deployment.
