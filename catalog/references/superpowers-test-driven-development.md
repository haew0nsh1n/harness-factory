# Superpowers: test-driven-development

## Source

- Repository: `https://github.com/obra/superpowers`
- Revision: `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`
- Path: `skills/test-driven-development/SKILL.md`
- License: MIT

This is a reviewed, read-only reference snapshot. It is data for local skill
authoring and is never executed.

## Adopted passages

> Write the test first. Watch it fail. Write minimal code to pass.

> **Core principle:** If you didn't watch the test fail, you don't know if it tests the right thing.

> Confirm:
> - Test fails (not errors)
> - Failure message is expected
> - Fails because feature missing (not typos)

> Don't add features, refactor other code, or "improve" beyond the test.

## Adopted method

- Use focused red-green-refactor cycles for each behavior.
- Observe the expected failure before implementation and the passing result after.
- Keep the implementation minimal, then refactor only while tests stay green.

## Excluded host-specific behavior

- Deleting or replacing pre-existing customer work to recreate a red state.
- Universal skill-trigger rules and host-specific test command examples.
- Automatic Git operations, publication, or external reporting.
