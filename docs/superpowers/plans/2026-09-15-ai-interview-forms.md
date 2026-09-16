# AI Interview and Structured Forms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let consultants conduct a resumable Azure OpenAI interview and explicitly turn its proposals into editable, reviewable workflow designs.

**Architecture:** Add a tenant-scoped interview domain with short database transactions around a tool-free structured model adapter. Integrate the phase-1 evidence workspace and lossless form adapters with the existing canonical design/approval/build pipeline.

**Tech Stack:** Python 3.12/uv, FastAPI, SQLAlchemy/Alembic, Azure Identity DefaultAzureCredential, OpenAI Responses, React/TypeScript, Vitest/Playwright.

**Spec:** `docs/superpowers/specs/2026-09-15-studio-interview-cli-design.md`

## Global Constraints

- This is phase 3, after visual refresh and CLI distribution.
- All implementation agents use `gpt-5.6-sol`.
- Azure OpenAI uses `DefaultAzureCredential` and Entra token scope `https://cognitiveservices.azure.com/.default`; no API-key path.
- Configured deployment is `gpt-5.6-sol`; do not silently select another model.
- Python dependency and execution commands use uv and the committed lock.
- One question per turn; facts require human confirmation; model output cannot approve, publish, execute tools, or invent verification evidence.
- Store conversation only after consent, within its tenant, with 30-day default retention and explicit deletion.
- Never log prompts, replies, credentials, provider exception bodies, or customer code.
- 8,000 characters per answer, 60 turns per session, 64,000 context characters, 8,192 maximum output tokens.
- Model timeout 60 seconds; at most one transient retry within an overall deadline.
- Keep existing catalog authoritative and preserve canonical JSON fields and existing approval invalidation.
- No worker egress, credential-directory mounts, runtime font CDN, telemetry, or package signing.
- Apply required commit trailers and commit only owned files.

## File Structure

- `web/api/interviews/{schemas,errors,model,azure_model,prompt}.py`: strict proposal contracts and isolated inference.
- `web/api/interviews/{models,repository,service,routes,cleanup}.py`: tenant persistence and lifecycle.
- `web/api/interviews/{proposals,catalog,privacy}.py`: safe draft assembly, catalog selection, input boundaries.
- `web/api/config.py`, `main.py`, `db.py`, `alembic/versions/0005_interviews.py`: runtime/lifespan and database wiring.
- `web/api/designs/{schemas,repository,service,routes}.py`: optional atomic revision/digest guards, reused by forms/proposals.
- `web/portal/src/lib/{interview-types,design-forms}.ts`: typed API and lossless document adapters.
- `web/portal/src/components/studio/{InterviewPageContent,ProfileForm,WorkflowForm,ScenarioForm,DraftReview}.tsx`: live workspace and editors.
- `web/portal/src/app/studio/interviews/{new,[id]}/page.tsx`: interview creation/resume.
- `web/portal/src/lib/api.ts`, `app/api/control-plane/[...path]/route.ts`: DELETE support without weakening proxy/auth.
- `web/tests/test_interview_*.py`, `web/portal/src/components/studio/__tests__`, `web/portal/e2e/interview.spec.ts`: contracts and acceptance.
- `web/acceptance/interview_flow.py`, `README.md`: opt-in live smoke and documented end-to-end workflow.

### Task 1: Strict LLM adapter and DefaultAzureCredential

**Files:** Create schema/error/model/Azure/prompt modules, new model tests;
modify config/lifespan and manifest/lock. Consult official Microsoft code
samples for current OpenAI Responses + Azure token-provider APIs before coding.

**Interfaces:**

```python
class SuggestedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    statement: str
    kind: Literal["fact", "assumption", "unknown"]
    source_turn_ids: list[str]

class InterviewReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    stage: Literal["discovery", "planning", "implementation", "testing",
                   "review", "release", "operations", "summary"]
    evidence: list[SuggestedEvidence]
    proposed_scope: str | None
    ready_for_review: bool

class InterviewModel(Protocol):
    async def next_question(self, context: "InterviewContext") -> InterviewReply: ...
    async def propose_design(self, context: "InterviewContext",
                             catalog: dict[str, object]) -> "DraftCandidate": ...
    async def close(self) -> None: ...
```

Define `InterviewContext` here as immutable session/revision, typed turns,
confirmed evidence, stage, and selected scope. Define `DraftCandidate` here
as strict profile/workflow/scenario candidate documents with no `approved`
field accepted from the model. Nested canonical structures use explicit
Pydantic types from the actual example/contracts, not arbitrary unvalidated
JSON. Server owns persisted evidence IDs; model IDs are temporary proposal
references remapped on receipt.

- [ ] **Write failing adapter tests with mocked SDK/credential.**

```python
assert captured["model"] == "gpt-5.6-sol"
assert captured["store"] is False
assert "tools" not in captured
assert captured_scope == "https://cognitiveservices.azure.com/.default"
assert credential_factory.call_count == 1
```

Verify `DefaultAzureCredential` construction rather than environment-selected
credential classes; optional managed-identity client ID is passed through.
Cover explicit missing config, 401/403, 429, timeout, refusal, malformed/extra
fields, invented source turn IDs, multiple-question output, context limits,
and attempts to include approval/catalog mutation/tool calls. No live calls.

- [ ] **Run red, then add SDK dependencies with uv.**

```bash
uv run --extra test pytest web/tests/test_interview_model.py -q
uv add openai azure-identity
```

Do not add an agent framework. Keep code execution out of this adapter.

- [ ] **Implement token provider and bounded Responses calls.**

```python
credential = DefaultAzureCredential(
    managed_identity_client_id=settings.azure_managed_identity_client_id
)
token_provider = get_bearer_token_provider(
    credential, "https://cognitiveservices.azure.com/.default"
)
```

Use `azure.identity.aio` and `AsyncOpenAI` so an `asyncio.timeout` deadline
covers initialization, token acquisition, all HTTP attempts, and retry waits.
HTTP phase timeouts alone are not a total deadline. Reject late results as
timeouts and propagate external cancellation while closing owned resources.
Check the full assembled context, including instructions and catalog, before
constructing a client. Use an Azure strict-compatible wire schema with typed
glossary entry arrays, then convert to the canonical glossary map and validate;
open-ended map schemas are not supported by Azure strict structured output.

Pass this provider using the SDK's documented Azure-compatible bearer
configuration, not a static token. Build the base URL from validated HTTPS
`HF_AZURE_OPENAI_ENDPOINT` plus `/openai/v1/`. Never accept a browser-provided
endpoint. Reuse client/credential and close both at application shutdown.
Set `store=False`, no tools, strict structured output, appropriate token limits,
and an explicit total deadline; disable overlapping SDK and application retry
loops. Safe typed error codes distinguish refusal, unavailable auth, throttling,
timeout, invalid result, and missing config. Unknown exceptions propagate to
standard server error handling without serializing provider text.

- [ ] **Run tests and commit.**

```bash
uv run --extra test pytest web/tests/test_interview_model.py web/tests/test_config.py web/tests/test_health.py -q
```

Commit subject: `feat: add keyless Azure OpenAI interview adapter`.

### Task 2: Durable consented interview lifecycle

**Files:** Create persistence/service/routes/cleanup/privacy modules,
`0005_interviews.py`, `test_interview_api.py`, `test_interview_concurrency.py`,
`test_interview_privacy.py`; update model registration and app wiring.

**Interfaces:**

```python
class StartInterviewRequest(BaseModel):
    name: str
    customer_id: str
    consent_version: Literal["2026-09-15"]
    consent_accepted: Literal[True]
    request_id: UUID

class AnswerRequest(BaseModel):
    expected_revision: int
    request_id: UUID
    answer: str
```

All request schemas forbid extra fields and enforce limits. Routes return
`{"ok": True, "session": InterviewSessionResponse}` where response contains
identity/revision/status/expiry, ordered turns, proposed and confirmed evidence,
stage, scope, last operation/error code, and proposal metadata.
Implement all interview routes listed in the spec except proposal/apply, which
task 3 wires. `POST confirmations` accepts evidence IDs and explicit
confirm/reject decisions with expected revision.

- [ ] **Write failing persistence and privacy cases.**

```python
response = client.post("/api/interviews", headers=author_headers,
                       json={**start_request, "consent_accepted": False})
assert response.status_code == 422
assert fake_model.calls == []
assert client.get(f"/api/interviews/{session_id}",
                  headers=other_tenant_headers).status_code == 404
```

Fixtures create both organizations/memberships with existing test patterns.
Check identical creation request id returns the same session, identical answer
request id never calls model twice, stale revision is 409, known secret input
is rejected before persistence, raw bodies never enter audit/logs, and expiry/
deletion prevent access. Use injected controllable models to race a second
answer, deletion, expiry, and failed/late provider completion.

- [ ] **Run tests red.**

```bash
uv run --extra test pytest web/tests/test_interview_api.py web/tests/test_interview_concurrency.py web/tests/test_interview_privacy.py -q
```

- [ ] **Implement short-transaction operation ownership.**

```text
short transaction:
  authorize tenant/role; check consent/expiry/revision;
  claim unique request ID and persist input + running operation; commit
outside transaction:
  construct bounded context; await model with cancellation-aware deadline
short transaction:
  compare operation ownership + session revision + expiry;
  append validated result only if session still exists; advance revision; commit
```

Use database compare-and-swap/unique constraints, not only in-process locks.
Do not let request-scoped identity DB sessions retain a transaction while the
model runs: resolve identity using existing auth logic in a short session.
Use a bounded operation lease to make abandoned operations explicitly
retryable after timeout, without automatic duplication of the stored turn.
409 identifies stale/busy state, failed operations retain a safe retry path,
and deletion cannot be undone by a delayed model response.
Add composite tenant foreign keys and indexes. Default retention is 30 days
from activity; server access rejects expiry even before cleanup. Cleanup
deletes only expired interview records and children, not generated designs.

- [ ] **Run migration/regression and commit.**

```bash
uv run --extra test pytest web/tests/test_interview_api.py web/tests/test_interview_concurrency.py web/tests/test_interview_privacy.py web/tests/test_schema.py -q
```

Exercise new migration upgrade/downgrade on isolated databases and document
`uv run python -m web.api.interviews.cleanup`. Commit subject:
`feat: persist consented tenant-scoped interviews`.

### Task 3: Human-reviewed proposals and canonical design guards

**Files:** Create proposals/catalog module and
`test_interview_proposals.py`, `test_design_revision_guard.py`; modify design
schema/repository/service/routes and interview routes.

**Interfaces:**

```python
class ApplyProposalRequest(BaseModel):
    expected_revision: int
    proposal_id: UUID
    expected_proposal_digest: str
    confirm_scope: Literal[True]
    design_id: UUID | None = None
    expected_design_digest: str | None = None
```

The server computes the exact proposal digest with existing canonical JSON.
`POST /proposals` uses expected revision/request ID and returns a persisted,
unapproved draft candidate with findings. `POST /apply` returns
`{"ok": True, "design": HarnessDesignResponse}` and marks accepted linkage.
Proposal body, target design, and requested digest cannot be substituted.

Extend `HarnessDesignRequest` with optional `expected_digest`, excluded from
canonical design data. Legacy callers omitting it keep existing behavior.
Portal saves always supply it. Repository update uses SQL `WHERE` with
organization, ID, and expected digest; failed match returns stale-digest 409.

- [ ] **Write failing proposal authority and race tests.**

```python
assert proposal["workflow"].get("approved") is None
assert applied["design"]["status"] == "draft"
assert applied["design"]["workflow"]["approved"]["by"] == author_subject
assert changed_design["status"] == "draft"
assert stale_apply.status_code == 409
```

Test unconfirmed fact excluded from canonical facts, invalid tool/skill/catalog,
scope not confirmed, proposal tamper, concurrent edit, cross-tenant design
target, model-forged approval, duplicate apply, and missing fields remaining
visible findings instead of synthesized facts.

- [ ] **Run tests red.**

```bash
uv run --extra test pytest web/tests/test_interview_proposals.py web/tests/test_design_revision_guard.py -q
```

- [ ] **Implement deterministic assembly and guarded application.**

Reuse authoritative catalog loading (extract the existing service helper once)
and expose a read-only author catalog endpoint if needed by forms. Strip no
dangerous fields silently: reject forbidden model fields. A scope-confirmed
apply stamps `workflow.approved` using server actor/time, explaining that this
is generation-scope confirmation, not exact-digest reviewer approval.
Use existing create/replace-draft logic inside one transaction with proposal
status and expected revisions; clear effective design approval.
Map only confirmed evidence to facts and preserve unresolved assumptions/
unknowns. Validate candidate contracts and present findings, but allow an
incomplete draft to be edited without falsely labeling it validated.

- [ ] **Run connected regressions and commit.**

```bash
uv run --extra test pytest web/tests/test_interview_proposals.py web/tests/test_design_revision_guard.py web/tests/test_design_api.py web/tests/test_design_approval.py web/tests/test_design_digest.py -q
```

Commit subject: `feat: apply reviewed interview proposals to guarded drafts`.

### Task 4: Live interview UI and lossless structured editing

**Files:** Create interview routes/components/types/forms, modify Studio links
and design editor; add DELETE to API wrapper/proxy and its tests; add
`test` coverage under `components/studio/__tests__` and `lib/__tests__`.

**Interfaces:**

```ts
export function updateDocumentField<T extends Record<string, unknown>>(
  document: T, field: string, value: unknown,
): T {
  return { ...document, [field]: value };
}
```

Use typed per-document adapters around this preserving update pattern.
Do not turn unknown values into empty strings and save them over original data.
DTO names match backend task-2/task-3 schemas. The phase-1 `InterviewWorkspace`
receives actual turns, evidence, callbacks, and composer nodes.

- [ ] **Write failing user-interaction tests.**

```tsx
expect(screen.getByRole("button", { name: "인터뷰 시작" })).toBeDisabled();
fireEvent.click(screen.getByRole("checkbox", { name: /Azure OpenAI/ }));
expect(screen.getByRole("button", { name: "인터뷰 시작" })).toBeEnabled();
```

Test consent, one-question rendering, source-linked fact confirmation, saving/
resuming, model failure/retry, 409 refresh without losing typed input, session
deletion, expiry, applying exact proposal digest, and navigating to resulting
design. Add pure round-trip tests using existing example JSON with extra
unknown fields: form edits preserve all untouched data and JSON view equality.

- [ ] **Run tests red.**

```bash
cd web/portal && npm test -- src/components/studio src/lib/__tests__
```

- [ ] **Wire live routes and form modes.**

Add consent destination/retention warnings before inference; never call the
model while typing or on every render. Generate stable request IDs per logical
submission, disable duplicate submit, preserve unsent input on recoverable
errors, and display safe specific error codes with actionable copy.
Use the existing server-side portal proxy; add DELETE both to its method
allowlist/export and client method union. Keep path validation and identity
server-owned. Avoid rendering raw model HTML.

Profile forms cover all spec fields, tracker-dependent fields, systems and
capabilities. Workflow forms cover dependency lists, tool/effect restrictions,
approval timing/role, manual handoff, inputs/outputs, rules and traceability.
Scenario form uses `id/given/expect/forbidden`. Catalog is read-only selection
from server-approved entries. Preserve JSON advanced mode and lossless
unknown fields. A read-only DAG preview uses actual dependency edges, with
cycle/missing-node feedback rather than a misleading linear flow.
Every existing design save passes its expected digest; 409 offers reload and
retains local edits rather than overwriting. Pending changes warn before
switching/closing. Render validation findings at the relevant form section
and retain original raw finding text where field mapping is unavailable.

- [ ] **Run frontend tests/typecheck/build and commit.**

```bash
cd web/portal && npm test && npm run typecheck && npm run build
```

Commit subject: `feat: add AI interview workspace and structured design editors`.

### Task 5: Real flow, visual critique, and operational documentation

**Files:** Create `web/acceptance/interview_flow.py`,
`web/tests/test_interview_acceptance.py`, `web/portal/e2e/interview.spec.ts`;
update README and any local host-API configuration docs.

**Interfaces:** Compose tasks 1-4 and phase-2 CLI acceptance without alternative
business logic. Default tests inject a structured fake model; a separately
invoked live mode requires configured endpoint/deployment and consented
synthetic input. Use actual `DefaultAzureCredential` in live mode.

- [ ] **Write acceptance assertions before wiring the complete flow.**

```python
assert proposed_design["status"] == "draft"
assert validated_design["status"] == "validated"
assert installation["operation"] == "install"
assert ready_result["ready"] is False
```

Use synthetic SDLC answers, explicit evidence/scope confirmation, canonical
validation, real review/build/publish services, and the HTTP CLI distribution
client. `ready` is false when no actual behavior/environment evidence exists.
Add delete/resume and cross-tenant failures to the same acceptance fixture.

- [ ] **Run red, then complete integrated flow and host-keyless setup.**

```bash
uv run --extra test --extra cli pytest web/tests/test_interview_acceptance.py -q
```

Document a host API under `uv run uvicorn` using Azure CLI login and a local
database, with portal proxy pointing to that host. Keep default Compose
working without Azure credentials; do not mount credential directories or
enable worker egress. Publish only loopback development ports.
Document model endpoint/deployment settings, consent/retention/cleanup,
DefaultAzureCredential behavior, role requirements, login prerequisites,
disabled-model behavior, and limits. Remove stale README claims that the
entire application has no server/dependencies; distinguish standalone core.

- [ ] **Exercise synthetic live model behavior and browser layouts.**

With user-authorized discovered resource, run the opt-in live adapter against
`https://proj-aimain.cognitiveservices.azure.com/`, deployment `gpt-5.6-sol`.
Use only fictional answers; verify structured reply validation, one question,
and human-proposal boundaries. Do not report Azure operational success if
only a mocked test ran. Do not provision registrations, roles, or resources.
Run browser journey at 320, 768, and 1440px, capture and inspect screenshots,
and correct overflow, focus, unclear hierarchy, and evidence/proposal confusion.
Keep visual artifacts in the session artifact location or ignored test output.

- [ ] **Run integrated regression, record truthful evidence, and commit.**

```bash
uv run --extra test --extra cli pytest web/tests tests/cli -q
uv run python -m unittest discover -s tests -v
cd web/portal && npm test && npm run typecheck && npm run build && npx playwright test
```

Use actual PostgreSQL for migration/concurrency/lifecycle acceptance when its
test service is available. Preserve explicit skips for unavailable external
prerequisites. Commit subject:
`test: verify interview to installed workflow lifecycle`.

## Plan Self-Review and Execution Order

The three plans implement spec sections 1-3 (visual), 2/4/7 (CLI/runtime), and
4-6/8-10 (interviews, forms, privacy, integration). No signing implementation is
required. Execute phase 1 tasks 1-2, phase 2 tasks 1-4, then phase 3 tasks 1-5.
Review each independently testable deliverable before advancing. Implementation
uses GPT-5.6 Sol throughout; do not substitute the planning model for coding.
