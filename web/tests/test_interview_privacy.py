from uuid import uuid4

from sqlalchemy import func, select

from web.api.audit.models import AuditEvent
from web.api.interviews.models import InterviewSession, InterviewTurn
from web.api.interviews.service import delete_expired_interviews
from web.tests.test_interview_api import (
    FakeInterviewModel,
    headers,
    start_interview,
    start_payload,
)


def test_recognizable_secret_is_rejected_before_storage_or_model_call(
    interview_client_factory,
):
    model = FakeInterviewModel()
    client, app = interview_client_factory(model)
    with client:
        response = client.post(
            "/api/interviews",
            headers=headers(),
            json={
                **start_payload(),
                "name": "password=CorrectHorseBatteryStaple!",
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "secret_detected"
        assert model.calls == []
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(InterviewSession)) == 0


def test_secret_answer_is_not_stored_or_sent(interview_client_factory):
    model = FakeInterviewModel()
    client, app = interview_client_factory(model)
    with client:
        session = start_interview(client)
        calls = len(model.calls)
        response = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "answer": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
            },
        )

        assert response.status_code == 422
        assert response.json()["code"] == "secret_detected"
        assert len(model.calls) == calls
    with app.state.session_factory() as db:
        turns = db.scalars(
            select(InterviewTurn).where(
                InterviewTurn.session_id == session["id"]
            )
        ).all()
        assert [turn.role for turn in turns] == ["assistant"]


def test_delete_audit_contains_identifiers_not_conversation_text(
    interview_client_factory,
):
    model = FakeInterviewModel()
    client, app = interview_client_factory(model)
    with client:
        session = start_interview(client)
        secret_business_text = "A uniquely identifying private business sentence"
        client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "answer": secret_business_text,
            },
        )

        response = client.delete(
            f"/api/interviews/{session['id']}", headers=headers()
        )
        assert response.status_code == 200
    with app.state.session_factory() as db:
        event = db.scalars(
            select(AuditEvent).where(AuditEvent.resource_id == session["id"])
        ).one()
        assert event.action == "interview.deleted"
        assert secret_business_text not in str(event.summary_json)
        assert set(event.summary_json) == {"turn_count", "proposal_count"}


def test_retention_cleanup_deletes_expired_interview_children(
    interview_client_factory,
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from web.api.interviews.models import InterviewOperation

    model = FakeInterviewModel()
    client, app = interview_client_factory(model)
    with client:
        session = start_interview(client)
        with app.state.session_factory.begin() as db:
            db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == session["id"])
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )

        assert delete_expired_interviews(app.state.session_factory) == 1

    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(InterviewSession)) == 0
        assert db.scalar(select(func.count()).select_from(InterviewTurn)) == 0
        assert db.scalar(select(func.count()).select_from(InterviewOperation)) == 0
