# Studio Interview and CLI Distribution

Date: 2026-09-15

Status: Direction and requested revisions approved. Azure OpenAI uses
DefaultAzureCredential; separate package signing is excluded from this MVP.

## 1. Outcome and sequence

Extend the existing authoring/registry application without replacing its Python
core, approval lifecycle, or generated package format. Deliver in this order:

1. Refresh the frontend around a consultant's interview workspace.
2. Connect published workflow assets to an authenticated local CLI installer.
3. Complete the LLM interview and structured profile/workflow/scenario editors.

The planning agent is Astra. All implementation tasks use `gpt-5.6-sol`.
The globally installed `frontend-design` skill is reused; do not reinstall it.
No telemetry, automatic upgrade, uninstall, standalone skill/plugin distribution,
cloud provisioning, customer-system execution, separate package signatures,
Key Vault, or private signing keys are included.

## 2. Existing behavior to preserve

- Next.js/React portal, FastAPI API, PostgreSQL, and isolated builder worker.
- Canonical JSON profile/workflow/scenario contracts and server-owned catalog.
- Tenant-scoped queries and author/reviewer/registry-admin/developer roles.
- Exact-digest design/version approvals; edits invalidate effective approval.
- Published versions and artifacts are immutable.
- `available`, `verified`, `approved`, `published`, `installed`, and `ready`
  remain distinct states. An LLM reply is not validation or approval evidence.
- The dependency-free `harness_factory` source invocation remains usable.
  The packaged web application continues to require Python 3.12.
- `harness_factory.install.plan_install` and `apply_install` remain the install
  authority. The existing implementation reports partial installation and
  explicitly has no rollback; this project must not claim transactionality.
- Builder egress remains disabled; LLM requests run in the API, never the worker.

## 3. Product and visual direction

Subject: a consultant turning an SDLC conversation into an explicitly reviewed
workflow. The primary page's job is to ask the next relevant question and show
what the conversation has established, not to display decorative metrics.

### Visual tokens

| Token | Value | Purpose |
| --- | --- | --- |
| Canvas | `#F3F6F8` | Quiet slate workspace |
| Surface | `#FFFFFF` | Conversation and editable documents |
| Ink | `#172B3A` | Primary type and navigation |
| Muted | `#526775` | Secondary text |
| Action | `#087F83` | Primary interaction and current step |
| Border | `#D4DFE5` | Grouping and inactive connections |

Semantic success/warning/error colors remain separately named tokens with
contrast-checked foreground/background pairs. Do not distinguish states only
by color. Avoid gradients, decorative charts, and a generic marketing hero.

Use a restrained Trebuchet MS/system fallback display stack, a system UI
body stack with Korean-capable fallbacks, and system monospace for digests.
No runtime font CDN, remote imagery, or new font dependency is needed.
Display typography is larger and slightly tighter; body copy stays readable.

The signature element is an evidence rail: confirmed facts, assumptions, and
unknowns remain visually separate beside the active question, with links back
to their source turn. A fact moves into the confirmed group only after a human
action, not after a model labels it confidently.

```text
Desktop
+-------------+--------------------------+----------------------+
| Studio      | Customer / saved status  | Evidence               |
| SDLC stages | Current question         | Confirmed facts        |
|             | Conversation             | Assumptions            |
| Registry    | Answer / send            | Unknowns               |
|             | Review proposed changes  | Proposed workflow      |
+-------------+--------------------------+----------------------+

Mobile: page header -> stage selector -> conversation ->
        explicit Evidence / Draft tabs -> answer composer
```

Phase 1 refreshes the shell, dashboard, studio list/detail, and registry with a
shared token/component language. It supplies the workspace layout and honest
empty states; it must not fabricate a working interview before its API exists.
Phase 3 adds the working `/studio/interviews/new` and
`/studio/interviews/[id]` routes and links them from Studio.

Use Korean user-facing copy consistently across touched workflows, preserving
technical identifiers and data. Buttons name their result: start interview,
send answer, confirm fact, review changes, save draft, validate, approve digest.
Expose loading, failure, empty, saved/unsaved, and stale-revision states.
Ensure keyboard access, visible focus, accessible labels, reduced motion,
320px-width support, and no destructive layout shift.

Rejected alternatives: a chatbot-only page hides evidence and review; a
canvas-first editor makes interviews depend on learning graph manipulation.
Keep the evidence workspace with ordinary forms and a read-only flow preview.

## 4. Python runtime and Azure identity

Adopt `uv` for dependency resolution, a committed `uv.lock`, local commands,
test commands, and the Python Docker build. Use `uv sync --frozen` for installs
from the lock and `uv run` for application/test entry points. Preserve the
documented optional private-feed override without committing feed credentials.
Install development/test extras only in development/test environments.

Azure CLI discovery and a minimal keyless inference request established:

- Resource: `proj-aimain`, resource group `rg-aimain`.
- Endpoint: `https://proj-aimain.cognitiveservices.azure.com/`.
- Deployment: `gpt-5.6-sol`.
- Responses endpoint: `/openai/v1/responses`.
- Minimal request with `store: false` returned `completed` and `OK`.

These are deployment settings, not hardcoded domain defaults. Introduce
`HF_AZURE_OPENAI_ENDPOINT`, `HF_AZURE_OPENAI_DEPLOYMENT`, and optional
`HF_AZURE_MANAGED_IDENTITY_CLIENT_ID`.

The Python adapter uses the OpenAI SDK, `DefaultAzureCredential`, and the Azure
Identity token provider with scope
`https://cognitiveservices.azure.com/.default`. Use the default credential chain
in both local and hosted environments, as explicitly requested by the user.
Local development can resolve the existing Azure CLI login; Azure hosting can
resolve managed identity. Pass the optional managed identity client ID into
`DefaultAzureCredential` when configured. Do not select separate credential
classes by environment or add an API-key/client-secret configuration path.
Reuse clients and close them with application lifespan. Never forward the
browser's token to Azure OpenAI.
Registry user authentication and the API's model identity are separate.

Keep endpoint, deployment, and identity server-side. Missing configuration
disables interview inference with an explicit `llm_not_configured` response;
it does not stop existing authoring/registry use. Authentication, rate-limit,
timeout, refusal, and malformed model responses have distinct safe error codes.
Do not silently use a different deployment or generate synthetic success.

Local keyless development runs the API under host `uv` so it can use `az login`.
Do not mount `~/.azure` into containers, copy tokens into environment variables,
or assume a developer's login exists in Docker. Keep the original local Compose
stack working for non-LLM functions and document a host-API development mode.
Azure-hosted containers require a real managed identity and inference RBAC.
Do not create resources or grant roles as a side effect of implementation.

## 5. LLM interview domain

### Persistence and permissions

Add tenant-owned `InterviewSession`, `InterviewTurn`, and `InterviewProposal`
tables. Include organization ID in every read/write/delete and foreign-key
relationship; only authors/org-admins may operate on interviews. Session data
includes owner, name/customer reference, revision, consent version/time, state,
confirmed evidence, selected workflow scope, timestamps, and expiry.

States: `active`, `awaiting-confirmation`, `completed`. Failed inference is a
turn outcome, not a successfully advanced interview. Session deletion removes
its turns and unaccepted proposals, while leaving an already-created design.
Audit the deletion by identifiers only.

Use a configurable retention interval, initially 30 days from last activity,
and an explicit `uv run python -m web.api.interviews.cleanup` command for expiry.
Expire access at the API boundary even if cleanup has not run. Document that
database backups have separate operator-controlled retention.

### Endpoints and concurrency

- `POST /api/interviews`: create with explicit consent and a client-generated
  request ID; ask the first question. Retrying creation must not create another
  session or duplicate the first inference operation.
- `GET /api/interviews`: list current organization's sessions.
- `GET /api/interviews/{id}`: resume session, turns, evidence, proposals.
- `POST /api/interviews/{id}/turns`: submit answer with expected revision and
  client-generated request ID.
- `POST /api/interviews/{id}/confirmations`: explicitly confirm or reject
  proposed evidence with expected revision.
- `POST /api/interviews/{id}/proposals`: request canonical draft proposal.
- `POST /api/interviews/{id}/apply`: accept exact proposal digest and expected
  interview/design revision, creating or updating an existing draft design.
- `DELETE /api/interviews/{id}`: delete session and its conversation data.

Concurrent/stale writes return 409; do not overwrite newer answers or edits.
Enforce request-ID uniqueness within a session. Persist an accepted user turn
and inference-operation identity before calling the model; do not hold a DB
transaction or row lock across network inference. A completed request can be
read again without another inference call. A timed-out request must not
automatically duplicate messages; explicit retry reuses the logical operation.
Concurrent submit/delete/completion must not resurrect deleted data.

### Model boundary

Implement a replaceable `InterviewModel` interface and Azure OpenAI adapter.
The model has no tools, file access, connectors, secrets, approvals, or
publication capability. The prompt follows the existing adaptive SDLC interview:
start with a concrete bottleneck, cover relevant lifecycle stages, distinguish
facts/assumptions/unknowns, and select one workflow.

Use Responses structured output and strict Pydantic parsing with unknown fields
rejected. A turn response contains one next-question string (or a final review
prompt), proposed evidence with source turn IDs, stage coverage, and proposed
scope. The server, not the model, owns IDs, revisions, consent, and lifecycle.
Display model text as escaped text, not raw HTML.

Draft generation returns typed candidate profile/workflow/scenario documents.
Use only server-approved catalog IDs and declared capabilities. The model
cannot invent catalog bodies, connector verification, behavior-evaluation
receipts, approval identities, or approval timestamps. Server-owned catalog
snapshots come from the existing configured catalog service.

Default bounds: 8,000 characters per answer, 60 turns per session, 64,000
characters of total model context, and 8,192 maximum output tokens. A normal
turn requests a lower output limit than a full draft. Use a 60-second model
timeout and at most one transient retry within an overall request deadline.
If context/session limits are exceeded, explain the limit and allow review or
deletion; do not silently omit conversation history or make another model call.
Do not promise a live interview succeeds merely because the minimal smoke
request succeeded; structured output gets a separate opt-in live check.

### Human confirmation and canonical contracts

Evidence suggestions and draft documents are proposals. Present proposed
changes and unknowns before applying them. Human confirmation of a fact is not
design approval. Apply only the exact proposal digest the user reviewed.

Existing core workflow JSON requires its `approved` marker. Add an explicit
scope-confirmation action for the human to supply that confirmation; derive
actor and time on the server and display what it means. Do not let model
output set it, and do not confuse it with subsequent exact-digest reviewer
approval. Missing confirmation remains a visible validation finding.

Applying to an existing design invokes the existing draft replacement path,
clears effective approval, and requires validation/review again. Use an atomic
expected-digest/revision guard for both form saves and proposal application.
Never discard unmapped JSON fields when switching between form and JSON views.

## 6. Structured editing

Keep canonical JSON as the single representation; add typed form adapters.

- Profile: customer, lifecycle current/desired process, roles, pains, success
  criteria, glossary, constraints, facts/evidence, assumptions, unknowns,
  declared systems, and tracker provider/connection/capabilities.
- Workflow: goal/trigger, inputs/outputs, rules, steps, dependencies, selected
  skill, tools/effect, approval timing/role, completion/failure, manual handoff,
  and traceability. Show an accessible read-only dependency preview.
- Scenarios: `id`, `given`, `expect`, and `forbidden`, inside the existing
  `schema_version`/`workflow`/`mode`/`scenarios` document.
- Catalog: select only authoritative entries; do not edit skill bodies.

Tracker choices remain Git+Markdown, GitHub Issues, and Jira. Skill/MCP
availability never proves capability, authentication, or permissions.
Unknown mandatory fields block validation rather than receiving plausible
defaults. Preserve existing advanced JSON editing with explicit parse errors,
dirty-state warnings, and lossless round trips.

## 7. CLI distribution MVP

### Authentication and package surface

Add an `hf` entry point in a separate `hf_cli` package, leaving
`python -m harness_factory` intact. Package CLI dependencies as an extra:
HTTP client, MSAL, and OS keyring.

Commands:

```text
hf login --registry URL --tenant ID --client-id ID --scope SCOPE
hf search QUERY
hf info SLUG[@VERSION]
hf install SLUG@VERSION --target PATH
hf install SLUG@VERSION --target PATH --approve DIGEST
```

Production login uses Entra device authorization with a configured public-client
app and delegated API scope. Validate server access through `/api/whoami`; do not
infer organization or roles from CLI input. Store the MSAL token cache only in
an OS credential store, keyed by registry/tenant/client identity. A missing or
unsafe keyring is a visible error, never a plaintext fallback. Store non-secret
registry settings separately. Support timeout, denied
login, expired sessions, and safe sign-out/cache removal as part of auth.

A separately flagged loopback-only development mode may use existing development
identity headers, but never infer this mode from an HTTP URL or failed login.
Tests use injected auth clients. Production registry URLs require HTTPS and
must not include credentials; reject unexpected redirects.

### Authenticated online delivery

Keep the current immutable registry manifest/digest unchanged. Add delivery
metadata containing schema version, organization ID, asset/version IDs,
manifest digest, artifact SHA-256, and byte length. Read metadata through the
authenticated configured registry for every preview and apply; it is not a
signed envelope or an offline authorization receipt.

The trust boundary is the explicitly configured registry over HTTPS with
normal certificate verification. Entra login establishes the caller identity;
server-side organization/role checks establish download authorization.
SHA-256 binds downloaded artifact bytes to metadata received from that trusted
server; it does not independently authenticate the publisher. This explicitly
narrows the previous platform design's signed-distribution requirement for the
current internal MVP. No signing provider, private key, public-key trust store,
signature badge, or key-rotation mechanism is implemented.

Reject metadata for a different organization, asset, version, or manifest.
Cached metadata does not authorize offline apply. A compromised authoritative
registry remains outside this mechanism's protection: a hash and artifact
obtained from the same compromised source could both be replaced. Independent
publisher verification for offline/mirrored distribution is a future feature.

Add tenant-scoped delivery metadata and artifact download endpoints under
`/api/registry/versions/{id}`. Both require developer/org-admin permission and
currently published status. Artifact paths are resolved only from stored
version metadata; never accept caller filesystem keys. Recheck lifecycle and
digest on apply, even when a CLI cache exists. Revoke/deprecate blocks new
installs in this MVP; already-installed content remains untouched.

Direct authenticated API streaming is sufficient for this phase, instead of
presigned object-storage URLs. Do not expose artifact volumes, API bearer tokens,
or internal storage keys as public download URLs.

### Download, preview, and apply

Bound transfer and extraction: 100 MiB archive, 256 MiB expanded bytes,
10,000 entries, and 16 MiB per file. Reject absolute/parent paths, duplicate
members, symlinks, hard links, devices, FIFOs, sparse files, excessive sizes,
and unsupported archive types. The current worker produces uncompressed tar.
Do not use unrestricted `extractall`.

Verify authenticated metadata and streamed artifact digest, safely extract, and run the
existing package checker before preview. Cache verified source in a private,
stable directory keyed by organization/version/artifact digest. This stable
path is mandatory: the existing installer binds the source path into its
preview digest, so recreating a random temp directory on apply would invalidate
every approval. Revalidate cached bytes and reject symlinked cache paths.

Preview reports file actions, relevant text diffs, conflicts, and the exact
existing installer digest without writing the target. Diffs are local only.
Apply requires that digest, a fresh authenticated delivery/lifecycle check, the same source
path/content, and unchanged target state, then calls `apply_install`.
Preserve unrelated customer files and existing receipt semantics.
Installation success does not claim behavior evaluation or environment readiness.
Expose safe typed CLI failures with nonzero exit status and no token-bearing
tracebacks. Clean interrupted downloads and expired unused cache entries;
do not delete a valid preview source without making expiry explicit to the user.

## 8. Privacy boundary

The user explicitly approved this narrowly scoped change to the previous
no-prompt-persistence boundary: interview text can be stored in tenant-scoped
interview records and sent to the configured Azure OpenAI deployment.

Before the first call, show the destination/service, retained data, retention
period, deletion behavior, and prohibition on secrets/code/issue bodies.
Require explicit consent and persist its version/time. This is not permission
to collect repository contents, use customer connector credentials, or send
data to another model/provider. Use `store: false` on Responses requests.

Reject recognizable secret patterns before storage/inference; do not claim
pattern detection can guarantee arbitrary free text contains no sensitive
data. Give a clear warning and do not request attachments or repository imports.
Audit/log only operation identifiers, safe status codes, durations, and counts;
never log request/response bodies, bearer tokens, or exception text from the
provider. Draft confirmation copies accepted structured business information
to the design; deleting the interview does not silently delete that design.

## 9. Delivery and evidence

Required coverage:

- Existing core and web behavior remains green.
- Portal component tests plus typecheck/build; keyboard/mobile/desktop browser
  checks at 320, 768, and 1440 pixels, including empty/error/dirty states.
- Tenant isolation and authorization for every new endpoint.
- Interview consent, source-linked proposals, stale/concurrent revisions,
  deletion during inference, idempotency, expiry, refusal, limits, and retry.
- Model attempts to set approval/catalog/tools are rejected.
- Form/JSON round trips preserve every supported and unmapped field.
- Package-installed `hf` entry point works outside the source checkout.
- CLI auth-cache safety, TLS/redirect policy, metadata identity/digest validation, corrupted/traversal
  archives, interrupted downloads, stable preview/apply, revoked versions,
  stale approvals, and customer-file preservation.
- PostgreSQL migrations upgrade/downgrade and real lifecycle acceptance.
- Opt-in synthetic Azure live interview uses the discovered deployment with
  keyless auth; never make live Azure calls during the default test suite.

Acceptance path: interview -> confirm evidence/scope -> review draft -> save ->
validate -> exact-digest approval -> build -> version review/publish -> CLI
search/info -> authenticated download -> preview -> digest-approved install into a
separate repository -> identify the generated workflow entry.

Local mocked identity coverage is not proof of production Entra login
or managed-identity model access. Actual Entra public-client/API registration,
member mapping, and Azure-hosted model identity/RBAC are deployment prerequisites.
CLI delivery does not require Key Vault or any package-signing keys.
Report anything not exercised against the real deployment as unverified.

## 10. Implementation boundaries

Deliver focused modules:

- UI: shared styles/shell, interview workspace/evidence components, typed forms.
- `web/api/interviews/`: schemas, persistence, lifecycle, model adapter,
  proposals, routes, cleanup.
- `web/api/distribution/`: delivery metadata, authorized artifact streaming.
- `hf_cli/`: arguments, configuration/auth, registry client, archive/cache,
  install orchestration.
- Existing design service/repository: shared authoritative catalog access and
  optional expected-revision/digest guards without breaking existing callers.
- Runtime: `pyproject.toml`, `uv.lock`, Dockerfile, development setup, migrations.

Do not split into microservices or add an agent framework for one structured
model adapter. Decompose implementation tasks around these boundaries, with
explicit phase dependencies and targeted regression commands.
