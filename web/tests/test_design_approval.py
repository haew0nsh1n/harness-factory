from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_factory import load_json
from web.api.audit.models import AuditEvent
from web.api.config import Settings
from web.api.db import Base
from web.api.designs.models import Approval, HarnessDesign
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
    *,
    organization_id: str = "org-acme",
    subject_id: str = "user-1",
    roles: str = "author",
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
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


def create_design(
    client: TestClient, request: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = client.post(
        "/api/designs",
        headers=build_headers(),
        json=request or build_design_request(),
    )

    assert response.status_code == 201
    return response.json()["design"]


def validate_design(client: TestClient, design_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/designs/{design_id}/validate",
        headers=build_headers(),
    )

    assert response.status_code == 200
    return response.json()["design"]


def review_design(
    client: TestClient,
    design_id: str,
    expected_digest: str,
    decision: str,
    *,
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/api/designs/{design_id}/reviews",
        headers=headers
        or build_headers(subject_id="reviewer-1", roles="reviewer"),
        json={
            "expected_digest": expected_digest,
            "decision": decision,
        },
    )


def test_review_requires_validated_design(design_client):
    design = create_design(design_client)

    response = review_design(
        design_client,
        design["id"],
        design["digest"],
        "approved",
    )

    assert response.status_code == 422
    assert response.json() == {
        "ok": False,
        "error": "design lifecycle does not allow review",
        "code": "invalid_lifecycle",
    }


def test_author_without_reviewer_role_receives_forbidden(design_client):
    created_design = create_design(design_client)
    validated_design = validate_design(design_client, created_design["id"])

    response = review_design(
        design_client,
        created_design["id"],
        validated_design["digest"],
        "approved",
        headers=build_headers(subject_id="user-1", roles="author"),
    )

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "required role missing",
        "code": "forbidden",
    }


def test_stale_review_digest_returns_conflict_without_persisting_changes(design_client):
    created_design = create_design(design_client)
    validated_design = validate_design(design_client, created_design["id"])

    response = review_design(
        design_client,
        created_design["id"],
        "f" * 64,
        "approved",
    )

    assert response.status_code == 409
    assert response.json() == {
        "ok": False,
        "error": "design digest is stale",
        "code": "stale_digest",
    }

    with Session(design_client.app.state.engine) as session:
        approvals = session.scalars(select(Approval)).all()
        audit_events = session.scalars(select(AuditEvent)).all()
        design = session.get(HarnessDesign, created_design["id"])

    assert len(approvals) == 0
    assert len(audit_events) == 0
    assert design is not None
    assert design.status == validated_design["status"] == "validated"


def test_approval_persists_exact_digest_actor_and_audit_event(design_client):
    created_design = create_design(design_client)
    validated_design = validate_design(design_client, created_design["id"])

    response = review_design(
        design_client,
        created_design["id"],
        validated_design["digest"],
        "approved",
    )

    assert response.status_code == 200
    approved_design = response.json()["design"]
    assert approved_design["status"] == "approved"

    with Session(design_client.app.state.engine) as session:
        approvals = session.scalars(select(Approval)).all()
        audit_events = session.scalars(select(AuditEvent)).all()

    assert len(approvals) == 1
    assert approvals[0].subject_digest == validated_design["digest"]
    assert approvals[0].actor_subject_id == "reviewer-1"
    assert approvals[0].decision == "approved"
    assert len(audit_events) == 1
    assert audit_events[0].actor_subject_id == "reviewer-1"
    assert audit_events[0].resource_id == created_design["id"]


def test_updating_approved_design_returns_to_draft_and_preserves_approval_history(
    design_client,
):
    created_design = create_design(design_client)
    validated_design = validate_design(design_client, created_design["id"])
    approval_response = review_design(
        design_client,
        created_design["id"],
        validated_design["digest"],
        "approved",
    )
    assert approval_response.status_code == 200

    update_request = build_design_request()
    update_request["workflow"] = deepcopy(update_request["workflow"])
    update_request["workflow"]["steps"][0]["completion"] = (
        "Reviewer asks for a smaller rollout."
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
    assert update_response.json()["design"]["status"] == "draft"
    assert update_response.json()["design"]["digest"] == expected_digest

    with Session(design_client.app.state.engine) as session:
        approvals = session.scalars(select(Approval)).all()

    assert len(approvals) == 1
    assert approvals[0].subject_digest == validated_design["digest"]


def test_rejection_requires_change_and_revalidation_before_later_approval(design_client):
    created_design = create_design(design_client)
    validated_design = validate_design(design_client, created_design["id"])

    rejection_response = review_design(
        design_client,
        created_design["id"],
        validated_design["digest"],
        "rejected",
    )

    assert rejection_response.status_code == 200
    assert rejection_response.json()["design"]["status"] == "draft"

    blocked_response = review_design(
        design_client,
        created_design["id"],
        validated_design["digest"],
        "approved",
    )

    assert blocked_response.status_code == 422
    assert blocked_response.json() == {
        "ok": False,
        "error": "design lifecycle does not allow review",
        "code": "invalid_lifecycle",
    }

    updated_request = build_design_request()
    updated_request["workflow"] = deepcopy(updated_request["workflow"])
    updated_request["workflow"]["steps"][0]["completion"] = (
        "Author addresses the rejection feedback."
    )
    update_response = design_client.put(
        f"/api/designs/{created_design['id']}",
        headers=build_headers(),
        json=updated_request,
    )
    assert update_response.status_code == 200

    revalidated_design = validate_design(design_client, created_design["id"])
    approval_response = review_design(
        design_client,
        created_design["id"],
        revalidated_design["digest"],
        "approved",
    )

    assert approval_response.status_code == 200
    assert approval_response.json()["design"]["status"] == "approved"


def test_audit_append_rejects_sensitive_summary_keys(design_client):
    from web.api.audit.service import AuditService

    engine = design_client.app.state.engine

    with Session(engine) as session:
        service = AuditService(session)
        with pytest.raises(ValueError, match="summary contains sensitive key"):
            service.append(
                organization_id="org-acme",
                actor_id="reviewer-1",
                action="design.reviewed",
                resource_type="harness-design",
                resource_id="design-1",
                summary={
                    "decision": "approved",
                    "source_code": "hidden",
                },
            )
        audit_events = session.scalars(select(AuditEvent)).all()

    assert audit_events == []
