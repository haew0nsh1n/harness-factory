from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from web.api.builds.worker import _run_once
from web.api.config import Settings, get_settings
from web.api.db import Base
from web.api.main import create_app
from web.api.organizations.models import Organization
from web.tests.test_build_worker import build_design_payload

FORBIDDEN_AUDIT_KEY_FRAGMENTS = frozenset(
    {
        "token",
        "password",
        "secret",
        "cookie",
        "credential",
        "prompt",
        "source_code",
        "diff",
        "content",
    }
)
FIXTURE_ROOT = Path(__file__).resolve().parents[2]


def build_headers(
    *,
    organization_id: str,
    subject_id: str,
    roles: str,
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
        "X-HF-Roles": roles,
    }


@pytest.fixture
def acceptance_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "acceptance.db"
    settings = Settings(
        auth_mode="development",
            allow_insecure_development_auth=True,
        database_url=f"sqlite+pysqlite:///{database_path}",
        catalog_root=FIXTURE_ROOT / "catalog",
        artifact_root=tmp_path / "artifacts",
    )
    app = create_app(settings)
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

    monkeypatch.setenv("HF_AUTH_MODE", "development")
    monkeypatch.setenv("HF_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("HF_CATALOG_ROOT", str(settings.catalog_root))
    monkeypatch.setenv("HF_ARTIFACT_ROOT", str(settings.artifact_root))
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_end_to_end_acceptance_flow_blocks_cross_tenant_reads_and_keeps_audit_keys_safe(
    acceptance_client: TestClient,
):
    create_response = acceptance_client.post(
        "/api/designs",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="author-1",
            roles="author",
        ),
        json=build_design_payload(),
    )
    assert create_response.status_code == 201
    design = create_response.json()["design"]

    validate_response = acceptance_client.post(
        f"/api/designs/{design['id']}/validate",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="author-1",
            roles="author",
        ),
    )
    assert validate_response.status_code == 200
    validated_design = validate_response.json()["design"]

    approve_design_response = acceptance_client.post(
        f"/api/designs/{design['id']}/reviews",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="reviewer-1",
            roles="reviewer",
        ),
        json={
            "expected_digest": validated_design["digest"],
            "decision": "approved",
        },
    )
    assert approve_design_response.status_code == 200
    approved_design = approve_design_response.json()["design"]
    assert approved_design["status"] == "approved"

    queue_build_response = acceptance_client.post(
        f"/api/designs/{design['id']}/builds",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="author-1",
            roles="author",
        ),
        json={"expected_digest": approved_design["digest"]},
    )
    assert queue_build_response.status_code == 202
    build = queue_build_response.json()["build"]
    assert build["status"] == "queued"

    worker_result = _run_once()
    assert worker_result == {
        "ok": True,
        "processed": True,
        "build_id": build["id"],
        "status": "succeeded",
    }

    build_status_response = acceptance_client.get(
        f"/api/builds/{build['id']}",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="author-1",
            roles="author",
        ),
    )
    assert build_status_response.status_code == 200
    succeeded_build = build_status_response.json()["build"]
    assert succeeded_build["status"] == "succeeded"
    assert succeeded_build["artifact_key"].endswith("/package.tar")

    create_asset_response = acceptance_client.post(
        "/api/registry/assets",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="registry-admin-1",
            roles="registry-admin",
        ),
        json={
            "type": "workflow",
            "slug": "github-issue-authoring",
            "name": "GitHub Issue Authoring",
            "description": "Approved workflow package for the example issue flow.",
            "owner_subject_id": "owner-1",
        },
    )
    assert create_asset_response.status_code == 201
    asset = create_asset_response.json()["asset"]

    create_version_response = acceptance_client.post(
        f"/api/registry/assets/{asset['id']}/versions",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="author-1",
            roles="author",
        ),
        json={
            "design_id": approved_design["id"],
            "design_digest": approved_design["digest"],
            "version": "1.0.0",
        },
    )
    assert create_version_response.status_code == 201
    version = create_version_response.json()["version"]

    approve_version_response = acceptance_client.post(
        f"/api/registry/versions/{version['id']}/reviews",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="reviewer-1",
            roles="reviewer",
        ),
        json={
            "expected_digest": version["digest"],
            "decision": "approved",
        },
    )
    assert approve_version_response.status_code == 200
    approved_version = approve_version_response.json()["version"]
    assert approved_version["status"] == "approved"

    publish_response = acceptance_client.post(
        f"/api/registry/versions/{version['id']}/publish",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="registry-admin-1",
            roles="registry-admin",
        ),
        json={
            "expected_digest": approved_version["digest"],
            "channel": "stable",
        },
    )
    assert publish_response.status_code == 200
    published_version = publish_response.json()["version"]
    assert published_version["status"] == "published"
    assert published_version["channel"] == "stable"

    search_response = acceptance_client.get(
        "/api/registry/assets?type=workflow&query=github",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="developer-1",
            roles="developer",
        ),
    )
    assert search_response.status_code == 200
    assert search_response.json()["items"] == [
        {
            "id": asset["id"],
            "type": "workflow",
            "slug": "github-issue-authoring",
            "name": "GitHub Issue Authoring",
            "description": "Approved workflow package for the example issue flow.",
            "versions": [
                {
                    "id": published_version["id"],
                    "version": "1.0.0",
                    "digest": published_version["digest"],
                    "status": "published",
                    "channel": "stable",
                    "artifact_sha256": published_version["artifact_sha256"],
                }
            ],
        }
    ]

    manifest_response = acceptance_client.get(
        f"/api/registry/versions/{published_version['id']}/manifest",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="developer-1",
            roles="developer",
        ),
    )
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["asset"] == {
        "type": "workflow",
        "slug": "github-issue-authoring",
    }
    assert manifest["version"] == "1.0.0"
    assert manifest["design_digest"] == approved_design["digest"]
    assert manifest["artifact"]["sha256"] == published_version["artifact_sha256"]

    for path in (
        f"/api/designs/{design['id']}",
        f"/api/builds/{build['id']}",
        f"/api/registry/assets/{asset['slug']}",
        f"/api/registry/versions/{published_version['id']}/manifest",
    ):
        response = acceptance_client.get(
            path,
            headers=build_headers(
                organization_id="org-umbrella",
                subject_id="developer-2",
                roles="developer",
            ),
        )
        assert response.status_code == 404

    create_other_tenant_version = acceptance_client.post(
        f"/api/registry/assets/{asset['id']}/versions",
        headers=build_headers(
            organization_id="org-umbrella",
            subject_id="author-2",
            roles="author",
        ),
        json={
            "design_id": approved_design["id"],
            "design_digest": approved_design["digest"],
            "version": "1.0.1",
        },
    )
    assert create_other_tenant_version.status_code == 404
    assert create_other_tenant_version.json() == {
        "ok": False,
        "error": "asset not found",
        "code": "error",
    }

    audit_response = acceptance_client.get(
        "/api/audit",
        headers=build_headers(
            organization_id="org-acme",
            subject_id="org-admin-1",
            roles="org-admin",
        ),
    )
    assert audit_response.status_code == 200
    audit_items = audit_response.json()["items"]
    assert [item["action"] for item in audit_items] == [
        "design.reviewed",
        "registry.asset.created",
        "registry.version.created",
        "registry.version.reviewed",
        "registry.version.published",
    ]
    for item in audit_items:
        for key in item["summary"]:
            lowered = key.lower()
            assert not any(
                fragment in lowered for fragment in FORBIDDEN_AUDIT_KEY_FRAGMENTS
            ), key
