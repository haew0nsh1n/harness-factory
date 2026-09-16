from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from web.api.config import Settings
from web.api.db import Base
from web.api.interviews.model import InterviewContext
from web.api.interviews.schemas import InterviewReply, SuggestedEvidence
from web.api.main import create_app
from web.api.organizations.models import Organization


CONSENT_VERSION = "2026-09-15"


class FakeInterviewModel:
    def __init__(self) -> None:
        self.calls: list[InterviewContext] = []
        self.closed = False

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self.calls.append(context)
        if not context.turns:
            return InterviewReply(
                question="Where does delivery work slow down most?",
                stage="discovery",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
            )
        source_id = context.turns[-1].id
        return InterviewReply(
            question="How do you know the handoff is complete?",
            stage="planning",
            evidence=[
                SuggestedEvidence(
                    id="model-id-is-not-authoritative",
                    statement="Reviews wait for a manual handoff.",
                    kind="fact",
                    source_turn_ids=[source_id],
                )
            ],
            proposed_scope="review-handoff",
            ready_for_review=True,
        )

    async def propose_design(self, context, catalog):
        raise AssertionError("proposal generation belongs to task 3")

    async def close(self) -> None:
        self.closed = True


def headers(
    organization_id: str = "org-acme",
    subject_id: str = "author-1",
    roles: str = "author",
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
        "X-HF-Roles": roles,
    }


@pytest.fixture
def interview_api():
    model = FakeInterviewModel()
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url="sqlite+pysqlite:///:memory:",
        ),
        interview_model_factory=lambda settings: model,
    )
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory.begin() as session:
        session.add_all(
            [
                Organization(
                    id="org-acme",
                    entra_tenant_id="tenant-acme",
                    name="Acme",
                ),
                Organization(
                    id="org-other",
                    entra_tenant_id="tenant-other",
                    name="Other",
                ),
            ]
        )
    with TestClient(app) as client:
        yield client, model, app


def start_payload(request_id: str | None = None) -> dict[str, object]:
    return {
        "name": "Acme delivery interview",
        "customer_id": "acme",
        "consent_version": CONSENT_VERSION,
        "consent_accepted": True,
        "request_id": request_id or str(uuid4()),
    }


def start_interview(client: TestClient, request_id: str | None = None) -> dict:
    response = client.post(
        "/api/interviews",
        headers=headers(),
        json=start_payload(request_id),
    )
    assert response.status_code == 201, response.text
    return response.json()["session"]


def test_start_requires_explicit_versioned_consent_before_model_call(interview_api):
    client, model, _ = interview_api
    response = client.post(
        "/api/interviews",
        headers=headers(),
        json={**start_payload(), "consent_accepted": False},
    )

    assert response.status_code == 422
    assert model.calls == []


def test_start_is_idempotent_and_returns_complete_session_dto(interview_api):
    client, model, _ = interview_api
    request_id = str(uuid4())

    first = client.post(
        "/api/interviews", headers=headers(), json=start_payload(request_id)
    )
    second = client.post(
        "/api/interviews", headers=headers(), json=start_payload(request_id)
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()
    session = first.json()["session"]
    assert session["revision"] == 1
    assert session["status"] == "active"
    assert session["consent_version"] == CONSENT_VERSION
    assert session["stage"] == "discovery"
    assert session["scope"] is None
    assert session["last_operation"]["status"] == "succeeded"
    assert session["last_error_code"] is None
    assert session["proposals"] == []
    assert [turn["role"] for turn in session["turns"]] == ["assistant"]
    assert len(model.calls) == 1


def test_answer_is_idempotent_and_stale_revision_conflicts(interview_api):
    client, model, _ = interview_api
    session = start_interview(client)
    request_id = str(uuid4())
    payload = {
        "expected_revision": session["revision"],
        "request_id": request_id,
        "answer": "The review queue waits for a manual handoff.",
    }

    answered = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json=payload,
    )
    repeated = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json=payload,
    )
    stale = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json={**payload, "request_id": str(uuid4())},
    )

    assert answered.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json() == answered.json()
    assert stale.status_code == 409
    result = answered.json()["session"]
    assert result["revision"] == 2
    assert [turn["role"] for turn in result["turns"]] == [
        "assistant",
        "user",
        "assistant",
    ]
    assert result["proposed_evidence"][0]["statement"] == (
        "Reviews wait for a manual handoff."
    )
    assert result["proposed_evidence"][0]["id"] != "model-id-is-not-authoritative"
    assert len(model.calls) == 2


def test_confirmations_require_explicit_decisions_and_are_idempotent(interview_api):
    client, _, _ = interview_api
    session = start_interview(client)
    answered = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json={
            "expected_revision": session["revision"],
            "request_id": str(uuid4()),
            "answer": "The review queue waits for a manual handoff.",
        },
    ).json()["session"]
    evidence_id = answered["proposed_evidence"][0]["id"]
    request_id = str(uuid4())
    payload = {
        "expected_revision": answered["revision"],
        "request_id": request_id,
        "decisions": [{"evidence_id": evidence_id, "decision": "confirm"}],
    }

    confirmed = client.post(
        f"/api/interviews/{session['id']}/confirmations",
        headers=headers(),
        json=payload,
    )
    repeated = client.post(
        f"/api/interviews/{session['id']}/confirmations",
        headers=headers(),
        json=payload,
    )

    assert confirmed.status_code == 200
    assert repeated.json() == confirmed.json()
    result = confirmed.json()["session"]
    assert result["revision"] == 3
    assert result["confirmed_evidence"][0]["id"] == evidence_id
    assert result["proposed_evidence"] == []


def test_list_get_delete_are_tenant_scoped_and_role_checked(interview_api):
    client, _, _ = interview_api
    session = start_interview(client)

    assert client.get("/api/interviews", headers=headers()).json()["items"][0][
        "id"
    ] == session["id"]
    assert (
        client.get(
            f"/api/interviews/{session['id']}",
            headers=headers("org-other", "author-2"),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/interviews/{session['id']}",
            headers=headers(roles="reviewer"),
        ).status_code
        == 403
    )
    deleted = client.delete(
        f"/api/interviews/{session['id']}",
        headers=headers(roles="org-admin"),
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "deleted": True}
    assert (
        client.get(f"/api/interviews/{session['id']}", headers=headers()).status_code
        == 404
    )


def test_expired_session_is_inaccessible_before_cleanup(interview_api):
    client, _, app = interview_api
    session = start_interview(client)
    with app.state.session_factory.begin() as db:
        from web.api.interviews.models import InterviewSession

        stored = db.get(InterviewSession, session["id"])
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert (
        client.get(f"/api/interviews/{session['id']}", headers=headers()).status_code
        == 404
    )
    assert client.get("/api/interviews", headers=headers()).json()["items"] == []


def test_answer_length_and_extra_fields_are_rejected(interview_api):
    client, model, _ = interview_api
    session = start_interview(client)
    calls = len(model.calls)
    response = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json={
            "expected_revision": session["revision"],
            "request_id": str(uuid4()),
            "answer": "x" * 8001,
            "unexpected": True,
        },
    )

    assert response.status_code == 422
    assert len(model.calls) == calls
