# Lossless issue update rules

Read this reference before reading, creating, or updating a local Markdown issue.

## Path and identity validation

- Resolve the configured issue directory and target beneath the repository root.
- Reject absolute input, traversal, symlinks, and any resolved escape.
- Require one `<issue-id>.md` file whose basename and frontmatter `id` match.
- Treat an existing target on create as a duplicate; never replace it silently.
- Treat a missing target on update as blocked; never create it implicitly.

## Schema and state validation

Require scalar `id`, `title`, `status`, `created`, and `updated` values plus list
values for `owners` and `labels`. Accept only the statuses declared by the entry
skill. Validate the requested target state before writing. Do not infer a state
transition from prose or convert malformed input to a convenient value.

## Lossless updates

Parse the existing document into known frontmatter fields and ordered body
sections. Change only fields or sections named by the authorized request, except
for the required `updated` value. Preserve `created`, unknown frontmatter fields,
unknown sections, section order, and untouched user text. New issues use the
template; updates do not regenerate the whole file from the template.

## Conflicts and duplicates

For create, use an authorized no-clobber operation that atomically creates the
target only if it does not exist. A prior existence check followed by an
unconditional write is not sufficient.

For update, keep the bytes, digest, or version originally read and use an
authorized conditional replacement that atomically replaces the target only if
that observed version is still current. A changed target is a conflict: retain
both versions as evidence, report the conflict, and request reconciliation; do
not overwrite, silently merge, or choose one version.

Use only a repository or runtime mechanism whose atomic guarantee has been
verified for the target. Block the write when either guarantee is unavailable
for the requested operation. If multiple files claim the same `id`, stop and
report every observed candidate.

After an authorized write, re-read the file and validate identity, schema,
required sections, preserved content, requested changes, and safe path. Report
only observed results. A local write never authorizes Git publication.

## Good and bad examples

**Good:** Update only `<requested-field>`, preserve `<unknown-field>` and
`<user-section-heading>`, then report the exact validated relative path.

**Bad:** Re-render the existing issue from the minimum template, drop unknown
content, resolve a concurrent edit silently, then commit and push it.
