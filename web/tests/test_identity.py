from importlib import import_module
from datetime import timedelta

from fastapi import Depends
from fastapi.testclient import TestClient


def test_whoami_returns_development_identity(development_client):
    response = development_client.get(
        "/api/whoami",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "author,developer",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "actor": {
            "organization_id": "org-acme",
            "subject_id": "user-1",
            "roles": ["author", "developer"],
        },
    }


def test_whoami_requires_all_development_headers(development_client):
    response = development_client.get(
        "/api/whoami",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }
    assert "missing-kid" not in response.text


def test_whoami_rejects_unknown_development_roles(development_client):
    response = development_client.get(
        "/api/whoami",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "author,superuser",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "required role missing",
        "code": "forbidden",
    }


def test_entra_mode_rejects_development_headers(entra_client):
    response = entra_client.get(
        "/api/whoami",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "author,developer",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_entra_mode_returns_database_backed_identity_only(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[
            {
                "organization_id": "org-acme",
                "subject_id": "oid-123",
                "roles_json": ["developer", "author"],
            }
        ],
    )
    token = build_entra_token(extra_claims={"roles": ["registry-admin"]})

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "actor": {
            "organization_id": "org-acme",
            "subject_id": "oid-123",
            "roles": ["author", "developer"],
        },
    }


def test_entra_mode_rejects_expired_tokens(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(expires_delta=timedelta(minutes=-1))

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_entra_mode_rejects_tokens_that_are_not_yet_valid(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(not_before_delta=timedelta(minutes=5))

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"******"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_entra_mode_rejects_wrong_audience(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(audience="wrong-client")

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_entra_mode_rejects_wrong_issuer(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(
        issuer="https://login.microsoftonline.com/other-tenant/v2.0"
    )

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_entra_mode_rejects_unknown_tenant_without_echoing_claims(
    entra_app, stub_entra_jwks, build_entra_token
):
    token = build_entra_token(tenant_id="tenant-missing")

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }
    assert "tenant-missing" not in response.text
    assert "oid-123" not in response.text


def test_entra_mode_rejects_missing_membership_without_echoing_claims(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(subject_id="oid-missing")

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "required role missing",
        "code": "forbidden",
    }
    assert "oid-missing" not in response.text
    assert "tenant-123" not in response.text


def test_entra_mode_rejects_algorithm_substitution(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(algorithm="HS256")

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_entra_mode_rejects_jwks_key_resolution_failures(
    entra_app,
    seed_identity_data,
    stub_entra_jwks,
    build_entra_token,
):
    seed_identity_data(
        organizations=[
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        memberships=[],
    )
    token = build_entra_token(key_id="missing-kid")

    with TestClient(entra_app) as client:
        response = client.get(
            "/api/whoami", headers={"Authorization": f"******"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": "authentication required",
        "code": "unauthorized",
    }


def test_require_roles_blocks_authenticated_actor_without_allowed_role(
    development_client,
):
    dependencies_module = import_module("web.api.identity.dependencies")
    require_roles = getattr(dependencies_module, "require_roles", None)

    assert callable(require_roles)

    @development_client.app.get("/api/author-only")
    def author_only(actor=Depends(require_roles("author"))):
        return {
            "ok": True,
            "actor": {
                "organization_id": actor.organization_id,
                "subject_id": actor.subject_id,
                "roles": sorted(actor.roles),
            },
        }

    response = development_client.get(
        "/api/author-only",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "developer",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "required role missing",
        "code": "forbidden",
    }
