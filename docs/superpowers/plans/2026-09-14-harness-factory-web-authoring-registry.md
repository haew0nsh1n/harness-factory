# Harness Factory Web Authoring and Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable enterprise web MVP where an authenticated organization can create and validate Harness Factory designs, approve exact digests, build immutable workflow artifacts, publish them to an internal registry, and browse them in a React portal.

**Architecture:** Add a modular FastAPI application backed by SQLAlchemy repositories, a file-backed immutable artifact adapter, and a database-backed build queue consumed by a separate Python worker process. Add a Next.js portal that calls the API through a typed client. Reuse the existing dependency-free `harness_factory` package for validation and package generation rather than reimplementing those contracts.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL 16, psycopg 3, pytest, HTTPX, TypeScript, React 19, Next.js 15, Vitest, Testing Library, Docker Compose.

## Global Constraints

- Preserve all existing `harness_factory` public behavior and keep the existing unittest suite green.
- The API must never accept or persist connector credentials, access tokens, cookies, prompts, issue bodies, source code, diffs, or customer artifact contents outside generated package artifacts.
- Every tenant-owned database query must include `organization_id`; no unscoped resource lookup is allowed in application services.
- Development authentication may use explicit test headers only when `HF_AUTH_MODE=development`; production mode accepts validated Entra claim objects through the identity adapter.
- Production authentication validates Entra bearer-token signature, issuer,
  audience, expiry and tenant before resolving organization and roles from the
  platform database.
- Catalog file access is rooted only at server-configured `HF_CATALOG_ROOT`;
  request data can select catalog entries but cannot provide filesystem paths.
- Approval is bound to the exact canonical SHA-256 digest of profile, workflow, scenarios, and catalog selection.
- Any design mutation after approval clears the effective approval and requires a new review.
- Published asset versions and stored artifact bytes are immutable.
- Builder jobs use fresh temporary directories and publish no artifact on validation or generation failure.
- Frontend code must not embed organization IDs chosen by the browser; the API derives organization context from authenticated identity.
- Python source files should remain focused and normally stay below 300 lines; split repository, service, API, and domain responsibilities.
- The first phase implements Web Authoring Core and minimal registry publish/read APIs. CLI distribution and usage telemetry remain separate later plans.

---

## Planned File Structure

```text
pyproject.toml                         Python package, API and test dependencies
alembic.ini                            Database migration configuration
docker-compose.yml                     Local PostgreSQL, API, worker and portal
web/
  api/
    __init__.py
    main.py                            FastAPI composition root
    config.py                          Environment settings
    db.py                              Engine/session and declarative base
    errors.py                          API-safe domain errors
    identity/
      models.py                        Actor and role types
      entra.py                         Entra JWT validation
      dependencies.py                  Request actor extraction and role guards
    organizations/
      models.py                        Organization and membership tables
      repository.py                    Tenant-scoped membership queries
    designs/
      models.py                        HarnessDesign and Approval tables
      schemas.py                       Request/response models
      digest.py                        Canonical JSON and design digest
      repository.py                    Tenant-scoped persistence
      service.py                       Draft, validation and approval rules
      routes.py                        `/api/designs`
    builds/
      models.py                        BuildJob table
      storage.py                       Immutable artifact storage port/adapters
      repository.py                    Build job persistence
      service.py                       Job submission and execution
      worker.py                        Queue consumer entry point
      routes.py                        Build status/download metadata endpoints
    registry/
      models.py                        Asset and AssetVersion tables
      schemas.py                       Registry request/response models
      repository.py                    Tenant-scoped registry queries
      service.py                       Publish/search lifecycle
      routes.py                        `/api/registry`
    audit/
      models.py                        AuditEvent table
      service.py                       Append-only audit writer
  portal/
    package.json
    next.config.ts
    tsconfig.json
    src/
      app/
        api/auth/[...nextauth]/route.ts  Entra login callback
        api/control-plane/[...path]/route.ts  Authenticated API proxy
        layout.tsx
        page.tsx                       Dashboard
        studio/page.tsx                Design list/create
        studio/[id]/page.tsx           JSON editors, validation, approval, build
        registry/page.tsx              Published asset search
        registry/[slug]/page.tsx       Asset version detail
      components/
        AppShell.tsx
        JsonEditor.tsx
        StatusBadge.tsx
      lib/
        api.ts                          Typed fetch client
        auth.ts                         Auth.js Entra configuration
        types.ts                        API DTOs
      test/
        setup.ts
    tests/
      conftest.py
      test_health.py
      test_identity.py
      test_schema.py
      test_design_digest.py
      test_design_api.py
      test_design_approval.py
      test_build_worker.py
      test_registry_api.py
      test_tenant_isolation.py
      test_acceptance_flow.py
    vitest.config.ts
alembic/
  env.py
  versions/
    0001_web_authoring_registry.py
```

---

### Task 1: Python Web Runtime and Health API

**Files:**
- Create: `pyproject.toml`
- Create: `web/__init__.py`
- Create: `web/api/__init__.py`
- Create: `web/api/config.py`
- Create: `web/api/db.py`
- Create: `web/api/main.py`
- Create: `web/tests/conftest.py`
- Create: `web/tests/test_health.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `web.api.main.create_app(settings: Settings | None = None) -> FastAPI`
- Produces: `web.api.config.Settings`
- Produces: `web.api.db.Base`, `session_scope()`, and FastAPI `get_session()`
- Consumes: no web modules from later tasks.

- [ ] **Step 1: Add the Python project manifest**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "harness-factory"
version = "1.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.116,<0.117",
  "uvicorn[standard]>=0.35,<0.36",
  "pydantic-settings>=2.10,<2.11",
  "sqlalchemy>=2.0.40,<2.1",
  "alembic>=1.16,<1.17",
  "psycopg[binary]>=3.2,<3.3",
  "PyJWT[crypto]>=2.10,<2.11",
]

[project.optional-dependencies]
test = [
  "httpx>=0.28,<0.29",
  "pytest>=8.4,<8.5",
]

[tool.setuptools.packages.find]
include = ["harness_factory*", "web*"]

[tool.pytest.ini_options]
testpaths = ["tests", "web/tests"]
python_files = ["test_*.py"]
```

- [ ] **Step 2: Write the failing health test**

Create `web/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from web.api.main import create_app


def test_health_reports_service_without_database_details():
    response = TestClient(create_app()).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "harness-factory-web",
        "version": "1.1.0",
    }
```

- [ ] **Step 3: Run the test to verify RED**

Run:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest web/tests/test_health.py -v
```

Expected: FAIL because `web.api.main` does not exist.

- [ ] **Step 4: Implement configuration, database composition and health**

Create `web/api/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HF_", extra="forbid")

    database_url: str = "sqlite+pysqlite:///:memory:"
    auth_mode: str = "development"
    artifact_root: Path = Path(".harness-factory/artifacts")
    catalog_root: Path = Path("catalog")
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_jwks_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create `web/api/db.py` with SQLAlchemy `DeclarativeBase`, an engine factory using
`Settings.database_url`, and `sessionmaker(expire_on_commit=False)`.
`create_app()` stores the engine and session factory in `app.state`;
`get_session(request)` uses that app-scoped factory, commits on success, rolls
back on failure, and always closes. This keeps tests and workers from sharing a
hidden global engine.

Create `web/api/main.py`:

```python
from fastapi import FastAPI

from harness_factory import __version__
from web.api.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Harness Factory Web")
    app.state.settings = settings or get_settings()

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "service": "harness-factory-web",
            "version": __version__,
        }

    return app


app = create_app()
```

Update `harness_factory.__version__` to `1.1.0` so package and API versions have
one source of truth.

- [ ] **Step 5: Run web and legacy tests**

Run:

```bash
.venv/bin/pytest web/tests/test_health.py -v
python3 -m unittest discover -s tests -v
```

Expected: health test PASS and all existing unittest tests PASS.

- [ ] **Step 6: Ignore generated runtime state**

Append to `.gitignore`:

```gitignore
.venv/
.pytest_cache/
.harness-factory/artifacts/
web/portal/.next/
web/portal/node_modules/
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml web .gitignore harness_factory/__init__.py
git commit -m "feat: add Harness Factory web API runtime"
```

---

### Task 2: Organization Identity and Role Enforcement

**Files:**
- Create: `web/api/errors.py`
- Create: `web/api/identity/models.py`
- Create: `web/api/identity/entra.py`
- Create: `web/api/identity/dependencies.py`
- Create: `web/api/organizations/models.py`
- Create: `web/api/organizations/repository.py`
- Create: `web/tests/test_identity.py`
- Modify: `web/api/main.py`
- Modify: `web/tests/conftest.py`

**Interfaces:**
- Consumes: `Settings.auth_mode`, SQLAlchemy `Base`, `get_session()`.
- Produces: `Actor(organization_id, subject_id, roles)`
- Produces: `EntraTokenValidator.validate(token) -> EntraPrincipal`
- Produces: `get_actor(request) -> Actor`
- Produces: `require_roles(*roles) -> FastAPI dependency`
- Produces: tenant-scoped `MembershipRepository`.

- [ ] **Step 1: Write failing development-auth tests**

Create tests that call `/api/whoami` with:

```python
headers = {
    "X-HF-Organization": "org-acme",
    "X-HF-Subject": "user-1",
    "X-HF-Roles": "author,developer",
}
```

Assert the response contains those IDs and sorted roles. Add tests that missing
headers return `401`, unknown roles return `403`, and headers are rejected when
`Settings(auth_mode="entra")`.

For Entra mode, sign test JWTs with a generated RSA key and serve the matching
JWKS through a stub transport. Assert valid signature/issuer/audience/expiry and
tenant claims resolve the database-backed organization and membership. Assert
expired tokens, wrong audience, wrong issuer, unknown tenant and absent
membership return `401` or `403` without echoing claims.

- [ ] **Step 2: Run identity tests to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_identity.py -v
```

Expected: FAIL because `/api/whoami` and identity dependencies do not exist.

- [ ] **Step 3: Implement actor and role types**

Create `web/api/identity/models.py`:

```python
from dataclasses import dataclass
from typing import FrozenSet

ROLES = frozenset({"author", "reviewer", "registry-admin", "developer", "org-admin"})


@dataclass(frozen=True)
class Actor:
    organization_id: str
    subject_id: str
    roles: FrozenSet[str]
```

Create `EntraTokenValidator` in `entra.py` using `PyJWKClient`. Require an
explicit configured tenant ID, client ID and JWKS URL. Validate RS256 signature,
issuer `https://login.microsoftonline.com/{tenant}/v2.0`, audience, `exp`, `nbf`,
`tid`, and non-empty `oid`; reject algorithm substitution.

Create `get_actor()` in `dependencies.py`. In development mode, validate the
three explicit headers against identifier regexes and `ROLES`. In entra mode,
require `Authorization: Bearer`, validate it with `EntraTokenValidator`, resolve
`tid` to `Organization.entra_tenant_id`, then resolve the `oid` membership and
take roles only from the database. Never trust role or organization claims from
the browser and never fall back to development headers.

Implement:

```python
def require_roles(*allowed: str):
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if not actor.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="required role missing")
        return actor
    return dependency
```

- [ ] **Step 4: Add organization tables and scoped repository**

Define:

```python
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    entra_tenant_id: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Membership(Base):
    __tablename__ = "memberships"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), primary_key=True
    )
    subject_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    roles_json: Mapped[list[str]] = mapped_column(JSON)
```

`MembershipRepository` methods must require `organization_id` as the first
argument and include it in every `WHERE` clause.
Add `OrganizationRepository.get_by_entra_tenant_id()` as the sole intentionally
cross-tenant lookup; it may return only the organization ID and status needed to
establish the tenant boundary.

- [ ] **Step 5: Add `/api/whoami` and exception mapping**

Register a route that returns actor metadata. Add exception handlers that return:

```json
{"ok": false, "error": "required role missing", "code": "forbidden"}
```

Do not return raw exceptions or claim values.

- [ ] **Step 6: Run identity and legacy tests**

Run:

```bash
.venv/bin/pytest web/tests/test_identity.py -v
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/api web/tests
git commit -m "feat: enforce organization identity and roles"
```

---

### Task 3: Database Schema and Initial Migration

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_web_authoring_registry.py`
- Create: `web/api/designs/models.py`
- Create: `web/api/builds/models.py`
- Create: `web/api/registry/models.py`
- Create: `web/api/audit/models.py`
- Create: `web/tests/test_schema.py`
- Modify: `web/api/db.py`

**Interfaces:**
- Consumes: SQLAlchemy `Base`, organization foreign keys.
- Produces: tables `harness_designs`, `approvals`, `build_jobs`, `assets`,
  `asset_versions`, `audit_events`.
- Produces: lifecycle string constants shared by services.

- [ ] **Step 1: Write failing schema tests**

Use a temporary SQLite database and assert all required tables and unique
constraints are present. Assert an `Asset` with the same `(organization_id,
slug)` cannot be inserted twice, while two organizations may use the same slug.

- [ ] **Step 2: Run schema tests to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_schema.py -v
```

Expected: FAIL because model modules and tables do not exist.

- [ ] **Step 3: Define design and approval models**

`HarnessDesign` fields:

```text
id UUID-string primary key
organization_id indexed foreign key
customer_id
name
profile_json JSON
workflow_json JSON
scenarios_json JSON
catalog_json JSON
revision integer
digest char(64)
status draft|validated|approved|build-queued|built|failed
created_by
created_at
updated_at
```

`Approval` fields:

```text
id UUID-string primary key
organization_id indexed
subject_type = harness-design|asset-version
subject_id
subject_digest char(64)
decision approved|rejected
actor_subject_id
created_at
```

Do not update approval rows after insertion.

- [ ] **Step 4: Define build, registry and audit models**

`BuildJob`: design ID/digest, `queued|running|succeeded|failed`, attempts,
artifact key/digest, structured error code, timestamps.

`Asset`: organization, `skill|plugin|workflow`, slug, name, description, owner,
visibility `internal`, lifecycle `active|archived`.

`AssetVersion`: asset, semantic version, immutable manifest JSON, digest,
artifact key/digest, status
`draft|validated|in-review|approved|published|deprecated|revoked`, channel,
created_by, timestamps. Add a unique constraint on `(asset_id, version)`.

`AuditEvent`: organization, actor, action, resource type/id, summary JSON and
timestamp. Expose no update method.

- [ ] **Step 5: Create Alembic migration**

Import every model into `alembic/env.py` and generate a checked-in migration
whose upgrade creates all tables and indexes and whose downgrade drops them in
foreign-key-safe reverse order.

- [ ] **Step 6: Run schema tests and migration smoke test**

Run:

```bash
.venv/bin/pytest web/tests/test_schema.py -v
HF_DATABASE_URL=sqlite+pysqlite:///./tests-web.db .venv/bin/alembic upgrade head
HF_DATABASE_URL=sqlite+pysqlite:///./tests-web.db .venv/bin/alembic downgrade base
rm tests-web.db
```

Expected: PASS and no database file remains.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini alembic web/api web/tests
git commit -m "feat: add web authoring and registry schema"
```

---

### Task 4: Canonical Design Digest and Validation Service

**Files:**
- Create: `web/api/designs/digest.py`
- Create: `web/api/designs/schemas.py`
- Create: `web/api/designs/repository.py`
- Create: `web/api/designs/service.py`
- Create: `web/api/designs/routes.py`
- Create: `web/tests/test_design_digest.py`
- Create: `web/tests/test_design_api.py`
- Modify: `web/api/main.py`

**Interfaces:**
- Consumes: existing `harness_factory.validate()` and
  `harness_factory.validate_scenarios()`.
- Produces:
  `canonical_design_bytes(profile, workflow, scenarios, catalog) -> bytes`
- Produces:
  `design_digest(profile, workflow, scenarios, catalog) -> str`
- Produces: design CRUD and validation endpoints under `/api/designs`.

- [ ] **Step 1: Write failing digest tests**

Assert:

```python
first = design_digest(profile, workflow, scenarios, catalog)
second = design_digest(
    dict(reversed(list(profile.items()))), workflow, scenarios, catalog
)
assert first == second
assert len(first) == 64
```

Also assert changing a single workflow completion string changes the digest.

- [ ] **Step 2: Run digest tests to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_design_digest.py -v
```

Expected: FAIL because digest helpers do not exist.

- [ ] **Step 3: Implement canonical digest**

Use one canonical envelope:

```python
payload = {
    "schema_version": 1,
    "profile": profile,
    "workflow": workflow,
    "scenarios": scenarios,
    "catalog": catalog,
}
```

Serialize with UTF-8, `sort_keys=True`, compact separators, `ensure_ascii=False`,
and `allow_nan=False`; hash the exact bytes with SHA-256.

- [ ] **Step 4: Write failing design API tests**

Test:

- author can create a draft.
- developer without author role receives `403`.
- organization B receives `404` for organization A's design ID.
- `POST /api/designs/{id}/validate` calls the real existing validators.
- invalid workflow returns `422` with a normalized finding and keeps status
  `draft`.
- valid workflow sets status `validated` and stores the current digest.

Use the repository's real `examples/github-issue/{profile,workflow,scenarios}.json`
and `catalog/catalog.json` as valid fixtures.

- [ ] **Step 5: Implement tenant-scoped repository and service**

Repository methods:

```python
create(organization_id, actor_id, request) -> HarnessDesign
list(organization_id) -> list[HarnessDesign]
get(organization_id, design_id) -> HarnessDesign | None
replace_draft(organization_id, design_id, request) -> HarnessDesign
save_validation(organization_id, design_id, digest, succeeded, finding) -> HarnessDesign
```

`replace_draft` increments revision, recalculates digest, sets `status="draft"`,
and never mutates rows belonging to another organization.

The validation service calls
`validate(profile, workflow, catalog, settings.catalog_root)` and
`validate_scenarios(scenarios, workflow)` against the server-configured catalog
root. It rejects any request catalog source or path field. It maps
`harness_factory.contracts.ValidationError` and
`harness_factory.evaluation.EvaluationError` to:

```json
{"field": "contract", "code": "invalid-design", "message": "..."}
```

Do not include a Python traceback.

- [ ] **Step 6: Add routes and run design tests**

Routes:

```text
POST /api/designs
GET /api/designs
GET /api/designs/{design_id}
PUT /api/designs/{design_id}
POST /api/designs/{design_id}/validate
```

Run:

```bash
.venv/bin/pytest web/tests/test_design_digest.py web/tests/test_design_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/api/designs web/api/main.py web/tests
git commit -m "feat: validate tenant-scoped harness designs"
```

---

### Task 5: Digest-Bound Review and Approval

**Files:**
- Create: `web/api/audit/service.py`
- Create: `web/tests/test_design_approval.py`
- Modify: `web/api/designs/repository.py`
- Modify: `web/api/designs/service.py`
- Modify: `web/api/designs/routes.py`

**Interfaces:**
- Consumes: validated design digest and `Approval` model.
- Produces:
  `approve_design(actor, design_id, expected_digest, decision) -> HarnessDesign`
- Produces:
  `POST /api/designs/{id}/reviews`.

- [ ] **Step 1: Write failing approval tests**

Cover:

- reviewer can approve only `validated` designs.
- author without reviewer role receives `403`.
- stale `expected_digest` returns `409`.
- approval row stores exact digest and actor.
- modifying the approved design returns it to `draft`; the prior approval remains
  auditable but is no longer effective.
- rejected design remains non-buildable until changed and revalidated.

- [ ] **Step 2: Run approval tests to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_design_approval.py -v
```

Expected: FAIL because review routes do not exist.

- [ ] **Step 3: Implement append-only audit writer**

`AuditService.append()` accepts only structured values:

```python
append(
    organization_id: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    summary: dict[str, str | int | bool | None],
) -> AuditEvent
```

Reject summary keys that denote sensitive values, including `token`, `password`,
`secret`, `cookie`, `credential`, `prompt`, `source_code`, `diff`, or
`content`. Permit bounded enum fields such as `error_code`.

- [ ] **Step 4: Implement approval transaction**

Within one database transaction:

1. Load the design with organization scope.
2. Require status `validated`.
3. Compare `expected_digest` using constant-time digest comparison.
4. Insert the immutable approval.
5. Set design status to `approved` for approval or `draft` for rejection.
6. Append the audit event.

Return `409` for stale digest and `422` for invalid lifecycle.

- [ ] **Step 5: Run approval and legacy tests**

Run:

```bash
.venv/bin/pytest web/tests/test_design_approval.py -v
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/api/designs web/api/audit web/tests
git commit -m "feat: bind harness approvals to exact digests"
```

---

### Task 6: Immutable Artifact Storage and Builder Worker

**Files:**
- Create: `web/api/builds/storage.py`
- Create: `web/api/builds/repository.py`
- Create: `web/api/builds/service.py`
- Create: `web/api/builds/worker.py`
- Create: `web/api/builds/routes.py`
- Create: `web/tests/test_build_worker.py`
- Modify: `web/api/main.py`
- Modify: `web/api/designs/models.py`

**Interfaces:**
- Consumes: approved `HarnessDesign`, existing
  `generate_package(...)` and `check_package(...)`.
- Produces:
  `ArtifactStorage.put_once(key: str, source: Path) -> StoredArtifact`
- Produces:
  `BuildService.submit(actor, design_id, expected_digest) -> BuildJob`
- Produces:
  `BuildService.run_next() -> BuildJob | None`
- Produces: `/api/designs/{id}/builds` and `/api/builds/{id}`.

- [ ] **Step 1: Write failing storage and build tests**

Test:

- `FileArtifactStorage.put_once` stores exact bytes under a digest-derived key.
- writing different bytes to an existing key raises `ArtifactConflict`.
- only approved exact design digest can be queued.
- duplicate submission for the same design digest returns the existing queued or
  successful job.
- worker generates a package, checks it, archives it deterministically and stores
  artifact digest.
- invalid build leaves no artifact and records only an error code.
- worker temporary directory is removed after success and failure.

- [ ] **Step 2: Run build tests to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_build_worker.py -v
```

Expected: FAIL because build services do not exist.

- [ ] **Step 3: Implement immutable file storage**

Define:

```python
@dataclass(frozen=True)
class StoredArtifact:
    key: str
    sha256: str
    size: int


class ArtifactStorage(Protocol):
    def put_once(self, key: str, source: Path) -> StoredArtifact: ...
    def open(self, key: str) -> BinaryIO: ...
```

`FileArtifactStorage` must reject absolute keys, `..`, symlinked roots and
non-regular source files. Copy to a unique scratch file in the destination
filesystem, fsync it, then create the final path with a no-overwrite hard-link
operation. If the destination exists, compare its digest and return the
existing artifact only when bytes match; otherwise raise `ArtifactConflict`.

- [ ] **Step 4: Implement build queue repository**

Use `BuildJob` rows as an at-least-once queue. `claim_next()` atomically moves one
`queued` row to `running` and increments attempts. PostgreSQL uses
`SELECT ... FOR UPDATE SKIP LOCKED`; SQLite tests use a serialized transaction
fallback.

- [ ] **Step 5: Implement deterministic package archive**

The worker:

1. Rechecks design status, digest and effective approval.
2. Creates a fresh temporary root.
3. Resolves the server-configured catalog root, rejects symlinked roots, and
   verifies the design's catalog JSON against files beneath that root.
4. Calls `generate_package(...)` with that root.
5. Calls `check_package(...)`.
6. Creates a tar archive with sorted names, uid/gid 0, empty owner/group names,
   mode-preserving regular files, and mtime 0.
7. Stores it under
   `organizations/{org}/designs/{design}/{digest}/package.tar`.
8. Records archive SHA-256 and marks both job and design `succeeded`/`built`.

Catch only known harness, validation and OS errors. Store an enum error code such
as `validation-failed`, `generation-failed`, `storage-conflict`, or
`worker-failed`; do not persist raw exception strings.

- [ ] **Step 6: Add worker entry point and routes**

`python -m web.api.builds.worker --once` processes at most one job and exits.
Without `--once`, sleep for one second when no job exists and continue until
SIGTERM.

Routes:

```text
POST /api/designs/{design_id}/builds
GET /api/builds/{build_id}
```

Artifact download is not exposed until registry publication in Task 7.

- [ ] **Step 7: Run build and legacy tests**

Run:

```bash
.venv/bin/pytest web/tests/test_build_worker.py -v
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add web/api/builds web/api/designs web/api/main.py web/tests
git commit -m "feat: build immutable harness artifacts"
```

---

### Task 7: Minimal Enterprise Registry API

**Files:**
- Create: `web/api/registry/schemas.py`
- Create: `web/api/registry/repository.py`
- Create: `web/api/registry/service.py`
- Create: `web/api/registry/routes.py`
- Create: `web/tests/test_registry_api.py`
- Create: `web/tests/test_tenant_isolation.py`
- Modify: `web/api/main.py`

**Interfaces:**
- Consumes: built design artifact, approval and audit services.
- Produces:
  `RegistryService.create_workflow_asset(...) -> Asset`
- Produces:
  `RegistryService.publish_workflow_version(...) -> AssetVersion`
- Produces: registry search, detail, version and manifest endpoints.

- [ ] **Step 1: Write failing registry lifecycle tests**

Cover:

- registry admin creates a workflow asset with an organization-unique slug.
- another organization may reuse the slug.
- only a built design with matching digest can create an asset version.
- reviewer approves the asset version digest.
- registry admin publishes only an approved version to `pilot` or `stable`.
- published manifest and artifact fields cannot be changed.
- developer can search only published versions in allowed channels.
- cross-tenant asset/version IDs return `404`.
- revoked versions are omitted from installable search results.

- [ ] **Step 2: Run registry tests to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_registry_api.py web/tests/test_tenant_isolation.py -v
```

Expected: FAIL because registry services and routes do not exist.

- [ ] **Step 3: Implement registry schemas and repository**

Request DTOs:

```python
class AssetCreate(BaseModel):
    type: Literal["workflow"]
    slug: str
    name: str
    description: str
    owner_subject_id: str


class VersionCreate(BaseModel):
    design_id: str
    design_digest: str
    version: str


class PublishRequest(BaseModel):
    expected_digest: str
    channel: Literal["pilot", "stable"]
```

Validate slug with lowercase hyphen identifiers and semantic version with
`MAJOR.MINOR.PATCH` only in this MVP.

- [ ] **Step 4: Implement registry lifecycle service**

Version manifest:

```json
{
  "schema_version": 1,
  "asset": {"type": "workflow", "slug": "issue-to-pr"},
  "version": "1.0.0",
  "runtime": "copilot-cli",
  "design_digest": "<sha256>",
  "artifact": {"sha256": "<sha256>", "key": "<opaque-key>"},
  "dependencies": []
}
```

Hash canonical manifest bytes for the version digest. Task 7 supports workflow
assets generated from designs; direct skill/plugin upload is reserved for the
next registry plan.

Publishing requires an effective approval whose subject digest equals the
current version digest. Append audit events for create, review, publish and
revoke.

- [ ] **Step 5: Add registry routes**

```text
POST /api/registry/assets
GET /api/registry/assets?query=&type=workflow&channel=stable
GET /api/registry/assets/{slug}
POST /api/registry/assets/{asset_id}/versions
POST /api/registry/versions/{version_id}/reviews
POST /api/registry/versions/{version_id}/publish
POST /api/registry/versions/{version_id}/revoke
GET /api/registry/versions/{version_id}/manifest
```

Manifest endpoint requires developer or higher role and returns JSON only. Do not
expose the storage filesystem path.

- [ ] **Step 6: Run registry, tenant and full Python tests**

Run:

```bash
.venv/bin/pytest web/tests/test_registry_api.py web/tests/test_tenant_isolation.py -v
.venv/bin/pytest web/tests -v
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/api/registry web/api/main.py web/tests
git commit -m "feat: publish workflow artifacts to internal registry"
```

---

### Task 8: React Portal for Studio and Registry

**Files:**
- Create: `web/portal/package.json`
- Create: `web/portal/next.config.ts`
- Create: `web/portal/tsconfig.json`
- Create: `web/portal/vitest.config.ts`
- Create: `web/portal/src/test/setup.ts`
- Create: `web/portal/src/app/layout.tsx`
- Create: `web/portal/src/app/api/auth/[...nextauth]/route.ts`
- Create: `web/portal/src/app/api/control-plane/[...path]/route.ts`
- Create: `web/portal/src/app/globals.css`
- Create: `web/portal/src/app/page.tsx`
- Create: `web/portal/src/app/studio/page.tsx`
- Create: `web/portal/src/app/studio/[id]/page.tsx`
- Create: `web/portal/src/app/registry/page.tsx`
- Create: `web/portal/src/app/registry/[slug]/page.tsx`
- Create: `web/portal/src/components/AppShell.tsx`
- Create: `web/portal/src/components/JsonEditor.tsx`
- Create: `web/portal/src/components/StatusBadge.tsx`
- Create: `web/portal/src/lib/api.ts`
- Create: `web/portal/src/lib/auth.ts`
- Create: `web/portal/src/lib/types.ts`
- Create: `web/portal/src/components/__tests__/JsonEditor.test.tsx`
- Create: `web/portal/src/app/studio/__tests__/StudioPage.test.tsx`
- Create: `web/portal/src/app/registry/__tests__/RegistryPage.test.tsx`

**Interfaces:**
- Consumes: Task 4-7 REST endpoints.
- Produces: locally runnable portal at port 3000.
- Produces: typed `api<T>(path, options) -> Promise<T>` client.

- [ ] **Step 1: Create the frontend manifest**

Create `web/portal/package.json`:

```json
{
  "name": "@harness-factory/portal",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "^15.5.0",
    "next-auth": "^5.0.0-beta.29",
    "react": "^19.1.0",
    "react-dom": "^19.1.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.8.0",
    "@testing-library/react": "^16.3.0",
    "@types/node": "^24.0.0",
    "@types/react": "^19.1.0",
    "@types/react-dom": "^19.1.0",
    "@vitejs/plugin-react": "^4.7.0",
    "jsdom": "^26.1.0",
    "typescript": "^5.9.0",
    "vitest": "^3.2.0"
  }
}
```

- [ ] **Step 2: Write failing component and page tests**

Tests must assert:

- `JsonEditor` reports invalid JSON without submitting.
- Studio page lists design status and exposes validate/review/build actions based
  on status, not merely on artifact presence.
- Registry page renders only published versions returned by the API.
- No component accepts or displays password, token or credential inputs.
- browser API calls use the same-origin control-plane proxy rather than exposing
  bearer tokens or development identity headers.

Mock `global.fetch` with explicit JSON fixtures; do not mock React components.

- [ ] **Step 3: Run frontend tests to verify RED**

Run:

```bash
cd web/portal
npm install
npm test
```

Expected: FAIL because components and pages do not exist.

- [ ] **Step 4: Implement typed API client**

`api.ts` sends browser requests only to the same-origin
`/api/control-plane/...` route. The route handler reads `HF_API_BASE_URL`
server-side and proxies only the allowlisted HTTP method, path, query and JSON
body.

In development mode, the proxy includes headers from server-side environment:

```text
HF_DEV_ORGANIZATION
HF_DEV_SUBJECT
HF_DEV_ROLES
```

In Entra mode, configure Auth.js with the Microsoft Entra ID provider using
`AUTH_MICROSOFT_ENTRA_ID_ID`, `AUTH_MICROSOFT_ENTRA_ID_SECRET`, and
`AUTH_MICROSOFT_ENTRA_ID_ISSUER`. Persist the Entra ID token only in the
encrypted, HTTP-only Auth.js session token and forward it to the API as a bearer
token from the server-side proxy. Never serialize it into page props or browser
storage.

Do not allow an organization ID form field. Map API error envelope to an
`ApiError(code, message, status)` without exposing response headers.

- [ ] **Step 5: Implement AppShell and dashboard**

Navigation: Dashboard, Harness Studio, Asset Registry. Show a visible
“Development identity” banner only when `NEXT_PUBLIC_HF_AUTH_MODE=development`.
In Entra mode, unauthenticated requests redirect to the Auth.js sign-in route
and sign-out clears the server session.

Dashboard shows counts fetched from design and registry list APIs. It must label
`validated`, `approved`, `built`, and `published` separately.

- [ ] **Step 6: Implement Studio pages**

Studio list: name, customer ID, revision, status and updated time.

Design detail: four JSON editors for profile, workflow, scenarios and catalog;
save draft, validate, approve/reject with exact digest, queue build and show build
status. Disable actions that are invalid for the current lifecycle and display
server findings verbatim as text, never as HTML.

- [ ] **Step 7: Implement Registry pages**

Registry list: query, channel filter, slug, name, version and channel.

Detail: description, immutable manifest summary, artifact digest, validation and
approval status. Provide no direct filesystem key or credential fields.

- [ ] **Step 8: Run frontend verification**

Run:

```bash
cd web/portal
npm test
npm run typecheck
npm run build
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add web/portal
git commit -m "feat: add Harness Studio and registry portal"
```

---

### Task 9: Local Stack, End-to-End Acceptance and Documentation

**Files:**
- Create: `docker-compose.yml`
- Create: `web/api/Dockerfile`
- Create: `web/portal/Dockerfile`
- Create: `web/tests/test_acceptance_flow.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-11-harness-factory-web-platform-design.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: one-command local stack and recorded acceptance evidence.

- [ ] **Step 1: Write the failing API acceptance test**

Create an end-to-end service test that:

1. Creates a design from `examples/github-issue`.
2. Validates it.
3. Approves the exact digest as reviewer.
4. Queues and runs the builder once.
5. Creates a workflow asset and version.
6. Approves the exact version digest.
7. Publishes to stable.
8. Searches as developer and reads the manifest.
9. Tries every resource ID from another organization and receives `404`.

Assert the audit log contains no keys matching the forbidden sensitive field
set.

- [ ] **Step 2: Run acceptance test to verify RED**

Run:

```bash
.venv/bin/pytest web/tests/test_acceptance_flow.py -v
```

Expected: FAIL until any missing composition or route behavior is completed.

- [ ] **Step 3: Add Dockerfiles and Compose**

`docker-compose.yml` services:

- `postgres`: PostgreSQL 16 with healthcheck and named volume.
- `api`: build `web/api/Dockerfile`, run Alembic then Uvicorn on 8000.
- `worker`: same image, run `python -m web.api.builds.worker`.
- `portal`: build `web/portal/Dockerfile`, expose 3000.

Mount only a named artifact volume into API and worker. Do not mount the Docker
socket or the host repository into the worker.

- [ ] **Step 4: Complete application composition**

Ensure `create_app()` imports all models before table/migration use, registers
identity, design, build and registry routers, and exposes a development-only
`GET /api/audit` route guarded by `org-admin` for acceptance inspection.

- [ ] **Step 5: Run complete verification**

Run:

```bash
.venv/bin/pytest web/tests -v
python3 -m unittest discover -s tests -v
cd web/portal && npm test && npm run typecheck && npm run build
docker compose config --quiet
```

Expected: all commands exit 0.

- [ ] **Step 6: Exercise the running stack**

Run:

```bash
docker compose up --build -d
curl --fail http://localhost:8000/api/health
curl --fail http://localhost:3000
docker compose ps
```

Expected: API health returns `ok: true`, portal returns HTTP 200, and all four
services are healthy/running.

- [ ] **Step 7: Document local usage and boundaries**

Add README sections with:

```bash
docker compose up --build
open http://localhost:3000
```

Document development identity variables, production Entra adapter boundary,
artifact directory, builder network restriction, exact-digest approval, and
that CLI distribution/usage telemetry are follow-up implementation plans rather
than completed features.

- [ ] **Step 8: Record acceptance in the design**

Append an implementation acceptance section containing exact Python test count,
frontend test count, build result, Compose services, acceptance flow outcome,
and intentionally deferred CLI/telemetry features.

- [ ] **Step 9: Stop the local stack**

Run:

```bash
docker compose down
```

Do not delete the PostgreSQL or artifact volumes unless explicitly requested.

- [ ] **Step 10: Commit**

```bash
git add docker-compose.yml web README.md docs/superpowers/specs/2026-09-11-harness-factory-web-platform-design.md
git commit -m "docs: record web authoring registry acceptance"
```
