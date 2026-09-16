from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from harness_factory import load_json
from web.api.audit.models import AuditEvent
from web.api.builds.models import (
    BUILD_STATUS_SUCCEEDED,
    BuildJob,
)
from web.api.builds.storage import ArtifactStorageError
from web.api.config import Settings
from web.api.db import Base
from web.api.designs.digest import canonical_json_bytes, design_digest
from web.api.designs.models import (
    APPROVAL_DECISION_APPROVED,
    APPROVAL_SUBJECT_TYPE_ASSET_VERSION,
    APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
    Approval,
    DESIGN_STATUS_APPROVED,
    DESIGN_STATUS_BUILT,
    HarnessDesign,
)
from web.api.main import create_app
from web.api.registry.repository import RegistryRepository
from web.api.organizations.models import Organization
from web.api.registry.models import AssetVersion


FIXTURE_ROOT = Path(__file__).resolve().parents[2]


def load_design_fixture(name: str) -> dict[str, object]:
    if name == "catalog":
        return load_json(FIXTURE_ROOT / "catalog" / "catalog.json")
    return load_json(FIXTURE_ROOT / "examples" / "github-issue" / f"{name}.json")


def build_design_payload() -> dict[str, object]:
    profile = load_design_fixture("profile")
    return {
        "customer_id": profile["customer_id"],
        "name": profile["name"],
        "profile": profile,
        "workflow": load_design_fixture("workflow"),
        "scenarios": load_design_fixture("scenarios"),
        "catalog": load_design_fixture("catalog"),
    }


def build_headers(
    *,
    organization_id: str = "org-acme",
    subject_id: str = "user-1",
    roles: str = "registry-admin",
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
        "X-HF-Roles": roles,
    }


@pytest.fixture
def registry_client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url="sqlite+pysqlite:///:memory:",
            catalog_root=FIXTURE_ROOT / "catalog",
            artifact_root=tmp_path / "artifacts",
        )
    )
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as session:
        session.add_all(
            [
                Organization(
                    id="org-acme",
                    entra_tenant_id="tenant-acme",
                    name="Acme",
                ),
                Organization(
                    id="org-umbrella",
                    entra_tenant_id="tenant-umbrella",
                    name="Umbrella",
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        yield client


def create_asset(
    client: TestClient,
    *,
    organization_id: str = "org-acme",
    slug: str = "issue-to-pr",
    name: str = "Issue to PR",
) -> dict[str, Any]:
    response = client.post(
        "/api/registry/assets",
        headers=build_headers(organization_id=organization_id),
        json={
            "type": "workflow",
            "slug": slug,
            "name": name,
            "description": "Publishes a workflow package",
            "owner_subject_id": "owner-1",
        },
    )
    assert response.status_code == 201
    return response.json()["asset"]


def seed_built_design(
    client: TestClient,
    *,
    organization_id: str = "org-acme",
    design_id: str = "design-1",
    artifact_bytes: bytes = b"workflow package bytes\n",
    status: str = DESIGN_STATUS_BUILT,
    with_successful_build: bool = True,
) -> dict[str, str]:
    payload = build_design_payload()
    workflow = dict(payload["workflow"])
    workflow["steps"] = list(payload["workflow"]["steps"])
    workflow["steps"][0] = dict(workflow["steps"][0])
    workflow["steps"][0]["completion"] = (
        f"{workflow['steps'][0]['completion']} ({design_id})"
    )
    digest = design_digest(
        payload["profile"],
        workflow,
        payload["scenarios"],
        payload["catalog"],
    )
    artifact_key = (
        f"organizations/{organization_id}/designs/{design_id}/{digest}/package.tar"
    )
    artifact_path = client.app.state.settings.artifact_root / artifact_key
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)
    artifact_digest = hashlib.sha256(artifact_bytes).hexdigest()

    with Session(client.app.state.engine) as session:
        session.add(
            HarnessDesign(
                id=design_id,
                organization_id=organization_id,
                customer_id=payload["customer_id"],
                name=f"{payload['name']} {design_id}",
                profile_json=payload["profile"],
                workflow_json=workflow,
                scenarios_json=payload["scenarios"],
                catalog_json=payload["catalog"],
                validation_findings_json=[],
                revision=1,
                digest=digest,
                status=status,
                created_by="author-1",
            )
        )
        session.flush()
        session.add(
            Approval(
                id=f"approval-{design_id}",
                organization_id=organization_id,
                subject_type=APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                subject_id=design_id,
                subject_digest=digest,
                decision=APPROVAL_DECISION_APPROVED,
                actor_subject_id="reviewer-1",
            )
        )
        if with_successful_build:
            session.add(
                BuildJob(
                    id=f"build-{design_id}",
                    organization_id=organization_id,
                    design_id=design_id,
                    design_digest=digest,
                    status=BUILD_STATUS_SUCCEEDED,
                    attempts=1,
                    artifact_key=artifact_key,
                    artifact_digest=artifact_digest,
                )
            )
        session.commit()

    return {
        "design_id": design_id,
        "design_digest": digest,
        "artifact_key": artifact_key,
        "artifact_digest": artifact_digest,
    }


def create_version(
    client: TestClient,
    asset_id: str,
    seeded_build: dict[str, str],
    *,
    version: str = "1.0.0",
    organization_id: str = "org-acme",
    subject_id: str = "author-1",
    roles: str = "author",
):
    return client.post(
        f"/api/registry/assets/{asset_id}/versions",
        headers=build_headers(
            organization_id=organization_id,
            subject_id=subject_id,
            roles=roles,
        ),
        json={
            "design_id": seeded_build["design_id"],
            "design_digest": seeded_build["design_digest"],
            "version": version,
        },
    )


def approve_version(
    client: TestClient,
    version_id: str,
    expected_digest: str,
    *,
    organization_id: str = "org-acme",
):
    return client.post(
        f"/api/registry/versions/{version_id}/reviews",
        headers=build_headers(
            organization_id=organization_id,
            subject_id="reviewer-1",
            roles="reviewer",
        ),
        json={
            "expected_digest": expected_digest,
            "decision": "approved",
        },
    )


def publish_version(
    client: TestClient,
    version_id: str,
    expected_digest: str,
    *,
    organization_id: str = "org-acme",
    channel: str = "stable",
):
    return client.post(
        f"/api/registry/versions/{version_id}/publish",
        headers=build_headers(
            organization_id=organization_id,
            subject_id="publisher-1",
            roles="registry-admin",
        ),
        json={
            "expected_digest": expected_digest,
            "channel": channel,
        },
    )


def search_assets_with_select_count(
    client: TestClient,
    *,
    subject_id: str,
    roles: str,
    params: dict[str, str],
) -> tuple[object, int]:
    search_selects = {"count": 0}

    def count_search_selects(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        del conn, cursor, parameters, context, executemany
        if statement.lstrip().upper().startswith("SELECT"):
            search_selects["count"] += 1

    event.listen(
        client.app.state.engine,
        "before_cursor_execute",
        count_search_selects,
    )
    try:
        response = client.get(
            "/api/registry/assets",
            headers=build_headers(subject_id=subject_id, roles=roles),
            params=params,
        )
    finally:
        event.remove(
            client.app.state.engine,
            "before_cursor_execute",
            count_search_selects,
        )
    return response, search_selects["count"]


def test_registry_admin_creates_org_scoped_workflow_assets(registry_client):
    created = create_asset(registry_client)

    assert created["type"] == "workflow"
    assert created["slug"] == "issue-to-pr"
    assert created["organization_id"] == "org-acme"

    duplicate = registry_client.post(
        "/api/registry/assets",
        headers=build_headers(),
        json={
            "type": "workflow",
            "slug": "issue-to-pr",
            "name": "Duplicate",
            "description": "Duplicate slug",
            "owner_subject_id": "owner-2",
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "ok": False,
        "error": "asset slug already exists",
        "code": "conflict",
    }

    other_org = create_asset(
        registry_client,
        organization_id="org-umbrella",
        name="Umbrella Issue to PR",
    )
    assert other_org["slug"] == "issue-to-pr"
    assert other_org["organization_id"] == "org-umbrella"


def test_registry_validates_asset_slug_and_semantic_version(registry_client):
    invalid_slug = registry_client.post(
        "/api/registry/assets",
        headers=build_headers(),
        json={
            "type": "workflow",
            "slug": "Issue_To_PR",
            "name": "Invalid Slug",
            "description": "Invalid slug",
            "owner_subject_id": "owner-1",
        },
    )

    assert invalid_slug.status_code == 422
    invalid_slug_payload = invalid_slug.json()
    assert invalid_slug_payload["ok"] is False
    assert invalid_slug_payload["code"] == "invalid_request"
    assert invalid_slug_payload["detail"][0]["field"] == "body.slug"

    asset = create_asset(registry_client, slug="valid-slug")
    seeded_build = seed_built_design(registry_client, design_id="design-semver")
    invalid_version = registry_client.post(
        f"/api/registry/assets/{asset['id']}/versions",
        headers=build_headers(subject_id="author-1", roles="author"),
        json={
            "design_id": seeded_build["design_id"],
            "design_digest": seeded_build["design_digest"],
            "version": "1.0",
        },
    )

    assert invalid_version.status_code == 422
    invalid_version_payload = invalid_version.json()
    assert invalid_version_payload["ok"] is False
    assert invalid_version_payload["code"] == "invalid_request"
    assert invalid_version_payload["detail"][0]["field"] == "body.version"


def test_version_creation_requires_a_built_design_with_matching_digest(
    registry_client,
):
    asset = create_asset(registry_client)
    unbuilt_design = seed_built_design(
        registry_client,
        design_id="design-unbuilt",
        status=DESIGN_STATUS_APPROVED,
        with_successful_build=False,
    )

    not_built = registry_client.post(
        f"/api/registry/assets/{asset['id']}/versions",
        headers=build_headers(subject_id="author-1", roles="author"),
        json={
            "design_id": unbuilt_design["design_id"],
            "design_digest": unbuilt_design["design_digest"],
            "version": "1.0.0",
        },
    )

    assert not_built.status_code == 422
    assert not_built.json() == {
        "ok": False,
        "error": "built design artifact required",
        "code": "invalid_lifecycle",
    }

    seeded_build = seed_built_design(registry_client)

    stale = registry_client.post(
        f"/api/registry/assets/{asset['id']}/versions",
        headers=build_headers(subject_id="author-1", roles="author"),
        json={
            "design_id": seeded_build["design_id"],
            "design_digest": "f" * 64,
            "version": "1.0.0",
        },
    )

    assert stale.status_code == 409
    assert stale.json() == {
        "ok": False,
        "error": "design digest is stale",
        "code": "stale_digest",
    }

    created = create_version(registry_client, asset["id"], seeded_build)

    assert created.status_code == 201
    version = created.json()["version"]
    expected_manifest = {
        "schema_version": 1,
        "asset": {"type": "workflow", "slug": asset["slug"]},
        "version": "1.0.0",
        "runtime": "copilot-cli",
        "design_digest": seeded_build["design_digest"],
        "artifact": {
            "sha256": seeded_build["artifact_digest"],
            "key": seeded_build["artifact_key"],
        },
        "dependencies": [],
    }

    assert version["status"] == "draft"
    assert version["channel"] == "unpublished"
    assert version["artifact_sha256"] == seeded_build["artifact_digest"]
    assert version["digest"] == hashlib.sha256(
        canonical_json_bytes(expected_manifest)
    ).hexdigest()

    manifest_response = registry_client.get(
        f"/api/registry/versions/{version['id']}/manifest",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )
    assert manifest_response.status_code == 404

    duplicate = create_version(registry_client, asset["id"], seeded_build)
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "ok": False,
        "error": "asset version already exists",
        "code": "conflict",
    }


@pytest.mark.parametrize(
    ("mode", "expected_error", "expected_code"),
    [
        ("missing", "built design artifact is unavailable", "artifact_unavailable"),
        ("non_regular", "built design artifact is unavailable", "artifact_unavailable"),
        ("unreadable", "built design artifact is unavailable", "artifact_unavailable"),
        (
            "corrupted",
            "built design artifact failed integrity check",
            "artifact_corrupted",
        ),
    ],
)
def test_version_creation_verifies_stored_artifact_bytes_before_persisting(
    registry_client,
    monkeypatch,
    mode: str,
    expected_error: str,
    expected_code: str,
):
    asset = create_asset(registry_client, slug=f"artifact-{mode.replace('_', '-')}")
    seeded_build = seed_built_design(registry_client, design_id=f"design-{mode}")
    artifact_path = (
        registry_client.app.state.settings.artifact_root / seeded_build["artifact_key"]
    )

    if mode == "missing":
        artifact_path.unlink()
    elif mode == "non_regular":
        artifact_path.unlink()
        artifact_path.mkdir()
    elif mode == "unreadable":
        def raise_unreadable(key: str):
            raise ArtifactStorageError("permission denied")

        monkeypatch.setattr(registry_client.app.state.artifact_storage, "open", raise_unreadable)
    else:
        artifact_path.write_bytes(b"corrupted bytes\n")

    response = create_version(registry_client, asset["id"], seeded_build)

    assert response.status_code == 422
    assert response.json() == {
        "ok": False,
        "error": expected_error,
        "code": expected_code,
    }
    assert str(registry_client.app.state.settings.artifact_root) not in response.text

    with Session(registry_client.app.state.engine) as session:
        versions = session.scalars(
            select(AssetVersion).where(
                AssetVersion.organization_id == "org-acme",
                AssetVersion.asset_id == asset["id"],
            )
        ).all()

    assert versions == []


def test_review_publish_and_revoke_bind_the_exact_version_digest(registry_client):
    asset = create_asset(registry_client)
    seeded_build = seed_built_design(registry_client)
    created = create_version(registry_client, asset["id"], seeded_build)
    version = created.json()["version"]

    unpublished_manifest = registry_client.get(
        f"/api/registry/versions/{version['id']}/manifest",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )
    assert unpublished_manifest.status_code == 404

    not_approved = publish_version(registry_client, version["id"], version["digest"])
    assert not_approved.status_code == 422
    assert not_approved.json() == {
        "ok": False,
        "error": "version lifecycle does not allow publish",
        "code": "invalid_lifecycle",
    }

    stale_review = approve_version(
        registry_client,
        version["id"],
        "0" * 64,
    )
    assert stale_review.status_code == 409
    assert stale_review.json() == {
        "ok": False,
        "error": "version digest is stale",
        "code": "stale_digest",
    }

    approved = approve_version(registry_client, version["id"], version["digest"])
    assert approved.status_code == 200
    approved_version = approved.json()["version"]
    assert approved_version["status"] == "approved"

    stale_publish = publish_version(
        registry_client,
        version["id"],
        "1" * 64,
    )
    assert stale_publish.status_code == 409
    assert stale_publish.json() == {
        "ok": False,
        "error": "version digest is stale",
        "code": "stale_digest",
    }

    published = publish_version(registry_client, version["id"], version["digest"])
    assert published.status_code == 200
    published_version = published.json()["version"]
    assert published_version["status"] == "published"
    assert published_version["channel"] == "stable"
    assert published_version["digest"] == version["digest"]
    assert published_version["artifact_sha256"] == version["artifact_sha256"]

    manifest_response = registry_client.get(
        f"/api/registry/versions/{version['id']}/manifest",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["artifact"]["sha256"] == version["artifact_sha256"]
    assert manifest["artifact"]["key"] == seeded_build["artifact_key"]
    assert "path" not in manifest["artifact"]
    assert "credential" not in manifest["artifact"]
    assert str(registry_client.app.state.settings.artifact_root) not in str(manifest)

    stale_revoke = registry_client.post(
        f"/api/registry/versions/{version['id']}/revoke",
        headers=build_headers(
            subject_id="publisher-1",
            roles="registry-admin",
        ),
        json={"expected_digest": "0" * 64},
    )
    assert stale_revoke.status_code == 409
    assert stale_revoke.json()["code"] == "stale_digest"

    revoke = registry_client.post(
        f"/api/registry/versions/{version['id']}/revoke",
        headers=build_headers(
            subject_id="publisher-1",
            roles="registry-admin",
        ),
        json={"expected_digest": version["digest"]},
    )
    assert revoke.status_code == 200
    assert revoke.json()["version"]["status"] == "revoked"
    assert revoke.json()["version"]["digest"] == version["digest"]
    assert revoke.json()["version"]["artifact_sha256"] == version["artifact_sha256"]

    developer_manifest = registry_client.get(
        f"/api/registry/versions/{version['id']}/manifest",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )
    assert developer_manifest.status_code == 404

    with Session(registry_client.app.state.engine) as session:
        approvals = session.scalars(
            select(Approval).where(
                Approval.subject_type == APPROVAL_SUBJECT_TYPE_ASSET_VERSION
            )
        ).all()
        stored_version = session.get(AssetVersion, version["id"])
        audit_events = session.scalars(
            select(AuditEvent).order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        ).all()

    assert len(approvals) == 1
    assert approvals[0].subject_digest == version["digest"]
    assert stored_version is not None
    assert stored_version.manifest_json == manifest
    assert stored_version.artifact_key == seeded_build["artifact_key"]
    assert stored_version.artifact_digest == version["artifact_sha256"]
    assert [event.action for event in audit_events] == [
        "registry.asset.created",
        "registry.version.created",
        "registry.version.reviewed",
        "registry.version.published",
        "registry.version.revoked",
    ]


def test_developer_search_uses_one_query_and_keeps_highest_semantic_version(
    registry_client,
):
    stable_asset = create_asset(registry_client, slug="issue-to-pr", name="Stable")
    semver_build = seed_built_design(registry_client, design_id="design-stable-2-0-0")
    semver_winner = create_version(
        registry_client,
        stable_asset["id"],
        semver_build,
        version="2.0.0",
    ).json()["version"]
    assert approve_version(
        registry_client,
        semver_winner["id"],
        semver_winner["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            semver_winner["id"],
            semver_winner["digest"],
            channel="stable",
        ).status_code
        == 200
    )
    later_patch_build = seed_built_design(
        registry_client,
        design_id="design-stable-1-0-1",
        artifact_bytes=b"later patch workflow bytes\n",
    )
    later_patch = create_version(
        registry_client,
        stable_asset["id"],
        later_patch_build,
        version="1.0.1",
    ).json()["version"]
    assert approve_version(
        registry_client,
        later_patch["id"],
        later_patch["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            later_patch["id"],
            later_patch["digest"],
            channel="pilot",
        ).status_code
        == 200
    )

    pilot_asset = create_asset(registry_client, slug="issue-to-pilot", name="Pilot")
    pilot_build = seed_built_design(registry_client, design_id="design-pilot")
    pilot_version = create_version(
        registry_client,
        pilot_asset["id"],
        pilot_build,
        version="3.0.0",
    ).json()["version"]
    assert approve_version(
        registry_client,
        pilot_version["id"],
        pilot_version["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            pilot_version["id"],
            pilot_version["digest"],
            channel="pilot",
        ).status_code
        == 200
    )

    revoked_asset = create_asset(registry_client, slug="issue-to-revoke", name="Revoked")
    revoked_build = seed_built_design(registry_client, design_id="design-revoked")
    revoked_version = create_version(
        registry_client,
        revoked_asset["id"],
        revoked_build,
        version="3.0.0",
    ).json()["version"]
    assert approve_version(
        registry_client,
        revoked_version["id"],
        revoked_version["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            revoked_version["id"],
            revoked_version["digest"],
            channel="stable",
        ).status_code
        == 200
    )
    assert (
        registry_client.post(
            f"/api/registry/versions/{revoked_version['id']}/revoke",
            headers=build_headers(
                subject_id="publisher-1",
                roles="registry-admin",
            ),
            json={"expected_digest": revoked_version["digest"]},
        ).status_code
        == 200
    )

    draft_asset = create_asset(registry_client, slug="issue-to-draft", name="Draft")
    draft_build = seed_built_design(registry_client, design_id="design-draft")
    draft_version = create_version(
        registry_client,
        draft_asset["id"],
        draft_build,
        version="4.0.0",
    ).json()["version"]
    assert draft_version["status"] == "draft"

    search_response, search_select_count = search_assets_with_select_count(
        registry_client,
        subject_id="developer-1",
        roles="developer",
        params={"query": "issue", "type": "workflow"},
    )

    assert search_response.status_code == 200
    assert search_select_count == 1
    assert search_response.json() == {
        "ok": True,
        "items": [
            {
                "id": pilot_asset["id"],
                "type": "workflow",
                "slug": "issue-to-pilot",
                "name": "Pilot",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [
                    {
                        "id": pilot_version["id"],
                        "version": "3.0.0",
                        "digest": pilot_version["digest"],
                        "status": "published",
                        "channel": "pilot",
                        "artifact_sha256": pilot_build["artifact_digest"],
                    }
                ],
            },
            {
                "id": stable_asset["id"],
                "type": "workflow",
                "slug": "issue-to-pr",
                "name": "Stable",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [
                    {
                        "id": semver_winner["id"],
                        "version": "2.0.0",
                        "digest": semver_winner["digest"],
                        "status": "published",
                        "channel": "stable",
                        "artifact_sha256": semver_build["artifact_digest"],
                    },
                    {
                        "id": later_patch["id"],
                        "version": "1.0.1",
                        "digest": later_patch["digest"],
                        "status": "published",
                        "channel": "pilot",
                        "artifact_sha256": later_patch_build["artifact_digest"],
                    },
                ],
            }
        ],
    }

    stable_search_response, stable_search_select_count = search_assets_with_select_count(
        registry_client,
        subject_id="developer-1",
        roles="developer",
        params={"query": "issue", "type": "workflow", "channel": "stable"},
    )

    assert stable_search_response.status_code == 200
    assert stable_search_select_count == 1
    assert stable_search_response.json() == {
        "ok": True,
        "items": [
            {
                "id": stable_asset["id"],
                "type": "workflow",
                "slug": "issue-to-pr",
                "name": "Stable",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [
                    {
                        "id": semver_winner["id"],
                        "version": "2.0.0",
                        "digest": semver_winner["digest"],
                        "status": "published",
                        "channel": "stable",
                        "artifact_sha256": semver_build["artifact_digest"],
                    }
                ],
            }
        ],
    }

    detail_response = registry_client.get(
        f"/api/registry/assets/{stable_asset['slug']}",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert detail_response.status_code == 200
    assert detail_response.json() == {
        "ok": True,
        "asset": {
            "id": stable_asset["id"],
            "organization_id": "org-acme",
            "type": "workflow",
            "slug": "issue-to-pr",
            "name": "Stable",
            "language": "ko",
            "description": "Publishes a workflow package",
            "owner_subject_id": "owner-1",
            "visibility": "internal",
            "lifecycle": "active",
            "versions": [
                {
                    "id": semver_winner["id"],
                    "version": "2.0.0",
                    "digest": semver_winner["digest"],
                    "status": "published",
                    "channel": "stable",
                    "artifact_sha256": semver_build["artifact_digest"],
                },
                {
                    "id": later_patch["id"],
                    "version": "1.0.1",
                    "digest": later_patch["digest"],
                    "status": "published",
                    "channel": "pilot",
                    "artifact_sha256": later_patch_build["artifact_digest"],
                }
            ],
        },
    }

    draft_detail = registry_client.get(
        f"/api/registry/assets/{draft_asset['slug']}",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )
    assert draft_detail.status_code == 404


def test_privileged_search_uses_one_query_and_preserves_unpublished_visibility(
    registry_client,
):
    stable_asset = create_asset(registry_client, slug="issue-to-pr", name="Stable")
    stable_build = seed_built_design(registry_client, design_id="design-stable")
    stable_version = create_version(
        registry_client,
        stable_asset["id"],
        stable_build,
        version="1.0.0",
    ).json()["version"]
    assert approve_version(
        registry_client,
        stable_version["id"],
        stable_version["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            stable_version["id"],
            stable_version["digest"],
            channel="stable",
        ).status_code
        == 200
    )

    pilot_asset = create_asset(registry_client, slug="issue-to-pilot", name="Pilot")
    pilot_build = seed_built_design(registry_client, design_id="design-pilot")
    pilot_version = create_version(
        registry_client,
        pilot_asset["id"],
        pilot_build,
        version="2.0.0",
    ).json()["version"]
    assert approve_version(
        registry_client,
        pilot_version["id"],
        pilot_version["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            pilot_version["id"],
            pilot_version["digest"],
            channel="pilot",
        ).status_code
        == 200
    )

    revoked_asset = create_asset(registry_client, slug="issue-to-revoke", name="Revoked")
    revoked_build = seed_built_design(registry_client, design_id="design-revoked")
    revoked_version = create_version(
        registry_client,
        revoked_asset["id"],
        revoked_build,
        version="3.0.0",
    ).json()["version"]
    assert approve_version(
        registry_client,
        revoked_version["id"],
        revoked_version["digest"],
    ).status_code == 200
    assert (
        publish_version(
            registry_client,
            revoked_version["id"],
            revoked_version["digest"],
            channel="stable",
        ).status_code
        == 200
    )
    assert (
        registry_client.post(
            f"/api/registry/versions/{revoked_version['id']}/revoke",
            headers=build_headers(
                subject_id="publisher-1",
                roles="registry-admin",
            ),
            json={"expected_digest": revoked_version["digest"]},
        ).status_code
        == 200
    )

    draft_asset = create_asset(registry_client, slug="issue-to-draft", name="Draft")
    draft_build = seed_built_design(registry_client, design_id="design-draft")
    draft_version = create_version(
        registry_client,
        draft_asset["id"],
        draft_build,
        version="4.0.0",
    ).json()["version"]

    search_response, search_select_count = search_assets_with_select_count(
        registry_client,
        subject_id="publisher-1",
        roles="registry-admin",
        params={"query": "issue", "type": "workflow", "channel": "stable"},
    )

    assert search_response.status_code == 200
    assert search_select_count == 1
    assert search_response.json() == {
        "ok": True,
        "items": [
            {
                "id": draft_asset["id"],
                "type": "workflow",
                "slug": "issue-to-draft",
                "name": "Draft",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [],
            },
            {
                "id": pilot_asset["id"],
                "type": "workflow",
                "slug": "issue-to-pilot",
                "name": "Pilot",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [],
            },
            {
                "id": stable_asset["id"],
                "type": "workflow",
                "slug": "issue-to-pr",
                "name": "Stable",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [
                    {
                        "id": stable_version["id"],
                        "version": "1.0.0",
                        "digest": stable_version["digest"],
                        "status": "published",
                        "channel": "stable",
                        "artifact_sha256": stable_build["artifact_digest"],
                    }
                ],
            },
            {
                "id": revoked_asset["id"],
                "type": "workflow",
                "slug": "issue-to-revoke",
                "name": "Revoked",
                "language": "ko",
                "description": "Publishes a workflow package",
                "versions": [
                    {
                        "id": revoked_version["id"],
                        "version": "3.0.0",
                        "digest": revoked_version["digest"],
                        "status": "revoked",
                        "channel": "stable",
                        "artifact_sha256": revoked_build["artifact_digest"],
                    }
                ],
            },
        ],
    }
    assert draft_version["status"] == "draft"


def test_registry_re_raises_unexpected_integrity_errors(registry_client, monkeypatch):
    def explode_create_asset(self, organization_id, request):
        del self, organization_id, request
        raise IntegrityError(
            "INSERT INTO assets ...",
            {},
            sqlite3.IntegrityError("NOT NULL constraint failed: assets.name"),
        )

    def no_duplicate(self, organization_id, slug):
        del self, organization_id, slug
        return None

    monkeypatch.setattr(RegistryRepository, "create_asset", explode_create_asset)
    monkeypatch.setattr(RegistryRepository, "get_asset_by_slug", no_duplicate)

    with TestClient(registry_client.app, raise_server_exceptions=False) as unsafe_client:
        response = unsafe_client.post(
            "/api/registry/assets",
            headers=build_headers(),
            json={
                "type": "workflow",
                "slug": "unexpected-integrity",
                "name": "Unexpected Integrity",
                "description": "Should bubble to generic handler",
                "owner_subject_id": "owner-1",
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "ok": False,
        "error": "internal server error",
        "code": "internal_error",
    }
