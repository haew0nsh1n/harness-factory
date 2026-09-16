import hashlib
import json
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


def test_interview_reply_scope_uses_canonical_workflow_id_grammar():
    from pydantic import ValidationError

    valid = InterviewReply(
        question="Is this the right scope?",
        stage="summary",
        evidence=[],
        proposed_scope="review-bottleneck",
        ready_for_review=True,
    )
    assert valid.proposed_scope == "review-bottleneck"

    with pytest.raises(ValidationError):
        InterviewReply(
            question="Is this the right scope?",
            stage="summary",
            evidence=[],
            proposed_scope="review_bottleneck",
            ready_for_review=True,
        )


class MalformedFirstScopeModel(FakeInterviewModel):
    async def next_question(self, context: InterviewContext):
        self.calls.append(context)
        return {
            "question": "Is this the right scope?",
            "stage": "discovery",
            "evidence": [],
            "proposed_scope": "review_bottleneck",
            "ready_for_review": False,
            "options": [],
            "allow_custom_answer": True,
        }


def test_malformed_scope_in_first_reply_is_rejected_without_being_persisted(
    interview_client_factory,
):
    from sqlalchemy import func, select

    from web.api.interviews.models import InterviewSession, InterviewTurn

    model = MalformedFirstScopeModel()
    client, app = interview_client_factory(model)
    request_id = str(uuid4())
    with client:
        rejected = client.post(
            "/api/interviews",
            headers=headers(),
            json={
                "name": "Malformed scope",
                "customer_id": "acme",
                "consent_version": CONSENT_VERSION,
                "consent_accepted": True,
                "request_id": request_id,
            },
        )

        assert rejected.status_code == 503
        assert rejected.json()["code"] == "llm_invalid_result"
        with app.state.session_factory() as db:
            stored = db.scalar(
                select(InterviewSession).where(
                    InterviewSession.creation_request_id == request_id
                )
            )
            assert stored is not None
            assert stored.selected_scope is None
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(InterviewTurn)
                    .where(InterviewTurn.session_id == stored.id)
                )
                == 0
            )


def test_existing_malformed_scope_can_be_replaced_by_next_valid_reply(interview_api):
    from sqlalchemy import update

    from web.api.interviews.models import InterviewSession

    client, model, app = interview_api
    session = start_interview(client)
    with app.state.session_factory.begin() as db:
        db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session["id"])
            .values(selected_scope="review_bottleneck")
        )

    recovered = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json={
            "expected_revision": session["revision"],
            "request_id": str(uuid4()),
            "answer": "Use a canonical scope.",
        },
    )

    assert recovered.status_code == 200, recovered.text
    assert model.calls[-1].selected_scope == "review_bottleneck"
    assert recovered.json()["session"]["scope"] == "review-handoff"


class ChoiceInterviewModel(FakeInterviewModel):
    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self.calls.append(context)
        if not context.turns:
            return InterviewReply(
                question="가장 큰 검토 병목은 무엇인가요?",
                stage=context.selected_stages[0],
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
                options=[
                    {"id": "slow-approval", "label": "승인 대기"},
                    {"id": "unclear-criteria", "label": "불명확한 검토 기준"},
                ],
                allow_custom_answer=True,
            )
        return InterviewReply(
            question="이 범위로 검토를 진행할까요?",
            stage="summary",
            evidence=[],
            proposed_scope="review-handoff",
            ready_for_review=True,
            options=[{"id": "yes", "label": "예"}],
            allow_custom_answer=True,
        )


def test_selected_stages_are_canonical_resumable_and_legacy_defaults_to_all(
    interview_client_factory,
):
    model = ChoiceInterviewModel()
    client, app = interview_client_factory(model)
    with client:
        selected = client.post(
            "/api/interviews",
            headers=headers(),
            json={
                **start_payload(),
                "selected_stages": ["review", "planning"],
            },
        )
        legacy = start_interview(client)

        assert selected.status_code == 201, selected.text
        session = selected.json()["session"]
        assert session["selected_stages"] == ["planning", "review"]
        assert session["stage"] == "planning"
        assert model.calls[0].selected_stages == ("planning", "review")
        resumed = client.get(
            f"/api/interviews/{session['id']}", headers=headers()
        ).json()["session"]
        assert resumed["selected_stages"] == ["planning", "review"]
        assert legacy["selected_stages"] == [
            "discovery",
            "planning",
            "implementation",
            "testing",
            "review",
            "release",
            "operations",
        ]

        from web.api.interviews.models import InterviewSession

        with app.state.session_factory.begin() as db:
            stored = db.get(InterviewSession, legacy["id"])
            assert stored is not None
            assert stored.selected_stages_json is None
            expected_legacy_digest = hashlib.sha256(
                json.dumps(
                    {
                        "kind": "start",
                        "name": "Acme delivery interview",
                        "customer_id": "acme",
                        "consent_version": CONSENT_VERSION,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            assert stored.creation_input_digest == expected_legacy_digest


@pytest.mark.parametrize(
    "selected_stages",
    [[], ["review", "review"], ["review", "summary"], ["unknown"]],
)
def test_selected_stages_reject_invalid_values(interview_api, selected_stages):
    client, model, _ = interview_api
    response = client.post(
        "/api/interviews",
        headers=headers(),
        json={**start_payload(), "selected_stages": selected_stages},
    )
    assert response.status_code == 422
    assert model.calls == []


def test_choice_answer_is_resolved_server_side_and_resumes_with_provenance(
    interview_client_factory,
):
    model = ChoiceInterviewModel()
    client, _ = interview_client_factory(model)
    with client:
        session = client.post(
            "/api/interviews",
            headers=headers(),
            json={**start_payload(), "selected_stages": ["review"]},
        ).json()["session"]
        question = session["turns"][0]
        assert question["options"] == [
            {"id": "slow-approval", "label": "승인 대기"},
            {"id": "unclear-criteria", "label": "불명확한 검토 기준"},
        ]
        response = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "choice_answer": {
                    "question_turn_id": question["id"],
                    "option_id": "unclear-criteria",
                },
            },
        )
        assert response.status_code == 200, response.text
        answered = response.json()["session"]
        user_turn = answered["turns"][1]
        assert user_turn["text"] == "불명확한 검토 기준"
        assert user_turn["choice_question_turn_id"] == question["id"]
        assert user_turn["choice_option_id"] == "unclear-criteria"
        assert model.calls[-1].turns[-1].text == "불명확한 검토 기준"
        assert client.get(
            f"/api/interviews/{session['id']}", headers=headers()
        ).json()["session"]["turns"] == answered["turns"]


def test_choice_rejects_forged_outdated_and_cross_tenant_questions(
    interview_client_factory,
):
    model = ChoiceInterviewModel()
    client, _ = interview_client_factory(model)
    with client:
        session = client.post(
            "/api/interviews",
            headers=headers(),
            json={**start_payload(), "selected_stages": ["review"]},
        ).json()["session"]
        question = session["turns"][0]
        forged = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "choice_answer": {
                    "question_turn_id": question["id"],
                    "option_id": "forged",
                },
            },
        )
        assert forged.status_code == 409
        assert forged.json()["code"] == "choice_option_not_found"

        answered = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "answer": "직접 입력",
            },
        ).json()["session"]
        outdated = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": answered["revision"],
                "request_id": str(uuid4()),
                "choice_answer": {
                    "question_turn_id": question["id"],
                    "option_id": "slow-approval",
                },
            },
        )
        assert outdated.status_code == 409
        assert outdated.json()["code"] == "choice_question_not_current"
        cross_tenant = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers("org-other", "author-2"),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "choice_answer": {
                    "question_turn_id": question["id"],
                    "option_id": "slow-approval",
                },
            },
        )
        assert cross_tenant.status_code == 404


@pytest.mark.parametrize(
    "answer_fields",
    [
        {},
        {"answer": "text", "choice_answer": {
            "question_turn_id": str(uuid4()), "option_id": "one"
        }},
        {"answer": "   "},
    ],
)
def test_answer_requires_exactly_one_nonblank_input(interview_api, answer_fields):
    client, model, _ = interview_api
    session = start_interview(client)
    calls = len(model.calls)
    response = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json={
            "expected_revision": session["revision"],
            "request_id": str(uuid4()),
            **answer_fields,
        },
    )
    assert response.status_code == 422
    assert len(model.calls) == calls


class OutOfSelectionModel(ChoiceInterviewModel):
    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self.calls.append(context)
        return InterviewReply(
            question="선택하지 않은 단계를 질문할까요?",
            stage="discovery",
            evidence=[],
            proposed_scope=None,
            ready_for_review=False,
        )


def test_model_question_outside_selected_stages_is_rejected(
    interview_client_factory,
):
    model = OutOfSelectionModel()
    client, _ = interview_client_factory(model)
    with client:
        response = client.post(
            "/api/interviews",
            headers=headers(),
            json={**start_payload(), "selected_stages": ["review"]},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "llm_invalid_result"
