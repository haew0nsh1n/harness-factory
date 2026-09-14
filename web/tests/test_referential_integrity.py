from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from web.api.config import Settings
from web.api.db import Base
from web.api.main import create_app
from web.api.organizations.models import Organization
from web.tests.test_design_api import build_design_request

FIXTURE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def integrity_client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'integrity.db'}",
            catalog_root=FIXTURE_ROOT / "catalog",
            artifact_root=tmp_path / "artifacts",
        )
    )
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as session:
        session.add(
            Organization(id="org-acme", entra_tenant_id="tenant-acme", name="Acme")
        )
        session.commit()
    with TestClient(app) as client:
        yield client


def test_design_write_for_unknown_tenant_returns_conflict(integrity_client) -> None:
    response = integrity_client.post(
        "/api/designs",
        headers={
            "X-HF-Organization": "org-missing",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "author",
        },
        json=build_design_request(),
    )

    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "error": "referenced tenant or resource does not exist",
        "code": "missing_reference",
    }


def test_known_tenant_design_write_still_succeeds(integrity_client) -> None:
    response = integrity_client.post(
        "/api/designs",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "user-1",
            "X-HF-Roles": "author",
        },
        json=build_design_request(),
    )

    assert response.status_code == 201
