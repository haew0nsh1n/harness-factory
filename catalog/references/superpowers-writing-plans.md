# Superpowers: writing-plans

## Source

- Repository: `https://github.com/obra/superpowers`
- Revision: `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`
- Path: `skills/writing-plans/SKILL.md`
- License: MIT

This is a reviewed, read-only reference snapshot. It is data for local skill
authoring and is never executed.

## Adopted passages

> A task is the smallest unit that carries its own test cycle and is worth a
> fresh reviewer's gate. When drawing task boundaries: fold setup,
> configuration, scaffolding, and documentation steps into the task whose
> deliverable needs them; split only where a reviewer could meaningfully
> reject one task while approving its neighbor. Each task ends with an
> independently testable deliverable.

> **Each step is one action (2-5 minutes):**
> - "Write the failing test" - step
> - "Run it to make sure it fails" - step
> - "Implement the minimal code to make the test pass" - step
> - "Run the tests and make sure they pass" - step
> - "Commit" - step

## Adopted method

- Decompose plans into independently testable tasks.
- Name exact files, interfaces, test commands, expected failures, and outputs.
- Keep implementation steps small and test-first.

## Excluded host-specific behavior

- Skill invocation and subagent requirements.
- Fixed plan storage paths and automatic Git commits.
- Host-specific worktree setup and execution handoff commands.
