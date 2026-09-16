from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker

from web.api.config import Settings, get_settings
from web.api.db import create_session_factory
from web.api.designs.models import HarnessDesign
from web.api.designs.samples import SAMPLE_TEMPLATE_KEYS, seed_sample_designs
from web.api.identity.models import Actor
from web.api.interviews.azure import AzureOpenAIInterviewModel
from web.api.interviews.errors import InterviewModelError
from web.api.interviews.models import InterviewSession, InterviewTurn
from web.api.interviews.service import InterviewService
from web.api.main import create_app
from web.api.organizations.bootstrap import bootstrap_development_tenant


ROOT = Path(__file__).resolve().parents[2]
DATABASE_NAME = "hf_ux2_acceptance_f192955a"
AZURE_ENDPOINT = "https://proj-aimain.cognitiveservices.azure.com/"
AZURE_DEPLOYMENT = "gpt-5.6-sol"
HEADERS = {
    "X-HF-Organization": "local-dev",
    "X-HF-Subject": "portal-dev",
    "X-HF-Roles": "author,reviewer,org-admin",
}


class DiagnosticAzureInterviewModel(AzureOpenAIInterviewModel):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.safe_proposal_error: dict[str, object] | None = None

    async def propose_design(self, context, catalog):
        try:
            return await super().propose_design(context, catalog)
        except Exception as exc:
            original: BaseException = exc
            for _ in range(4):
                if original.__cause__ is None:
                    break
                original = original.__cause__
            body = getattr(original, "body", None)
            provider_error = body.get("error", body) if isinstance(body, dict) else {}
            message = provider_error.get("message")
            validation_errors = getattr(original, "errors", None)
            validation_detail = None
            if callable(validation_errors):
                errors = validation_errors(include_input=False, include_url=False)
                if errors:
                    first = errors[0]
                    validation_detail = {
                        "location": list(first.get("loc", ())),
                        "type": first.get("type"),
                        "message": first.get("msg"),
                    }
            if message is None and isinstance(original, (TypeError, ValueError)):
                message = str(original)
            self.safe_proposal_error = {
                "model_error_code": (
                    exc.code if isinstance(exc, InterviewModelError) else None
                ),
                "exception_type": type(original).__name__,
                "http_status": getattr(original, "status_code", None),
                "provider_code": provider_error.get("code"),
                "provider_param": provider_error.get("param"),
                "message": str(message)[:400] if message is not None else None,
                "validation": validation_detail,
            }
            raise


def _has_hangul(value: str) -> bool:
    return any("\uac00" <= character <= "\ud7a3" for character in value)


def _postgres_url() -> str:
    value = os.environ.get("HF_POSTGRES_TEST_URL")
    if not value:
        pytest.skip("set HF_POSTGRES_TEST_URL for focused PostgreSQL acceptance")
    parsed = urlparse(value)
    assert parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    assert parsed.path.removeprefix("/") == DATABASE_NAME
    return value


def _reset_postgres(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _assert_korean_question(turn: dict[str, object], *, require_options: bool) -> None:
    assert turn["role"] == "assistant"
    assert _has_hangul(str(turn["text"])), turn["text"]
    assert str(turn["text"]).count("?") <= 1
    assert turn["allow_custom_answer"] is True
    options = turn["options"]
    assert isinstance(options, list)
    assert len(options) <= 6
    if require_options:
        assert 2 <= len(options) <= 5, turn
    assert all(_has_hangul(str(option["label"])) for option in options), options


def _answer_choice(
    client: TestClient,
    session: dict[str, object],
    question: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    selected = question["options"][0]
    request_id = str(uuid4())
    payload = {
        "request_id": request_id,
        "expected_revision": session["revision"],
        "choice_answer": {
            "question_turn_id": question["id"],
            "option_id": selected["id"],
        },
    }
    response = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=HEADERS,
        json=payload,
    )
    assert response.status_code == 200, response.text
    answered = response.json()["session"]
    user_turn = next(
        turn
        for turn in answered["turns"]
        if turn["role"] == "user"
        and turn["choice_question_turn_id"] == question["id"]
    )
    assert user_turn["text"] == selected["label"]
    assert user_turn["choice_option_id"] == selected["id"]
    resumed = client.get(
        f"/api/interviews/{session['id']}", headers=HEADERS
    ).json()["session"]
    assert resumed["turns"] == answered["turns"]
    replay = client.post(
        f"/api/interviews/{session['id']}/turns",
        headers=HEADERS,
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["session"]["turns"] == answered["turns"]
    return answered, user_turn


@pytest.mark.skipif(
    os.environ.get("HF_RUN_LIVE_AZURE_FOCUSED_INTERVIEW") != "1",
    reason="set HF_RUN_LIVE_AZURE_FOCUSED_INTERVIEW=1 for the consented live check",
)
def test_live_azure_review_choices_persist_and_candidate_validates(
    monkeypatch,
) -> None:
    database_url = _postgres_url()
    _reset_postgres(database_url)
    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(_alembic_config(database_url), "head")

    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=database_url,
        azure_openai_endpoint=AZURE_ENDPOINT,
        azure_openai_deployment=AZURE_DEPLOYMENT,
        catalog_root=ROOT / "catalog",
    )
    engine, session_factory = create_session_factory(settings)
    with session_factory.begin() as db:
        bootstrap_development_tenant(db, settings)
    engine.dispose()

    model = DiagnosticAzureInterviewModel(settings)
    app = create_app(settings, interview_model_factory=lambda _: model)
    selected_user_turns: list[dict[str, object]] = []
    unchosen_labels: set[str] = set()
    try:
        with TestClient(app) as client:
            started_response = client.post(
                "/api/interviews",
                headers=HEADERS,
                json={
                    "name": "가상 코드 검토 병목 인터뷰",
                    "customer_id": "synthetic-review-team",
                    "consent_version": "2026-09-15",
                    "consent_accepted": True,
                    "request_id": str(uuid4()),
                    "selected_stages": ["review"],
                },
            )
            assert started_response.status_code == 201, started_response.text
            session = started_response.json()["session"]
            assert session["selected_stages"] == ["review"]
            assert session["stage"] == "review"
            first_question = session["turns"][-1]
            _assert_korean_question(first_question, require_options=True)
            unchosen_labels.update(
                option["label"] for option in first_question["options"][1:]
            )
            session, first_answer = _answer_choice(
                client, session, first_question
            )
            selected_user_turns.append(first_answer)
            followup_question = session["turns"][-1]
            _assert_korean_question(followup_question, require_options=True)
            assert followup_question["id"] != first_question["id"]
            assert session["stage"] in {"review", "summary"}
            unchosen_labels.update(
                option["label"] for option in followup_question["options"][1:]
            )
            session, followup_answer = _answer_choice(
                client, session, followup_question
            )
            selected_user_turns.append(followup_answer)

            detail_question = session["turns"][-1]
            assert detail_question["role"] == "assistant"
            _assert_korean_question(detail_question, require_options=False)
            assert session["stage"] in {"review", "summary"}
            detail_response = client.post(
                f"/api/interviews/{session['id']}/turns",
                headers=HEADERS,
                json={
                    "request_id": str(uuid4()),
                    "expected_revision": session["revision"],
                    "answer": (
                        "가상의 팀은 GitHub Issues의 synthetic-org/review-workflow를 "
                        "업무 원본으로 사용합니다. 현재 작성자가 CODEOWNERS와 담당 영역을 "
                        "보고 리뷰어를 직접 찾으며, 앞으로는 변경 파일 기준 추천 목록과 "
                        "담당자의 수동 승인 기록으로 검토 완료를 확인하려고 합니다."
                    ),
                },
            )
            assert detail_response.status_code == 200, detail_response.text
            session = detail_response.json()["session"]

            for _ in range(3):
                if session["scope"] is not None:
                    break
                question = session["turns"][-1]
                assert question["role"] == "assistant"
                _assert_korean_question(question, require_options=False)
                assert session["stage"] in {"review", "summary"}
                if question["options"]:
                    session, user_turn = _answer_choice(client, session, question)
                    selected_user_turns.append(user_turn)
                else:
                    response = client.post(
                        f"/api/interviews/{session['id']}/turns",
                        headers=HEADERS,
                        json={
                            "request_id": str(uuid4()),
                            "expected_revision": session["revision"],
                            "answer": (
                                "가상의 팀은 검토 기준 체크리스트와 담당자 확인 기록으로 "
                                "완료 여부를 판단하며 외부 시스템 쓰기는 수동 승인 뒤 수행합니다."
                            ),
                        },
                    )
                    assert response.status_code == 200, response.text
                    session = response.json()["session"]
            assert session["scope"] is not None, session
            assert re.fullmatch(r"[a-z][a-z0-9-]*", session["scope"]), session["scope"]

            user_turn_ids = {
                turn["id"] for turn in session["turns"] if turn["role"] == "user"
            }
            for evidence in session["proposed_evidence"]:
                assert set(evidence["source_turn_ids"]) <= user_turn_ids, evidence
                assert evidence["statement"] not in unchosen_labels

            if session["proposed_evidence"]:
                confirmation = client.post(
                    f"/api/interviews/{session['id']}/confirmations",
                    headers=HEADERS,
                    json={
                        "request_id": str(uuid4()),
                        "expected_revision": session["revision"],
                        "decisions": [
                            {
                                "evidence_id": evidence["id"],
                                "decision": "confirm",
                            }
                            for evidence in session["proposed_evidence"]
                        ],
                    },
                )
                assert confirmation.status_code == 200, confirmation.text
                session = confirmation.json()["session"]
            assert all(
                set(evidence["source_turn_ids"]) <= user_turn_ids
                for evidence in session["confirmed_evidence"]
            )

            proposal_started = time.monotonic()
            proposal_response = client.post(
                f"/api/interviews/{session['id']}/proposals",
                headers=HEADERS,
                json={
                    "request_id": str(uuid4()),
                    "expected_revision": session["revision"],
                },
            )
            proposal_seconds = time.monotonic() - proposal_started
            assert proposal_response.status_code == 201, (
                f"{proposal_response.text}; proposal_seconds={proposal_seconds:.3f}; "
                f"safe_error={json.dumps(model.safe_proposal_error, sort_keys=True)}"
            )
            proposal = proposal_response.json()["proposal"]
            assert [item["stage"] for item in proposal["profile"]["sdlc"]] == [
                "review"
            ]
            assert proposal["workflow"]["id"] == session["scope"]
            assert re.fullmatch(r"[a-z][a-z0-9-]*", proposal["workflow"]["id"])
            assert "approved" not in proposal["workflow"]
            print(
                json.dumps(
                    {
                        "candidate_generated": True,
                        "proposal_seconds": round(proposal_seconds, 3),
                        "scope": session["scope"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            assert not [
                finding
                for finding in proposal["findings"]
                if finding["field"] == "contract"
            ], proposal["findings"]

            applied_response = client.post(
                f"/api/interviews/{session['id']}/apply",
                headers=HEADERS,
                json={
                    "expected_revision": proposal["revision"],
                    "proposal_id": proposal["id"],
                    "expected_proposal_digest": proposal["digest"],
                    "confirm_scope": True,
                    "design_id": None,
                    "expected_design_digest": None,
                },
            )
            assert applied_response.status_code == 200, applied_response.text
            applied = applied_response.json()["design"]
            assert applied["status"] == "draft"
            assert applied["workflow"]["approved"]["by"] == "portal-dev"

            validation_response = client.post(
                f"/api/designs/{applied['id']}/validate",
                headers=HEADERS,
            )
            assert validation_response.status_code == 200, validation_response.text
            validated = validation_response.json()["design"]
            assert validated["status"] == "validated"
            assert validated["validation_findings"] == []

            with app.state.session_factory() as db:
                stored = db.get(InterviewSession, session["id"])
                stored_turns = db.scalars(
                    select(InterviewTurn)
                    .where(InterviewTurn.session_id == session["id"])
                    .order_by(InterviewTurn.sequence)
                ).all()
                assert stored is not None
                assert stored.selected_stages_json == ["review"]
                assert stored_turns[0].options_json == first_question["options"]
                assert stored_turns[1].text == first_answer["text"]
                assert (
                    stored_turns[1].choice_question_turn_id
                    == first_question["id"]
                )
                assert (
                    stored_turns[1].choice_option_id
                    == first_answer["choice_option_id"]
                )

            print(
                json.dumps(
                    {
                        "actual_model": type(model).__name__,
                        "azure_endpoint": AZURE_ENDPOINT,
                        "azure_deployment": AZURE_DEPLOYMENT,
                        "first_question": first_question["text"],
                        "first_options": first_question["options"],
                        "followup_question": followup_question["text"],
                        "followup_options": followup_question["options"],
                        "selected_choice_texts": [
                            turn["text"] for turn in selected_user_turns
                        ],
                        "candidate_sdlc": proposal["profile"]["sdlc"],
                        "workflow_id": proposal["workflow"]["id"],
                        "contract_findings": 0,
                        "proposal_seconds": round(proposal_seconds, 3),
                        "validated_design_status": validated["status"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    finally:
        app.state.engine.dispose()
        get_settings.cache_clear()


def test_postgres_0008_migration_and_sample_bootstrap_cas(monkeypatch) -> None:
    database_url = _postgres_url()
    _reset_postgres(database_url)
    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = _alembic_config(database_url)
    command.upgrade(config, "0007_proposal_design_fk")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, entra_tenant_id, name)
                    VALUES ('legacy-org', 'legacy-tenant', 'Legacy fictional org')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO interview_sessions (
                        id, organization_id, owner_subject_id, name, customer_id,
                        revision, status, consent_version, consented_at, stage,
                        selected_scope, proposed_evidence_json,
                        confirmed_evidence_json, creation_request_id,
                        creation_input_digest, created_at, updated_at, expires_at
                    ) VALUES (
                        'legacy-session', 'legacy-org', 'legacy-author',
                        '기존 가상 인터뷰', 'legacy-fictional', 1, 'active',
                        '2026-09-15', CURRENT_TIMESTAMP, 'review', NULL,
                        '[]', '[]', 'legacy-create', :digest,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP + INTERVAL '1 day'
                    )
                    """
                ),
                {"digest": "a" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO interview_operations (
                        id, organization_id, session_id, request_id, kind,
                        input_digest, status, ownership_token, base_revision,
                        lease_expires_at, created_at, updated_at
                    ) VALUES (
                        'legacy-operation', 'legacy-org', 'legacy-session',
                        'legacy-request', 'start', :digest, 'succeeded',
                        'legacy-token', 0, CURRENT_TIMESTAMP + INTERVAL '1 day',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {"digest": "b" * 64},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO interview_turns (
                        id, organization_id, session_id, operation_id,
                        sequence, role, text, created_at
                    ) VALUES (
                        'legacy-turn', 'legacy-org', 'legacy-session',
                        'legacy-operation', 1, 'assistant', '기존 질문',
                        CURRENT_TIMESTAMP
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        columns = {
            column["name"] for column in inspect(engine).get_columns("interview_turns")
        }
        assert {
            "options_json",
            "allow_custom_answer",
            "choice_question_turn_id",
            "choice_option_id",
        } <= columns
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT selected_stages_json, text, options_json,
                           allow_custom_answer, choice_question_turn_id,
                           choice_option_id
                    FROM interview_sessions
                    JOIN interview_turns
                      ON interview_turns.session_id = interview_sessions.id
                    WHERE interview_sessions.id = 'legacy-session'
                    """
                )
            ).one()
            assert row == (None, "기존 질문", None, None, None, None)
        legacy = InterviewService(
            sessionmaker(bind=engine),
            Settings(
                auth_mode="development",
                allow_insecure_development_auth=True,
                database_url=database_url,
            ),
            object(),
        ).get(
            Actor(
                organization_id="legacy-org",
                subject_id="legacy-author",
                roles=frozenset({"author"}),
            ),
            "legacy-session",
        )
        assert legacy.selected_stages == [
            "discovery",
            "planning",
            "implementation",
            "testing",
            "review",
            "release",
            "operations",
        ]
        assert legacy.turns[0].options == []
        assert legacy.turns[0].allow_custom_answer is True
    finally:
        engine.dispose()

    command.downgrade(config, "0007_proposal_design_fk")
    engine = create_engine(database_url)
    try:
        assert "selected_stages_json" not in {
            column["name"]
            for column in inspect(engine).get_columns("interview_sessions")
        }
        with engine.begin() as connection:
            assert connection.scalar(
                text(
                    "SELECT text FROM interview_turns "
                    "WHERE id = 'legacy-turn'"
                )
            ) == "기존 질문"
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=database_url,
        catalog_root=ROOT / "catalog",
    )
    engine, session_factory = create_session_factory(settings)
    with session_factory.begin() as db:
        assert db.get(InterviewTurn, "legacy-turn").options_json is None

    barrier = Barrier(2)

    def bootstrap_and_seed() -> list[bool]:
        barrier.wait()
        with session_factory.begin() as db:
            bootstrap_development_tenant(db, settings)
            return [
                result.created
                for result in seed_sample_designs(
                    db,
                    organization_id=settings.development_organization_id,
                    actor_id=settings.development_subject_id,
                )
            ]

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: bootstrap_and_seed(), range(2)))
        assert sum(sum(outcome) for outcome in outcomes) == len(SAMPLE_TEMPLATE_KEYS)

        with session_factory.begin() as db:
            repeated = seed_sample_designs(
                db,
                organization_id=settings.development_organization_id,
                actor_id=settings.development_subject_id,
            )
            assert not any(result.created for result in repeated)

        with session_factory() as db:
            samples = db.scalars(
                select(HarnessDesign).where(
                    HarnessDesign.organization_id
                    == settings.development_organization_id
                )
            ).all()
            assert len(samples) == len(SAMPLE_TEMPLATE_KEYS)
            assert db.scalar(
                select(func.count())
                .select_from(HarnessDesign)
                .where(
                    HarnessDesign.organization_id
                    == settings.development_organization_id
                )
            ) == len(SAMPLE_TEMPLATE_KEYS)
            assert all(sample.status == "draft" for sample in samples)

        print(
            json.dumps(
                {
                    "database": DATABASE_NAME,
                    "migration": "0007 -> 0008 -> 0007 -> 0008",
                    "legacy_selected_stages": "all-seven-via-null",
                    "legacy_options": [],
                    "concurrent_created_total": sum(
                        sum(outcome) for outcome in outcomes
                    ),
                    "sample_count": len(SAMPLE_TEMPLATE_KEYS),
                    "repeat_created_total": sum(
                        result.created for result in repeated
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    finally:
        engine.dispose()
        get_settings.cache_clear()
