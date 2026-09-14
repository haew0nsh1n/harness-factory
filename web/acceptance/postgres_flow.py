"""Bounded PostgreSQL acceptance run for the web authoring registry.

Executes the complete authoring lifecycle against a running Compose stack:

    docker compose exec api python -m web.acceptance.postgres_flow

The command talks to the running API over HTTP, relies on the running worker to
produce the build artifact, and asserts tenant isolation directly against
PostgreSQL. It is idempotent across repeated runs because every asset slug and
design name carries a unique suffix.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from harness_factory import load_json
from web.api.config import Settings, get_settings
from web.api.db import create_session_factory
from web.api.organizations.models import Membership, Organization

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 1.0
OTHER_ORGANIZATION_ID = "acceptance-other"
PRIVILEGED_ROLES = "author,reviewer,registry-admin,developer,org-admin"


class AcceptanceFailure(RuntimeError):
    """Raised when an acceptance expectation is not met."""


@dataclass(frozen=True)
class HttpResult:
    status: int
    payload: object


def _http_request(
    base_url: str,
    method: str,
    path: str,
    headers: dict[str, str],
    body: object | None,
) -> HttpResult:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=data, method=method
    )
    request.add_header("accept", "application/json")
    if data is not None:
        request.add_header("content-type", "application/json")
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return HttpResult(response.status, json.loads(response.read() or b"null"))
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw or b"null")
        except json.JSONDecodeError:
            payload = {"raw": raw.decode(errors="replace")}
        return HttpResult(error.code, payload)


def http_transport(base_url: str):
    def transport(
        method: str, path: str, headers: dict[str, str], body: object | None
    ) -> HttpResult:
        return _http_request(base_url, method, path, headers, body)

    return transport


def _request(
    send,
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    body: object | None = None,
) -> HttpResult:
    return send(method, path, headers, body)


def _headers(organization_id: str, subject_id: str, roles: str) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
        "X-HF-Roles": roles,
    }


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def _expect_status(result: HttpResult, expected: int, step: str) -> object:
    _expect(
        result.status == expected,
        f"{step}: expected HTTP {expected}, got {result.status}: {result.payload!r}",
    )
    return result.payload


def _design_payload(catalog_root: Path, examples_root: Path, suffix: str) -> dict:
    profile = load_json(examples_root / "github-issue" / "profile.json")
    workflow = load_json(examples_root / "github-issue" / "workflow.json")
    scenarios = load_json(examples_root / "github-issue" / "scenarios.json")
    catalog = load_json(catalog_root / "catalog.json")
    return {
        "customer_id": profile["customer_id"],
        "name": f"{profile['name']} {suffix}",
        "profile": profile,
        "workflow": workflow,
        "scenarios": scenarios,
        "catalog": catalog,
    }


def _ensure_other_organization(settings: Settings) -> None:
    engine, factory = create_session_factory(settings)
    try:
        with factory() as session:
            existing = session.scalar(
                select(Organization).where(Organization.id == OTHER_ORGANIZATION_ID)
            )
            if existing is None:
                session.add(
                    Organization(
                        id=OTHER_ORGANIZATION_ID,
                        entra_tenant_id=f"development-{OTHER_ORGANIZATION_ID}",
                        name="Acceptance Other Tenant",
                    )
                )
                session.flush()
                session.add(
                    Membership(
                        organization_id=OTHER_ORGANIZATION_ID,
                        subject_id="acceptance-other-subject",
                        roles_json=["author", "developer", "registry-admin"],
                    )
                )
                session.commit()
    finally:
        engine.dispose()


def _wait_for_build(
    transport,
    headers: dict[str, str],
    build_id: str,
    timeout_seconds: float,
    on_poll=None,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last: object = None
    while time.monotonic() < deadline:
        if on_poll is not None:
            on_poll()
        result = transport("GET", f"/api/builds/{build_id}", headers, None)
        payload = _expect_status(result, 200, "poll build")
        build = payload["build"]  # type: ignore[index]
        last = build
        if build["status"] == "succeeded":
            return build
        if build["status"] == "failed":
            raise AcceptanceFailure(f"build failed: {build}")
        if on_poll is None:
            time.sleep(POLL_INTERVAL_SECONDS)
    raise AcceptanceFailure(f"build did not finish within {timeout_seconds}s: {last}")


def run_flow(
    *,
    settings: Settings,
    base_url: str = DEFAULT_API_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    examples_root: Path | None = None,
    transport=None,
    on_build_poll=None,
) -> dict[str, object]:
    _expect(
        settings.database_url.startswith("postgresql"),
        "acceptance requires a PostgreSQL HF_DATABASE_URL, "
        f"got {settings.database_url.split('://', 1)[0]}",
    )
    suffix = uuid4().hex[:8]
    organization_id = settings.development_organization_id
    subject_id = settings.development_subject_id
    headers = _headers(organization_id, subject_id, PRIVILEGED_ROLES)
    other_headers = _headers(
        OTHER_ORGANIZATION_ID, "acceptance-other-subject", "author,developer"
    )
    examples = examples_root or Path("examples")
    send = transport or http_transport(base_url)
    _ensure_other_organization(settings)

    health = _request(send, "GET", "/api/health", headers={})
    _expect_status(health, 200, "health")

    created = _expect_status(
        _request(
            send,
            "POST",
            "/api/designs",
            headers=headers,
            body=_design_payload(settings.catalog_root, examples, suffix),
        ),
        201,
        "create design",
    )
    design = created["design"]  # type: ignore[index]

    validated = _expect_status(
        _request(
            send,
            "POST",
            f"/api/designs/{design['id']}/validate",
            headers=headers,
        ),
        200,
        "validate design",
    )
    design = validated["design"]  # type: ignore[index]
    _expect(design["status"] == "validated", f"unexpected status {design['status']}")

    stale_review = _request(
        send,
        "POST",
        f"/api/designs/{design['id']}/reviews",
        headers=headers,
        body={"expected_digest": "0" * 64, "decision": "approved"},
    )
    _expect(stale_review.status == 409, f"stale review not rejected: {stale_review}")

    malformed_review = _request(
        send,
        "POST",
        f"/api/designs/{design['id']}/reviews",
        headers=headers,
        body={"expected_digest": "é" * 64, "decision": "approved"},
    )
    _expect(
        malformed_review.status == 422
        and malformed_review.payload["code"] == "invalid_request",  # type: ignore[index]
        f"malformed digest not rejected: {malformed_review}",
    )

    approved = _expect_status(
        _request(
            send,
            "POST",
            f"/api/designs/{design['id']}/reviews",
            headers=headers,
            body={"expected_digest": design["digest"], "decision": "approved"},
        ),
        200,
        "approve design",
    )
    design = approved["design"]  # type: ignore[index]

    queued = _expect_status(
        _request(
            send,
            "POST",
            f"/api/designs/{design['id']}/builds",
            headers=headers,
            body={"expected_digest": design["digest"]},
        ),
        202,
        "queue build",
    )
    build = _wait_for_build(
        send,
        headers,
        queued["build"]["id"],  # type: ignore[index]
        timeout_seconds,
        on_build_poll,
    )

    slug = f"acceptance-workflow-{suffix}"
    asset = _expect_status(
        _request(
            send,
            "POST",
            "/api/registry/assets",
            headers=headers,
            body={
                "type": "workflow",
                "slug": slug,
                "name": f"Acceptance Workflow {suffix}",
                "description": "PostgreSQL acceptance workflow package",
                "owner_subject_id": subject_id,
            },
        ),
        201,
        "create asset",
    )["asset"]  # type: ignore[index]

    version = _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/assets/{asset['id']}/versions",
            headers=headers,
            body={
                "design_id": design["id"],
                "design_digest": design["digest"],
                "version": "1.0.0",
            },
        ),
        201,
        "create version",
    )["version"]  # type: ignore[index]

    _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/versions/{version['id']}/reviews",
            headers=headers,
            body={"expected_digest": version["digest"], "decision": "approved"},
        ),
        200,
        "approve version",
    )
    published = _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/versions/{version['id']}/publish",
            headers=headers,
            body={"expected_digest": version["digest"], "channel": "stable"},
        ),
        200,
        "publish version",
    )["version"]  # type: ignore[index]
    _expect(published["status"] == "published", f"unexpected status {published}")

    search = _expect_status(
        _request(
            send,
            "GET",
            f"/api/registry/assets?type=workflow&query={slug}",
            headers=headers,
        ),
        200,
        "search assets",
    )
    slugs = [item["slug"] for item in search["items"]]  # type: ignore[index]
    _expect(slug in slugs, f"published asset missing from search: {slugs}")

    manifest = _expect_status(
        _request(
            send,
            "GET",
            f"/api/registry/versions/{version['id']}/manifest",
            headers=_headers(organization_id, subject_id, "developer"),
        ),
        200,
        "manifest",
    )
    _expect(
        manifest["artifact"]["sha256"] == build["artifact_digest"],  # type: ignore[index]
        "manifest artifact digest does not match the build artifact",
    )

    cross_tenant_detail = _request(
        send, "GET", f"/api/registry/assets/{slug}", headers=other_headers
    )
    _expect(
        cross_tenant_detail.status == 404,
        f"cross-tenant asset detail leaked: {cross_tenant_detail}",
    )
    cross_tenant_version = _request(
        send,
        "POST",
        f"/api/registry/assets/{asset['id']}/versions",
        headers=other_headers,
        body={
            "design_id": design["id"],
            "design_digest": design["digest"],
            "version": "1.0.1",
        },
    )
    _expect(
        cross_tenant_version.status == 404,
        f"cross-tenant version create leaked: {cross_tenant_version}",
    )
    cross_tenant_manifest = _request(
        send,
        "GET",
        f"/api/registry/versions/{version['id']}/manifest",
        headers=_headers(OTHER_ORGANIZATION_ID, "acceptance-other-subject", "developer"),
    )
    _expect(
        cross_tenant_manifest.status == 404,
        f"cross-tenant manifest leaked: {cross_tenant_manifest}",
    )

    unknown_tenant = _request(
        send,
        "POST",
        "/api/designs",
        headers=_headers("acceptance-unknown", "ghost", "author"),
        body=_design_payload(settings.catalog_root, examples, f"{suffix}-ghost"),
    )
    _expect(
        unknown_tenant.status == 409
        and unknown_tenant.payload["code"] == "missing_reference",  # type: ignore[index]
        f"unknown tenant write was not a safe 4xx: {unknown_tenant}",
    )

    return {
        "ok": True,
        "database": "postgresql",
        "design_id": design["id"],
        "design_digest": design["digest"],
        "build_id": build["id"],
        "artifact_sha256": build["artifact_digest"],
        "asset_slug": slug,
        "version_id": version["id"],
        "version_digest": version["digest"],
        "channel": published["channel"],
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Run the PostgreSQL authoring registry acceptance flow."
    )
    root.add_argument("--base-url", default=DEFAULT_API_BASE_URL)
    root.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    root.add_argument("--examples-root", default="examples")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = run_flow(
            settings=get_settings(),
            base_url=args.base_url,
            timeout_seconds=args.timeout,
            examples_root=Path(args.examples_root),
        )
    except (AcceptanceFailure, OSError, KeyError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "code": "acceptance-failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
