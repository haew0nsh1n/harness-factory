from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from harness_factory import load_json
from web.api.config import Settings
from web.api.db import Base
from web.api.designs.digest import design_digest
from web.api.main import create_app
from web.api.organizations.models import Organization


FIXTURE_ROOT = Path(__file__).resolve().parents[2]


def load_design_fixture(name: str) -> dict[str, object]:
    if name == "catalog":
        return load_json(FIXTURE_ROOT / "catalog" / "catalog.json")
    return load_json(FIXTURE_ROOT / "examples" / "github-issue" / f"{name}.json")


def build_design_request() -> dict[str, Any]:
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
    organization_id: str = "org-acme", roles: str = "author"
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": "user-1",
        "X-HF-Roles": roles,
    }


@pytest.fixture
def design_client() -> TestClient:
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url="sqlite+pysqlite:///:memory:",
            catalog_root=FIXTURE_ROOT / "catalog",
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


def test_author_can_create_list_get_and_update_a_draft_design(design_client):
    create_response = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_request(),
    )

    assert create_response.status_code == 201
    created_design = create_response.json()["design"]
    assert created_design["customer_id"] == "example-team"
    assert created_design["revision"] == 1
    assert created_design["status"] == "draft"
    assert created_design["validation_findings"] is None

    list_response = design_client.get("/api/designs", headers=build_headers())

    assert list_response.status_code == 200
    listed_designs = list_response.json()["items"]
    assert len(listed_designs) == 1
    assert listed_designs[0]["id"] == created_design["id"]
    assert listed_designs[0]["digest"] == created_design["digest"]
    assert listed_designs[0]["status"] == "draft"
    assert listed_designs[0]["validation_findings"] is None

    get_response = design_client.get(
        f"/api/designs/{created_design['id']}",
        headers=build_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["design"] == created_design

    update_request = build_design_request()
    update_request["workflow"] = deepcopy(update_request["workflow"])
    update_request["workflow"]["steps"][0]["completion"] = (
        "Product owner confirms the narrowed scope."
    )
    expected_digest = design_digest(
        update_request["profile"],
        update_request["workflow"],
        update_request["scenarios"],
        update_request["catalog"],
    )

    update_response = design_client.put(
        f"/api/designs/{created_design['id']}",
        headers=build_headers(),
        json=update_request,
    )

    assert update_response.status_code == 200
    updated_design = update_response.json()["design"]
    assert updated_design["id"] == created_design["id"]
    assert updated_design["revision"] == 2
    assert updated_design["status"] == "draft"
    assert updated_design["digest"] == expected_digest
    assert updated_design["digest"] != created_design["digest"]
    assert updated_design["validation_findings"] is None


def test_developer_without_author_role_receives_forbidden(design_client):
    response = design_client.post(
        "/api/designs",
        headers=build_headers(roles="developer"),
        json=build_design_request(),
    )

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "required role missing",
        "code": "forbidden",
    }


def test_other_organization_receives_not_found_for_design(design_client):
    create_response = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_request(),
    )
    design_id = create_response.json()["design"]["id"]

    response = design_client.get(
        f"/api/designs/{design_id}",
        headers=build_headers(organization_id="org-umbrella"),
    )

    assert response.status_code == 404
    assert response.json() == {
        "ok": False,
        "error": "design not found",
        "code": "error",
    }


def test_validate_endpoint_calls_real_validators_with_settings_catalog_root(
    design_client, monkeypatch
):
    service = import_module("web.api.designs.service")
    recorded_calls: list[tuple[str, object]] = []
    real_validate = service.validate
    real_validate_scenarios = service.validate_scenarios

    def spy_validate(profile, workflow, catalog, catalog_root):
        recorded_calls.append(("validate", Path(catalog_root)))
        return real_validate(profile, workflow, catalog, catalog_root)

    def spy_validate_scenarios(scenarios, workflow):
        recorded_calls.append(("validate_scenarios", workflow["id"]))
        return real_validate_scenarios(scenarios, workflow)

    monkeypatch.setattr(service, "validate", spy_validate)
    monkeypatch.setattr(service, "validate_scenarios", spy_validate_scenarios)

    create_response = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_request(),
    )
    design_id = create_response.json()["design"]["id"]

    response = design_client.post(
        f"/api/designs/{design_id}/validate",
        headers=build_headers(),
    )

    assert response.status_code == 200
    assert recorded_calls == [
        ("validate", FIXTURE_ROOT / "catalog"),
        ("validate_scenarios", "issue-to-reviewed-pr"),
    ]


def test_validate_endpoint_rejects_mutated_nested_catalog_path_without_reading_it(
    design_client, monkeypatch
):
    service = import_module("web.api.designs.service")

    def fail_validate(*args, **kwargs):
        raise AssertionError("core validators must not run for mismatched catalog")

    monkeypatch.setattr(service, "validate", fail_validate)
    monkeypatch.setattr(service, "validate_scenarios", fail_validate)

    request = build_design_request()
    request["catalog"] = deepcopy(request["catalog"])
    request["catalog"]["skills"][0]["compatibility"]["evidence"] = (
        "evidence/should-not-be-read.json"
    )
    create_response = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=request,
    )
    design_id = create_response.json()["design"]["id"]

    response = design_client.post(
        f"/api/designs/{design_id}/validate",
        headers=build_headers(),
    )

    assert response.status_code == 422
    assert response.json()["finding"] == {
        "field": "contract",
        "code": "invalid-design",
        "message": "validation: catalog: request snapshot does not match server catalog",
    }
    assert response.json()["design"]["validation_findings"] == [
        response.json()["finding"]
    ]


def test_invalid_workflow_validation_returns_normalized_finding_and_keeps_draft(
    design_client,
):
    invalid_request = build_design_request()
    invalid_request["workflow"] = deepcopy(invalid_request["workflow"])
    invalid_request["workflow"]["steps"][0]["completion"] = ""
    expected_digest = design_digest(
        invalid_request["profile"],
        invalid_request["workflow"],
        invalid_request["scenarios"],
        invalid_request["catalog"],
    )
    create_response = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=invalid_request,
    )
    design_id = create_response.json()["design"]["id"]

    response = design_client.post(
        f"/api/designs/{design_id}/validate",
        headers=build_headers(),
    )

    assert response.status_code == 422
    assert response.json()["ok"] is False
    assert response.json()["error"] == "design validation failed"
    assert response.json()["code"] == "invalid_design"
    assert response.json()["finding"] == {
        "field": "contract",
        "code": "invalid-design",
        "message": "workflow.steps.completion: expected nonempty string",
    }
    assert response.json()["design"]["validation_findings"] == [
        response.json()["finding"]
    ]
    assert "Traceback" not in response.text

    design_response = design_client.get(
        f"/api/designs/{design_id}",
        headers=build_headers(),
    )

    assert design_response.status_code == 200
    assert design_response.json()["design"]["status"] == "draft"
    assert design_response.json()["design"]["digest"] == expected_digest
    assert design_response.json()["design"]["validation_findings"] == [
        response.json()["finding"]
    ]


def test_valid_workflow_validation_sets_validated_status_and_current_digest(
    design_client,
):
    request = build_design_request()
    expected_digest = design_digest(
        request["profile"],
        request["workflow"],
        request["scenarios"],
        request["catalog"],
    )
    create_response = design_client.post(
        "/api/designs",
        headers=build_headers(),
        json=request,
    )
    design_id = create_response.json()["design"]["id"]

    response = design_client.post(
        f"/api/designs/{design_id}/validate",
        headers=build_headers(),
    )

    assert response.status_code == 200
    assert response.json()["design"]["status"] == "validated"
    assert response.json()["design"]["digest"] == expected_digest
    assert response.json()["design"]["validation_findings"] == []
