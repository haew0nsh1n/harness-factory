import asyncio
import os
import time
from threading import Barrier, Event, Thread, current_thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from web.api.config import Settings
from web.api.db import Base
from web.api.identity.models import Actor
from web.api.interviews import routes as interview_routes
from web.api.interviews.errors import InterviewModelError
from web.api.interviews.model import InterviewContext
from web.api.interviews.schemas import (
    AnswerRequest,
    InterviewReply,
    StartInterviewRequest,
    SuggestedEvidence,
)
from web.api.interviews.service import InterviewConflict, InterviewService
from web.api.main import create_app
from web.api.organizations.models import Organization
from web.tests.test_interview_api import headers, start_interview


class BlockingModel:
    def __init__(self) -> None:
        self.calls = 0
        self.entered = Event()
        self.release = Event()
        self.fail = False

    async def next_question(self, context):
        self.calls += 1
        if not context.turns:
            return InterviewReply(
                question="Where is the bottleneck?",
                stage="discovery",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
            )
        self.entered.set()
        await asyncio.to_thread(self.release.wait, 5)
        if self.fail:
            raise InterviewModelError("llm_timeout", "provider details must stay private")
        return InterviewReply(
            question="What should improve?",
            stage="planning",
            evidence=[],
            proposed_scope=None,
            ready_for_review=False,
        )

    async def propose_design(self, context, catalog):
        raise AssertionError

    async def close(self):
        return None


class RetryRaceModel(BlockingModel):
    async def next_question(self, context):
        self.calls += 1
        if not context.turns:
            return InterviewReply(
                question="Where is the bottleneck?",
                stage="discovery",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
            )
        if self.calls == 2:
            self.entered.set()
            await asyncio.to_thread(self.release.wait, 5)
        return InterviewReply(
            question="What should improve?",
            stage="planning",
            evidence=[],
            proposed_scope=None,
            ready_for_review=False,
        )


class CasRaceModel:
    def __init__(self) -> None:
        self.calls: list[InterviewContext] = []
        self.fail = False

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self.calls.append(context)
        if self.fail:
            raise InterviewModelError("llm_timeout", "provider details stay private")
        if not context.turns:
            return InterviewReply(
                question="Where is the bottleneck?",
                stage="discovery",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
            )
        return InterviewReply(
            question="What should improve?",
            stage="planning",
            evidence=[
                SuggestedEvidence(
                    id="model-id",
                    statement="The handoff is slow.",
                    kind="fact",
                    source_turn_ids=[context.turns[-1].id],
                )
            ],
            proposed_scope=None,
            ready_for_review=False,
        )

    async def propose_design(self, context, catalog):
        raise AssertionError

    async def close(self):
        return None


class ChoiceRetryModel:
    def __init__(self) -> None:
        self.calls: list[InterviewContext] = []
        self.fail = True

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        self.calls.append(context)
        if not context.turns:
            return InterviewReply(
                question="병목을 선택하세요.",
                stage="review",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
                options=[{"id": "approval-wait", "label": "승인 대기"}],
            )
        if self.fail:
            raise InterviewModelError("llm_timeout", "private")
        return InterviewReply(
            question="이 범위로 진행할까요?",
            stage="summary",
            evidence=[],
            proposed_scope="review-handoff",
            ready_for_review=True,
        )

    async def propose_design(self, context, catalog):
        raise AssertionError

    async def close(self):
        return None


class BarrierInterviewService(InterviewService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._claim_barrier: Barrier | None = None
        self._delayed_thread_name: str | None = None
        self.claim_connection_ids: set[int] = set()

    def arm_claim_barrier(self, *, delayed_thread_name: str | None = None) -> None:
        self._claim_barrier = Barrier(2)
        self._delayed_thread_name = delayed_thread_name
        self.claim_connection_ids.clear()

    def _claim_session_operation(self, db, session, **kwargs) -> None:
        barrier = self._claim_barrier
        if barrier is not None:
            connection = db.connection().connection.driver_connection
            self.claim_connection_ids.add(id(connection))
            barrier.wait(5)
            if current_thread().name == self._delayed_thread_name:
                time.sleep(0.05)
        return super()._claim_session_operation(db, session, **kwargs)


@pytest.fixture
def cas_race_client_factory(tmp_path, monkeypatch):
    resources = []

    def build(model: CasRaceModel):
        database_path = tmp_path / f"interview-race-{len(resources)}.db"
        database_url = os.environ.get(
            "HF_POSTGRES_CAS_TEST_URL",
            f"sqlite+pysqlite:///{database_path}",
        )
        app = create_app(
            Settings(
                auth_mode="development",
                allow_insecure_development_auth=True,
                database_url=database_url,
            ),
            interview_model_factory=lambda settings: model,
        )
        if database_url.startswith("postgresql"):
            Base.metadata.drop_all(app.state.engine)
        Base.metadata.create_all(app.state.engine)
        with app.state.session_factory.begin() as db:
            db.add(
                Organization(
                    id="org-acme",
                    entra_tenant_id=f"tenant-acme-{len(resources)}",
                    name="Acme",
                )
            )
        service = BarrierInterviewService(
            app.state.session_factory,
            app.state.settings,
            model,
        )
        monkeypatch.setattr(interview_routes, "_service", lambda request: service)
        client = TestClient(app)
        resources.append((client, app))
        return client, app, service

    yield build

    for client, app in resources:
        client.close()
        app.state.engine.dispose()


def _post_answer(
    client: TestClient,
    session: dict,
    request_id: str,
    result: dict,
) -> None:
    response = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=headers(),
        json={
            "expected_revision": session["revision"],
            "request_id": request_id,
            "answer": "The handoff is slow.",
        },
    )
    result.update(status=response.status_code, body=response.json())


def _post_json(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    result: dict,
) -> None:
    response = client.post(path, headers=headers(), json=payload)
    result.update(status=response.status_code, body=response.json())


def _call_answer(
    service: InterviewService,
    actor: Actor,
    session_id: str,
    payload: dict[str, object],
    result: dict,
) -> None:
    try:
        response = asyncio.run(
            service.answer(actor, session_id, AnswerRequest.model_validate(payload))
        )
    except InterviewConflict as exc:
        result.update(status=409, code=exc.code)
    else:
        result.update(status=200, session=response)


def _call_start(
    service: InterviewService,
    actor: Actor,
    payload: dict[str, object],
    result: dict,
) -> None:
    try:
        response, created = asyncio.run(
            service.start(actor, StartInterviewRequest.model_validate(payload))
        )
    except InterviewConflict as exc:
        result.update(status=409, code=exc.code)
    else:
        result.update(status=201 if created else 200, session=response)


def test_concurrent_answer_is_busy_and_only_one_model_call(interview_client_factory):
    model = BlockingModel()
    client, _ = interview_client_factory(model)
    with client:
        session = start_interview(client)
        result: dict = {}
        thread = Thread(
            target=_post_answer,
            args=(client, session, str(uuid4()), result),
        )
        thread.start()
        assert model.entered.wait(2)

        running = client.get(
            f"/api/interviews/{session['id']}", headers=headers()
        )
        assert running.status_code == 200
        assert running.json()["session"]["last_operation"]["lease_expired"] is False

        competing = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "answer": "A second answer must not win.",
            },
        )
        assert competing.status_code == 409
        assert competing.json()["code"] == "interview_busy"

        model.release.set()
        thread.join(5)
        assert result["status"] == 200
        assert model.calls == 2


def test_delete_during_inference_prevents_late_completion(interview_client_factory):
    model = BlockingModel()
    client, _ = interview_client_factory(model)
    with client:
        session = start_interview(client)
        result: dict = {}
        thread = Thread(
            target=_post_answer,
            args=(client, session, str(uuid4()), result),
        )
        thread.start()
        assert model.entered.wait(2)

        deleted = client.delete(
            f"/api/interviews/{session['id']}", headers=headers()
        )
        assert deleted.status_code == 200
        model.release.set()
        thread.join(5)

        assert result["status"] == 409
        assert result["body"]["code"] == "operation_superseded"
        assert (
            client.get(
                f"/api/interviews/{session['id']}", headers=headers()
            ).status_code
            == 404
        )


def test_delete_during_failed_inference_supersedes_provider_error(
    interview_client_factory,
):
    model = BlockingModel()
    model.fail = True
    client, _ = interview_client_factory(model)
    with client:
        session = start_interview(client)
        result: dict = {}
        thread = Thread(
            target=_post_answer,
            args=(client, session, str(uuid4()), result),
        )
        thread.start()
        assert model.entered.wait(2)

        assert (
            client.delete(
                f"/api/interviews/{session['id']}", headers=headers()
            ).status_code
            == 200
        )
        model.release.set()
        thread.join(5)

        assert result["status"] == 409
        assert result["body"]["code"] == "operation_superseded"


def test_failed_operation_can_be_explicitly_retried_without_duplicate_user_turn(
    interview_client_factory,
):
    model = BlockingModel()
    model.fail = True
    model.release.set()
    client, app = interview_client_factory(model)
    with client:
        session = start_interview(client)
        request_id = str(uuid4())
        payload = {
            "expected_revision": session["revision"],
            "request_id": request_id,
            "answer": "The handoff is slow.",
        }

        failed = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json=payload,
        )
        assert failed.status_code == 503
        assert failed.json()["code"] == "llm_timeout"

        model.fail = False
        retried = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json=payload,
        )
        assert retried.status_code == 200
        assert [
            turn["role"] for turn in retried.json()["session"]["turns"]
        ] == ["assistant", "user", "assistant"]
        assert model.calls == 3

        from sqlalchemy import func, select
        from web.api.interviews.models import InterviewTurn

        with app.state.session_factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(InterviewTurn)
                    .where(
                        InterviewTurn.session_id == session["id"],
                        InterviewTurn.role == "user",
                    )
                )
                == 1
            )


def test_choice_retry_reuses_immutable_resolved_answer_without_revalidation(
    interview_client_factory,
):
    from web.api.interviews.models import InterviewTurn

    model = ChoiceRetryModel()
    client, app = interview_client_factory(model)
    with client:
        session = client.post(
            "/api/interviews",
            headers=headers(),
            json={
                "name": "Review interview",
                "customer_id": "acme",
                "consent_version": "2026-09-15",
                "consent_accepted": True,
                "request_id": str(uuid4()),
                "selected_stages": ["review"],
            },
        ).json()["session"]
        question = session["turns"][0]
        request_id = str(uuid4())
        payload = {
            "expected_revision": session["revision"],
            "request_id": request_id,
            "choice_answer": {
                "question_turn_id": question["id"],
                "option_id": "approval-wait",
            },
        }
        failed = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json=payload,
        )
        assert failed.status_code == 503
        with app.state.session_factory.begin() as db:
            stored_question = db.get(InterviewTurn, question["id"])
            assert stored_question is not None
            stored_question.options_json = []

        model.fail = False
        retried = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json=payload,
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["session"]["turns"][1]["text"] == "승인 대기"
        assert model.calls[-1].turns[-1].text == "승인 대기"
        with app.state.session_factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(InterviewTurn)
                    .where(
                        InterviewTurn.session_id == session["id"],
                        InterviewTurn.role == "user",
                    )
                )
                == 1
            )


def test_abandoned_operation_retry_wins_and_late_completion_is_rejected(
    interview_client_factory,
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from web.api.interviews.models import InterviewOperation, InterviewSession

    model = RetryRaceModel()
    client, app = interview_client_factory(model)
    with client:
        session = start_interview(client)
        request_id = str(uuid4())
        first_result: dict = {}
        thread = Thread(
            target=_post_answer,
            args=(client, session, request_id, first_result),
        )
        thread.start()
        assert model.entered.wait(2)

        expired_lease = datetime.now(UTC) - timedelta(seconds=1)
        with app.state.session_factory.begin() as db:
            db.execute(
                update(InterviewOperation)
                .where(
                    InterviewOperation.session_id == session["id"],
                    InterviewOperation.request_id == request_id,
                )
                .values(lease_expires_at=expired_lease)
            )
            db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == session["id"])
                .values(last_operation_lease_expires_at=expired_lease)
            )

        expired = client.get(
            f"/api/interviews/{session['id']}", headers=headers()
        )
        assert expired.status_code == 200
        assert expired.json()["session"]["last_operation"] == {
            "request_id": request_id,
            "kind": "answer",
            "status": "running",
            "lease_expired": True,
        }

        retried = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": request_id,
                "answer": "The handoff is slow.",
            },
        )
        assert retried.status_code == 200
        assert model.calls == 3

        model.release.set()
        thread.join(5)
        assert first_result["status"] == 409
        assert first_result["body"]["code"] == "operation_superseded"
        assert [
            turn["role"] for turn in retried.json()["session"]["turns"]
        ] == ["assistant", "user", "assistant"]


def test_expiry_during_inference_rejects_completion(interview_client_factory):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from web.api.interviews.models import InterviewSession

    model = BlockingModel()
    client, app = interview_client_factory(model)
    with client:
        session = start_interview(client)
        result: dict = {}
        thread = Thread(
            target=_post_answer,
            args=(client, session, str(uuid4()), result),
        )
        thread.start()
        assert model.entered.wait(2)

        with app.state.session_factory.begin() as db:
            db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == session["id"])
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        model.release.set()
        thread.join(5)

        assert result["status"] == 409
        assert result["body"]["code"] == "operation_superseded"
        assert (
            client.get(
                f"/api/interviews/{session['id']}", headers=headers()
            ).status_code
            == 404
        )


def test_confirmation_revision_claim_is_atomic_across_two_connections(
    cas_race_client_factory,
):
    model = CasRaceModel()
    client, app, service = cas_race_client_factory(model)
    with client:
        session = start_interview(client)
        answered = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json={
                "expected_revision": session["revision"],
                "request_id": str(uuid4()),
                "answer": "The handoff is slow.",
            },
        ).json()["session"]
        evidence_id = answered["proposed_evidence"][0]["id"]
        service.arm_claim_barrier()
        results = [{}, {}]
        threads = [
            Thread(
                target=_post_json,
                args=(
                    client,
                    f"/api/interviews/{session['id']}/confirmations",
                    {
                        "expected_revision": answered["revision"],
                        "request_id": str(uuid4()),
                        "decisions": [
                            {
                                "evidence_id": evidence_id,
                                "decision": decision,
                            }
                        ],
                    },
                    results[index],
                ),
            )
            for index, decision in enumerate(("confirm", "reject"))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)

        assert {result["status"] for result in results} == {200, 409}
        assert len(service.claim_connection_ids) == 2
        winner = next(result for result in results if result["status"] == 200)
        assert winner["body"]["session"]["revision"] == 3

        from sqlalchemy import func, select
        from web.api.interviews.models import InterviewOperation

        with app.state.session_factory() as db:
            assert db.scalar(
                select(func.count())
                .select_from(InterviewOperation)
                .where(
                    InterviewOperation.session_id == session["id"],
                    InterviewOperation.kind == "confirmation",
                )
            ) == 1


def test_failed_answer_retry_cannot_steal_new_claim(
    cas_race_client_factory,
):
    model = CasRaceModel()
    client, _, service = cas_race_client_factory(model)
    actor = Actor("org-acme", "author-1", frozenset({"author"}))
    with client:
        session = start_interview(client)
        failed_request_id = str(uuid4())
        failed_payload = {
            "expected_revision": session["revision"],
            "request_id": failed_request_id,
            "answer": "The failed answer.",
        }
        model.fail = True
        failed = client.post(
            f"/api/interviews/{session['id']}/turns",
            headers=headers(),
            json=failed_payload,
        )
        assert failed.status_code == 503

        model.fail = False
        service.arm_claim_barrier(delayed_thread_name="failed-retry")
        retry_result: dict = {}
        new_result: dict = {}
        retry = Thread(
            name="failed-retry",
            target=_call_answer,
            args=(
                service,
                actor,
                session["id"],
                failed_payload,
                retry_result,
            ),
        )
        new = Thread(
            name="new-answer",
            target=_call_answer,
            args=(
                service,
                actor,
                session["id"],
                {
                    "expected_revision": session["revision"],
                    "request_id": str(uuid4()),
                    "answer": "The winning new answer.",
                },
                new_result,
            ),
        )
        retry.start()
        new.start()
        retry.join(5)
        new.join(5)

        assert retry_result["status"] == 409
        assert new_result["status"] == 200
        assert len(service.claim_connection_ids) == 2
        assert len(model.calls) == 3
        assert model.calls[-1].turns[-1].text == "The winning new answer."


def test_failed_creation_retry_has_one_atomic_owner(
    cas_race_client_factory,
):
    model = CasRaceModel()
    model.fail = True
    client, _, service = cas_race_client_factory(model)
    actor = Actor("org-acme", "author-1", frozenset({"author"}))
    with client:
        request_id = str(uuid4())
        payload = {
            "name": "Acme delivery interview",
            "customer_id": "acme",
            "consent_version": "2026-09-15",
            "consent_accepted": True,
            "request_id": request_id,
        }
        failed = client.post("/api/interviews", headers=headers(), json=payload)
        assert failed.status_code == 503

        model.fail = False
        service.arm_claim_barrier(delayed_thread_name="losing-retry")
        results = [{}, {}]
        threads = [
            Thread(
                name=name,
                target=_call_start,
                args=(service, actor, payload, results[index]),
            )
            for index, name in enumerate(("winning-retry", "losing-retry"))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)

        assert results[0]["status"] == 200
        assert results[1]["status"] == 409
        assert len(service.claim_connection_ids) == 2
        assert len(model.calls) == 2
