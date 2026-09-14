from fastapi.testclient import TestClient

from web.tests.test_registry_api import (
    approve_version,
    build_headers,
    create_asset,
    create_version,
    publish_version,
    registry_client,
    seed_built_design,
)


def test_cross_tenant_registry_queries_return_not_found(registry_client: TestClient):
    asset = create_asset(registry_client)
    seeded_build = seed_built_design(registry_client)
    created = create_version(registry_client, asset["id"], seeded_build)
    version = created.json()["version"]
    assert approve_version(
        registry_client,
        version["id"],
        version["digest"],
    ).status_code == 200
    assert publish_version(
        registry_client,
        version["id"],
        version["digest"],
    ).status_code == 200

    asset_detail = registry_client.get(
        f"/api/registry/assets/{asset['slug']}",
        headers=build_headers(
            organization_id="org-umbrella",
            subject_id="developer-2",
            roles="developer",
        ),
    )
    assert asset_detail.status_code == 404
    assert asset_detail.json() == {
        "ok": False,
        "error": "asset not found",
        "code": "error",
    }

    create_other_tenant_version = registry_client.post(
        f"/api/registry/assets/{asset['id']}/versions",
        headers=build_headers(
            organization_id="org-umbrella",
            subject_id="author-2",
            roles="author",
        ),
        json={
            "design_id": seeded_build["design_id"],
            "design_digest": seeded_build["design_digest"],
            "version": "1.0.1",
        },
    )
    assert create_other_tenant_version.status_code == 404
    assert create_other_tenant_version.json() == {
        "ok": False,
        "error": "asset not found",
        "code": "error",
    }

    manifest = registry_client.get(
        f"/api/registry/versions/{version['id']}/manifest",
        headers=build_headers(
            organization_id="org-umbrella",
            subject_id="developer-2",
            roles="developer",
        ),
    )
    assert manifest.status_code == 404
    assert manifest.json() == {
        "ok": False,
        "error": "version not found",
        "code": "error",
    }

    publish = registry_client.post(
        f"/api/registry/versions/{version['id']}/publish",
        headers=build_headers(
            organization_id="org-umbrella",
            subject_id="publisher-2",
            roles="registry-admin",
        ),
        json={
            "expected_digest": version["digest"],
            "channel": "stable",
        },
    )
    assert publish.status_code == 404
    assert publish.json() == {
        "ok": False,
        "error": "version not found",
        "code": "error",
    }
