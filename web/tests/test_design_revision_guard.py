from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from harness_factory import load_json
from web.api.config import Settings
from web.api.db import Base
from web.api.main import create_app
from web.api.organizations.models import Organization


ROOT = Path(__file__).resolve().parents[2]


def build_design_request():
    profile = load_json(ROOT / "examples/github-issue/profile.json")
    return {
        "customer_id": profile["customer_id"],
        "name": profile["name"],
        "profile": profile,
        "workflow": load_json(ROOT / "examples/github-issue/workflow.json"),
        "scenarios": load_json(ROOT / "examples/github-issue/scenarios.json"),
        "catalog": load_json(ROOT / "catalog/catalog.json"),
    }


def build_headers(roles: str = "author"):
    return {
        "X-HF-Organization": "org-acme",
        "X-HF-Subject": "user-1",
        "X-HF-Roles": roles,
    }


@pytest.fixture
def design_client():
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url="sqlite+pysqlite:///:memory:",
            catalog_root=ROOT / "catalog",
        )
    )
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as session:
        session.add(
            Organization(
                id="org-acme",
                entra_tenant_id="tenant-acme",
                name="Acme",
            )
        )
        session.commit()
    with TestClient(app) as client:
        yield client


def test_expected_digest_guards_draft_replacement(design_client):
    created = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_request(),
    ).json()["design"]
    first_update = build_design_request()
    first_update["expected_digest"] = created["digest"]
    first_update["workflow"] = deepcopy(first_update["workflow"])
    first_update["workflow"]["goal"] = "First guarded edit."

    accepted = design_client.put(
        f"/api/designs/{created['id']}",
        headers=build_headers(),
        json=first_update,
    )
    stale = design_client.put(
        f"/api/designs/{created['id']}",
        headers=build_headers(),
        json={
            **build_design_request(),
            "expected_digest": created["digest"],
        },
    )

    assert accepted.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_digest"
    current = design_client.get(
        f"/api/designs/{created['id']}", headers=build_headers()
    ).json()["design"]
    assert current["revision"] == 2
    assert current["workflow"]["goal"] == "First guarded edit."


def test_legacy_replacement_without_expected_digest_remains_supported(design_client):
    created = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_request(),
    ).json()["design"]
    request = build_design_request()
    request["name"] = "Legacy caller"

    response = design_client.put(
        f"/api/designs/{created['id']}",
        headers=build_headers(),
        json=request,
    )

    assert response.status_code == 200
    assert response.json()["design"]["name"] == "Legacy caller"
    assert response.json()["design"]["revision"] == 2


def test_guarded_edit_of_approved_design_clears_effective_approval(design_client):
    created = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_request(),
    ).json()["design"]
    validated = design_client.post(
        f"/api/designs/{created['id']}/validate",
        headers=build_headers(),
    ).json()["design"]
    approved = design_client.post(
        f"/api/designs/{created['id']}/reviews",
        headers=build_headers(roles="reviewer"),
        json={"expected_digest": validated["digest"], "decision": "approved"},
    ).json()["design"]
    request = build_design_request()
    request["expected_digest"] = approved["digest"]
    request["workflow"] = deepcopy(request["workflow"])
    request["workflow"]["goal"] = "Changed after exact-digest review."

    response = design_client.put(
        f"/api/designs/{created['id']}",
        headers=build_headers(),
        json=request,
    )

    assert response.status_code == 200
    assert response.json()["design"]["status"] == "draft"
    assert response.json()["design"]["revision"] == 2
