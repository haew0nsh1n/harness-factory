from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from web.api.registry.models import AssetVersion
from web.tests.test_registry_api import (  # noqa: F401
    approve_version,
    build_headers,
    create_asset,
    create_version,
    publish_version,
    registry_client,
    seed_built_design,
)


def create_published_version(
    client: TestClient,
    asset_id: str,
    *,
    design_id: str,
    version: str,
    channel: str = "stable",
) -> dict[str, object]:
    seeded = seed_built_design(client, design_id=design_id)
    created = create_version(client, asset_id, seeded, version=version)
    assert created.status_code == 201, created.text
    payload = created.json()["version"]
    assert (
        approve_version(client, payload["id"], payload["digest"]).status_code == 200
    )
    published = publish_version(
        client, payload["id"], payload["digest"], channel=channel
    )
    assert published.status_code == 200, published.text
    return published.json()["version"]


def version_rows(client: TestClient) -> dict[str, AssetVersion]:
    with Session(client.app.state.engine) as session:
        rows = session.scalars(select(AssetVersion)).all()
        return {row.version: row for row in rows}


def test_publishing_demotes_previous_published_version_in_same_channel(
    registry_client,
) -> None:
    asset = create_asset(registry_client, slug="lifecycle-demote")

    first = create_published_version(
        registry_client, asset["id"], design_id="design-l1", version="1.0.0"
    )
    second = create_published_version(
        registry_client, asset["id"], design_id="design-l2", version="1.1.0"
    )

    rows = version_rows(registry_client)
    assert rows["1.0.0"].status == "deprecated"
    assert rows["1.0.0"].channel == "stable"
    assert rows["1.1.0"].status == "published"
    assert first["status"] == "published"
    assert second["status"] == "published"


def test_publishing_preserves_other_channels(registry_client) -> None:
    asset = create_asset(registry_client, slug="lifecycle-channels")

    create_published_version(
        registry_client,
        asset["id"],
        design_id="design-p1",
        version="1.0.0",
        channel="pilot",
    )
    create_published_version(
        registry_client,
        asset["id"],
        design_id="design-s1",
        version="2.0.0",
        channel="stable",
    )

    rows = version_rows(registry_client)
    assert rows["1.0.0"].status == "published"
    assert rows["1.0.0"].channel == "pilot"
    assert rows["2.0.0"].status == "published"
    assert rows["2.0.0"].channel == "stable"


def test_demotion_is_recorded_in_the_audit_log(registry_client) -> None:
    asset = create_asset(registry_client, slug="lifecycle-audit")
    create_published_version(
        registry_client, asset["id"], design_id="design-a1", version="1.0.0"
    )
    create_published_version(
        registry_client, asset["id"], design_id="design-a2", version="1.0.1"
    )

    events = registry_client.get(
        "/api/audit", headers=build_headers(roles="org-admin")
    )

    assert events.status_code == 200
    actions = [event["action"] for event in events.json()["items"]]
    assert "registry.version.deprecated" in actions


def test_revoke_requires_exact_expected_digest(registry_client) -> None:
    asset = create_asset(registry_client, slug="lifecycle-revoke")
    published = create_published_version(
        registry_client, asset["id"], design_id="design-r1", version="1.0.0"
    )

    stale = registry_client.post(
        f"/api/registry/versions/{published['id']}/revoke",
        headers=build_headers(roles="registry-admin"),
        json={"expected_digest": "0" * 64},
    )

    assert stale.status_code == 409
    assert stale.json() == {
        "ok": False,
        "error": "version digest is stale",
        "code": "stale_digest",
    }
    assert version_rows(registry_client)["1.0.0"].status == "published"

    revoked = registry_client.post(
        f"/api/registry/versions/{published['id']}/revoke",
        headers=build_headers(roles="registry-admin"),
        json={"expected_digest": published["digest"]},
    )

    assert revoked.status_code == 200
    assert revoked.json()["version"]["status"] == "revoked"


def test_revoke_requires_expected_digest_field(registry_client) -> None:
    asset = create_asset(registry_client, slug="lifecycle-revoke-missing")
    published = create_published_version(
        registry_client, asset["id"], design_id="design-r2", version="1.0.0"
    )

    response = registry_client.post(
        f"/api/registry/versions/{published['id']}/revoke",
        headers=build_headers(roles="registry-admin"),
        json={},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
