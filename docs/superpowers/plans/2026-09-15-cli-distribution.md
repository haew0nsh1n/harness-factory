# CLI Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install a published workflow from the authenticated registry through the existing exact-digest installer.

**Architecture:** Add authorized online delivery endpoints and a separately packaged `hf_cli` client. Trust the configured HTTPS registry and verify artifact hashes; reuse stable cached package paths with the existing installer.

**Tech Stack:** Python 3.12, uv, FastAPI/SQLAlchemy, HTTPX, MSAL, OS keyring, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-studio-interview-cli-design.md`

## Global Constraints

- This is phase 2, after `2026-09-15-studio-visual-refresh.md` and before live interviews/forms.
- All implementation agents use `gpt-5.6-sol`.
- No package signatures, Key Vault, signing keys, telemetry, automatic upgrade, or uninstall.
- Production registry requires HTTPS and no unexpected redirects; loopback development requires explicit opt-in.
- Every delivery read includes organization and published-lifecycle checks; no role bypass for CLI input.
- Tokens only in a safe OS credential store; never plaintext configuration or logs.
- Archive bounds: 100 MiB transfer, 256 MiB expanded, 10,000 entries, 16 MiB per file.
- Preserve dependency-free source CLI and existing public installer behavior, including explicit partial-install errors.
- Published/installed does not imply evaluated/ready.
- uv lock/install/run is the Python workflow. Add dependencies only where required.
- Required commit trailers apply to every owned-file commit.

## File Structure

- `pyproject.toml`, `uv.lock`, `web/api/Dockerfile`, `README.md`: uv runtime/CLI packaging.
- `web/api/distribution/{__init__,schemas,service,routes}.py`: immutable metadata and authorized streaming.
- `hf_cli/{__init__,__main__,main,errors,config,auth,client}.py`: CLI/config/login/registry operations.
- `hf_cli/{archive,cache,install}.py`: bounded verified package materialization and installer orchestration.
- `tests/cli/`: standalone CLI unit/integration tests.
- `web/tests/test_distribution.py`: API role/tenant/lifecycle/digest coverage.
- `web/acceptance/distribution_flow.py`: published asset through CLI preview/apply.

### Task 1: Authorized delivery API and uv runtime

**Files:** Create distribution module/tests; modify `web/api/main.py`, `web/api/registry/repository.py` only as needed to reuse tenant-scoped lookup; update Python manifest/lock/Dockerfile/README.

**Interfaces:**

```python
class DeliveryMetadata(BaseModel):
    schema_version: Literal[1]
    organization_id: str
    asset_id: str
    version_id: str
    slug: str
    version: str
    manifest: dict[str, Any]
    manifest_sha256: str
    artifact_sha256: str
    artifact_size: int
```

Produce:
- `GET /api/registry/versions/{version_id}/delivery` -> `{"ok": True, "delivery": DeliveryMetadata}`.
- `GET /api/registry/versions/{version_id}/artifact` -> bounded binary tar response.
- Require `developer` or `org-admin`; unpublished, revoked, deprecated, and cross-tenant versions return 404.

- [ ] **Write API failures first.** Reuse lifecycle setup patterns from
`web/tests/test_registry_lifecycle.py`, creating local fixtures in the new test:

```python
response = client.get(f"/api/registry/versions/{published_version.id}/delivery",
                      headers=other_tenant_headers)
assert response.status_code == 404
assert client.get(f"/api/registry/versions/{published_version.id}/artifact",
                  headers=author_only_headers).status_code == 403
```

Test published metadata byte length and hash, missing/corrupt artifact, explicit
403 for insufficient role, revoke between metadata and download, and no
attacker-controlled storage path.

- [ ] **Run existing pytest red, then adopt uv.**

```bash
.venv/bin/pytest web/tests/test_distribution.py -q
```

Update manifest for CLI extra and `hf` script when its module is introduced.
Use uv to lock dependencies, then `uv sync --extra test --extra cli`.
If uv is unavailable, install it only after the missing-tool failure.
Keep web dependencies working; constrain package discovery to `harness_factory*`,
`web`, `web.api*`, `web.acceptance*`, and `hf_cli*`, excluding node_modules/tests.
Docker copies the lock and uses a pinned uv image/binary and `uv sync --frozen`.
Retain non-secret private-feed override support.

- [ ] **Implement shared delivery authorization.**

```python
version = repository.get_version(actor.organization_id, version_id)
if version is None or version.status != ASSET_VERSION_STATUS_PUBLISHED:
    raise HTTPException(status_code=404, detail="version not found")
```

Use the stored immutable artifact key with existing `ArtifactStorage.open`.
Validate bytes/size/hash before sending success headers; use a bounded spooled
file when needed so corrupt storage cannot return a success-shaped download.
Close streams on completion, cancellation, and errors. Compare canonical
manifest digest with the persisted version digest. Do not modify old manifests.

- [ ] **Run regression and lock/build checks, then commit.**

```bash
uv run --extra test --extra cli pytest web/tests/test_distribution.py web/tests/test_registry_api.py web/tests/test_registry_lifecycle.py -q
uv lock --check
```

Run Docker config/build only after Dockerfile changes and where available;
record environment blockers, not inferred success. Commit subject:
`feat: add authenticated workflow delivery and uv runtime`.

### Task 2: hf configuration, Entra login, search, and info

**Files:** Create CLI argument/auth/client modules and `tests/cli/test_auth.py`,
`test_config.py`, `test_registry_client.py`; update `pyproject.toml` entry point.

**Interfaces:**

```python
@dataclass(frozen=True)
class RegistryConfig:
    url: str
    tenant_id: str
    client_id: str
    scope: str
    development: bool = False

class AuthSession:
    def headers(self) -> dict[str, str]: ...
    def login(self) -> None: ...
    def logout(self) -> None: ...

class RegistryClient:
    def whoami(self) -> dict[str, object]: ...
    def search(self, query: str) -> list[dict[str, object]]: ...
    def info(self, slug: str, version: str | None) -> dict[str, object]: ...
    def delivery(self, version_id: str) -> DeliveryMetadata: ...
```

These signatures are interface contracts, not stub implementation instructions.
CLI errors use a local typed `CliError(code: str, message: str)` with a safe
message and nonzero process exit. Provide `--json` for automation consistently.

- [ ] **Write tests using injected keyring/MSAL/HTTP clients.**

```python
with pytest.raises(CliError, match="HTTPS"):
    validate_registry_url("http://registry.example.test", development=False)
assert validate_registry_url("http://127.0.0.1:8000", development=True)
```

Test credential-bearing URLs, redirects, null/plaintext keyring backends,
device-flow denial/timeout, silent refresh, cache isolation by registry/tenant/
client/scope, logout, `/api/whoami` membership, and typed 401/403/network errors.
No test obtains or logs a real token.

- [ ] **Run tests red.**

```bash
uv run --extra test --extra cli pytest tests/cli/test_auth.py tests/cli/test_config.py tests/cli/test_registry_client.py -q
```

- [ ] **Implement CLI public entry point and client.**

```toml
[project.scripts]
hf = "hf_cli.main:main"
```

MSAL uses the tenant-specific authority, public-client device flow, and the
configured delegated scope. Serialize its cache only into a supported native
OS keyring; allowlist platform-native backends rather than trusting arbitrary
plugin priority. Do not store tokens under XDG config. Persist only non-secret
registry config with owner-only permissions. Use HTTPX with certificate checks,
explicit timeouts, no redirects, and safe error mapping.
Use existing `/api/whoami`, `/api/registry/assets?query=...`, and asset-detail
routes; URL-encode slugs and validate semantic versions. Explicit development
login accepts separate organization/subject/role arguments only on literal
loopback addresses and sends existing development headers, never production.

- [ ] **Run tests and installed-entry smoke, document Entra prerequisites, commit.**

```bash
uv run --extra test --extra cli pytest tests/cli/test_auth.py tests/cli/test_config.py tests/cli/test_registry_client.py -q
uv run --extra cli hf --help
```

Document public-client app registration, delegated API scope, membership mapping,
and native keyring requirement without creating Azure resources.
Commit subject: `feat: add hf Entra login and registry discovery`.

### Task 3: Safe archive/cache and digest-approved installation

**Files:** Create CLI archive/cache/install modules and
`tests/cli/test_archive.py`, `test_cache.py`, `test_install.py`.

**Interfaces:**

```python
def extract_package(archive: Path, destination: Path) -> None: ...
def materialize_package(client: RegistryClient, delivery: DeliveryMetadata,
                        cache_root: Path) -> Path: ...
def install_workflow(client: RegistryClient, slug: str, version: str,
                     target: Path, cache_root: Path,
                     approved_digest: str | None) -> dict[str, object]: ...
```

Extend `RegistryClient` with streaming download whose byte limit is enforced
even if `Content-Length` is absent or false. Return the original installer
preview/apply shape, optionally adding local diff information without changing
the digest.

- [ ] **Write malicious archive and stable-path regression tests.**

```python
first = materialize_package(client, delivery, cache_root)
second = materialize_package(client, delivery, cache_root)
assert first == second
preview = plan_install(first, target)
result = apply_install(second, target, preview["digest"])
assert result["operation"] == "install"
```

Create synthetic tar members for `../outside`, absolute paths, Windows-style
paths, duplicate files, links, FIFOs, devices, sparse metadata, oversized members,
and deceptive size headers. Verify exact spec limits including boundary values,
empty/corrupt files, symlinked cache ancestors, target changes, cached byte
changes, revoke after preview, and preserving unrelated customer code.

- [ ] **Run tests red.**

```bash
uv run --extra test --extra cli pytest tests/cli/test_archive.py tests/cli/test_cache.py tests/cli/test_install.py -q
```

- [ ] **Implement bounded staging and reuse core installation.**

```python
package = materialize_package(client, metadata, cache_root)
check_package(package)
if approved_digest is None:
    return plan_install(package, target)
return apply_install(package, target, approved_digest)
```

Before this snippet, resolve exact published version and obtain fresh metadata;
verify tenant/asset/version/manifest identity. Cache path is deterministic from
organization/version/artifact hash and never from arbitrary server filenames.
Extract into a fresh private staging directory, validate every member, check
the package, then atomically promote the verified directory to stable cache.
Reject unsupported compression; do not call unrestricted `extractall`.
Rehash cache inventory before reuse. Compute local text diffs with `difflib`
and bounded output; never upload target files/diffs.
On apply, refresh registry metadata and lifecycle and require the same
artifact identity as preview; preserve the original source path. No implicit
approval, offline fallback, or silent partial-install success.

- [ ] **Run regression, document hash trust and partial writes, commit.**

```bash
uv run --extra test --extra cli pytest tests/cli/test_archive.py tests/cli/test_cache.py tests/cli/test_install.py tests/test_install.py -q
```

Commit subject: `feat: install verified registry packages with digest approval`.

### Task 4: Packaged CLI and PostgreSQL end-to-end delivery

**Files:** Create `web/acceptance/distribution_flow.py`,
`web/tests/test_distribution_acceptance.py`, and `tests/cli/test_packaging.py`;
update README and optional CLI hints in registry detail.

**Interfaces:** Reuse task 1 delivery routes, task 2 CLI entry point, task 3
installer, and the existing PostgreSQL lifecycle fixture/acceptance helpers.
No duplicated build/publish domain logic.

- [ ] **Write failing acceptance expectations.**

```python
assert preview["operation"] == "install-preview"
assert not target.exists()
assert applied["operation"] == "install"
assert (target / ".harness" / "manifest.json").is_file()
assert (target / "customer-owned.txt").read_text() == "preserved"
```

Seed an approved/built/published synthetic workflow using existing application
services. Perform HTTP-backed search/info/delivery, then CLI preview/apply.
Add cross-tenant 404, revoke rejection, missing evaluation/ready distinction.

- [ ] **Run acceptance red, then wire real packaged imports.**

```bash
uv run --extra test --extra cli pytest web/tests/test_distribution_acceptance.py tests/cli/test_packaging.py -q
```

Build a wheel with `uv build`, install it with CLI extra into a temporary
environment, and invoke `hf --help` from outside the checkout. Confirm no
portal/node_modules directories enter the wheel and the original core source
tests still pass. Do not require a live native keyring for fake-auth integration.

- [ ] **Complete real PostgreSQL acceptance and documentation.**

```bash
uv run --extra test --extra cli pytest tests/cli web/tests/test_distribution.py web/tests/test_distribution_acceptance.py -q
uv run python -m unittest discover -s tests -v
```

Run PostgreSQL acceptance only with its explicit test URL or isolated Compose
stack. Document the exact successful commands and any skipped live Entra
checks. Keep API/worker volume/network isolation unchanged.

- [ ] **Commit the end-to-end delivery.**

Commit subject: `test: cover packaged CLI distribution lifecycle`.

## Handoff

Continue with `2026-09-15-ai-interview-forms.md`. The CLI establishes online
registry trust, not independent publisher signing or customer readiness.
