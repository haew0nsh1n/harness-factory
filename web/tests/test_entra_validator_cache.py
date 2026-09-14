from __future__ import annotations

from fastapi.testclient import TestClient
from jwt import PyJWKClient

from web.api.config import Settings
import web.api.identity.entra as entra_module
from web.api.identity.entra import EntraTokenValidator
from web.api.main import create_app


def entra_settings() -> Settings:
    return Settings(
        auth_mode="entra",
        entra_tenant_id="tenant-123",
        entra_client_id="client-123",
        entra_jwks_url="https://entra.example.test/discovery/keys",
    )


def test_validator_is_created_once_at_startup(monkeypatch) -> None:
    constructions: list[str] = []

    class CountingJWKClient(PyJWKClient):
        def __init__(self, uri, *args, **kwargs):
            constructions.append(uri)
            super().__init__(uri, *args, **kwargs)

    monkeypatch.setattr(entra_module, "PyJWKClient", CountingJWKClient)

    app = create_app(entra_settings())

    assert isinstance(app.state.entra_validator, EntraTokenValidator)
    assert len(constructions) == 1

    with TestClient(app) as client:
        for _ in range(3):
            response = client.get(
                "/api/whoami", headers={"Authorization": "Bearer not-a-token"}
            )
            assert response.status_code == 401

    assert len(constructions) == 1


def test_validator_instance_is_reused_across_requests(
    monkeypatch, entra_app, seed_identity_data, stub_entra_jwks, build_entra_token
) -> None:
    del monkeypatch
    seed_identity_data(
        [
            {
                "id": "org-acme",
                "entra_tenant_id": "tenant-123",
                "name": "Acme",
            }
        ],
        [
            {
                "organization_id": "org-acme",
                "subject_id": "oid-123",
                "roles_json": ["author"],
            }
        ],
    )
    validator = entra_app.state.entra_validator
    assert validator is not None

    with TestClient(entra_app) as client:
        for _ in range(2):
            response = client.get(
                "/api/whoami",
                headers={"Authorization": f"Bearer {build_entra_token()}"},
            )
            assert response.status_code == 200

    assert entra_app.state.entra_validator is validator
