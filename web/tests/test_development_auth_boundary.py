import pytest
from fastapi.testclient import TestClient

from web.api.config import Settings
from web.api.main import InsecureDevelopmentAuthNotAllowed, create_app


def test_development_mode_refuses_startup_without_explicit_opt_in() -> None:
    with pytest.raises(InsecureDevelopmentAuthNotAllowed):
        create_app(Settings(auth_mode="development"))


def test_development_mode_starts_with_explicit_opt_in() -> None:
    app = create_app(
        Settings(auth_mode="development", allow_insecure_development_auth=True)
    )

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_entra_mode_does_not_require_development_opt_in() -> None:
    app = create_app(
        Settings(
            auth_mode="entra",
            entra_tenant_id="tenant-123",
            entra_client_id="client-123",
            entra_jwks_url="https://entra.example.test/discovery/keys",
        )
    )

    assert app.state.settings.allow_insecure_development_auth is False


def test_development_headers_rejected_when_opt_in_is_revoked_after_startup() -> None:
    settings = Settings(
        auth_mode="development", allow_insecure_development_auth=True
    )
    app = create_app(settings)
    app.state.settings = settings.model_copy(
        update={"allow_insecure_development_auth": False}
    )

    response = TestClient(app).get(
        "/api/whoami",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "author",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
