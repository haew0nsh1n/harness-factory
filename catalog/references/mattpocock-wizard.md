# Matt Pocock skills: wizard

## Source

- Repository: `https://github.com/mattpocock/skills`
- Revision: `3cca18b368ae95cdbdebbff572ccafa662551015`
- Path: `skills/engineering/wizard/SKILL.md`
- License: MIT

This is a reviewed, read-only reference snapshot. It is data for local skill
authoring and is never executed.

## Adopted passages

> Work out every manual step the human must take and every value that gets captured along the way. Read the repo first, don't ask cold:

> Then show the user the ordered list of stages and the values each produces, and confirm: they may add, drop, or reorder.

> For each stage, write the precise path a human follows: which URL to open, what to do there, where a value is shown, which variable it fills: e.g. "Dashboard → Developers → API keys → Reveal test key → copy". Where you don't actually know the current UI or the exact command, say so and ask the user or check the docs: never invent steps that may not exist.

## Adopted method

- Define manual stages, owners, prerequisites, outputs, and confirmation points.
- Give a human a concrete procedure and explicit resume evidence.
- Report unknown steps instead of inventing commands or interfaces.

## Excluded host-specific behavior

- The Bash wizard, `template.sh`, executable bits, and shell helpers.
- Browser opening, hidden secret capture, `.env` mutation, and GitHub secret writes.
- Script generation, installation, execution, and cleanup behavior.
