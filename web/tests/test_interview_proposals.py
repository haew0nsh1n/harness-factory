import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from harness_factory import load_json
from web.acceptance.portal_interview_app import ReviewOnlyFixtureModel
from web.api.config import Settings
from web.api.db import Base
from web.api.designs.models import (
    APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
    Approval,
    HarnessDesign,
)
from web.api.interviews import routes as interview_routes
from web.api.interviews.model import InterviewContext
from web.api.interviews.models import (
    InterviewOperation,
    InterviewProposal,
    InterviewSession,
)
from web.api.interviews.proposals import ProposalService
from web.api.interviews.schemas import DraftCandidate, InterviewReply
from web.api.main import create_app
from web.api.organizations.models import Organization


ROOT = Path(__file__).resolve().parents[2]


def headers(
    organization_id: str = "org-acme",
    subject_id: str = "author-1",
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
        "X-HF-Roles": "author",
    }


def candidate_value() -> dict[str, object]:
    profile = load_json(ROOT / "examples/github-issue/profile.json")
    workflow = load_json(ROOT / "examples/github-issue/workflow.json")
    scenarios = load_json(ROOT / "examples/github-issue/scenarios.json")
    workflow.pop("approved")
    profile["facts"] = [
        {
            "id": "model-fact",
            "statement": "The model called this a fact.",
            "evidence": "model output",
        }
    ]
    profile["assumptions"] = ["The repository has tests."]
    profile["unknowns"] = ["Authentication has not been checked."]
    return {"profile": profile, "workflow": workflow, "scenarios": scenarios}


class ProposalModel:
    def __init__(self, candidate: object | None = None) -> None:
        self.candidate = candidate or DraftCandidate.model_validate(candidate_value())
        self.proposal_calls: list[tuple[InterviewContext, dict[str, object]]] = []

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        raise AssertionError("question generation is not used by proposal tests")

    async def propose_design(
        self, context: InterviewContext, catalog: dict[str, object]
    ) -> DraftCandidate:
        self.proposal_calls.append((context, catalog))
        return self.candidate

    async def close(self) -> None:
        return None


class BlockingProposalModel(ProposalModel):
    def __init__(self) -> None:
        super().__init__()
        self.block = None
        self.entered = Event()
        self.release = Event()

    def arm(self, kind: str) -> None:
        self.block = kind
        self.entered.clear()
        self.release.clear()

    async def next_question(self, context: InterviewContext) -> InterviewReply:
        if self.block == "answer":
            self.entered.set()
            await asyncio.to_thread(self.release.wait, 5)
        return InterviewReply(
            question="What should improve?",
            stage="planning",
            evidence=[],
            proposed_scope=None,
            ready_for_review=False,
        )

    async def propose_design(
        self, context: InterviewContext, catalog: dict[str, object]
    ) -> DraftCandidate:
        if self.block == "proposal":
            self.entered.set()
            await asyncio.to_thread(self.release.wait, 5)
        return await super().propose_design(context, catalog)


class PausingApplyProposalService(ProposalService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pause_before_advance = False
        self.advance_entered = Event()
        self.advance_release = Event()

    def arm_advance_pause(self) -> None:
        self.pause_before_advance = True
        self.advance_entered.clear()
        self.advance_release.clear()

    def _advance_session_for_apply(self, db, session, **kwargs) -> None:
        if self.pause_before_advance:
            self.advance_entered.set()
            self.advance_release.wait(5)
        return super()._advance_session_for_apply(db, session, **kwargs)


@pytest.fixture
def proposal_api():
    clients: list[TestClient] = []

    def build(candidate: object | None = None):
        model = ProposalModel(candidate)
        app = create_app(
            Settings(
                auth_mode="development",
                allow_insecure_development_auth=True,
                database_url="sqlite+pysqlite:///:memory:",
                catalog_root=ROOT / "catalog",
            ),
            interview_model_factory=lambda settings: model,
        )
        Base.metadata.create_all(app.state.engine)
        with app.state.session_factory.begin() as db:
            db.add_all(
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
        client = TestClient(app)
        clients.append(client)
        return client, model, app

    yield build

    for client in clients:
        client.close()


@pytest.fixture
def proposal_concurrency_api(tmp_path, monkeypatch):
    database_path = tmp_path / "proposal-concurrency.db"
    model = BlockingProposalModel()
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url=f"sqlite+pysqlite:///{database_path}",
            catalog_root=ROOT / "catalog",
        ),
        interview_model_factory=lambda settings: model,
    )
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory.begin() as db:
        db.add(
            Organization(
                id="org-acme",
                entra_tenant_id="tenant-acme",
                name="Acme",
            )
        )
    proposal_service = PausingApplyProposalService(
        app.state.session_factory,
        app.state.settings,
        model,
    )
    monkeypatch.setattr(
        interview_routes,
        "_proposal_service",
        lambda request: proposal_service,
    )
    client = TestClient(app)
    yield client, model, app, proposal_service
    client.close()
    app.state.engine.dispose()


def seed_interview(
    app,
    *,
    organization_id: str = "org-acme",
    scope: str | None = "issue-to-reviewed-pr",
    selected_stages: list[str] | None = None,
) -> InterviewSession:
    now = datetime.now(UTC)
    session = InterviewSession(
        id=str(uuid4()),
        organization_id=organization_id,
        owner_subject_id="author-1",
        name="Acme interview",
        customer_id="example-team",
        revision=4,
        status="active",
        consent_version="2026-09-15",
        consented_at=now,
        stage="summary",
        selected_scope=scope,
        selected_stages_json=selected_stages,
        proposed_evidence_json=[
            {
                "id": str(uuid4()),
                "statement": "This unconfirmed statement must not become a fact.",
                "kind": "fact",
                "source_turn_ids": [],
            },
            {
                "id": str(uuid4()),
                "statement": "Repository permissions are still unknown.",
                "kind": "unknown",
                "source_turn_ids": [],
            },
        ],
        confirmed_evidence_json=[
            {
                "id": str(uuid4()),
                "statement": "Acceptance ambiguity is the confirmed bottleneck.",
                "kind": "fact",
                "source_turn_ids": [],
            }
        ],
        creation_request_id=str(uuid4()),
        creation_input_digest="a" * 64,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
    )
    with app.state.session_factory.begin() as db:
        db.add(session)
    return session


def generate(client: TestClient, session: InterviewSession, request_id=None):
    return client.post(
        f"/api/interviews/{session.id}/proposals",
        headers=headers(session.organization_id),
        json={
            "expected_revision": session.revision,
            "request_id": request_id or str(uuid4()),
        },
    )


def apply_payload(proposal: dict[str, object], **overrides):
    payload = {
        "expected_revision": proposal["revision"],
        "proposal_id": proposal["id"],
        "expected_proposal_digest": proposal["digest"],
        "confirm_scope": True,
        "design_id": None,
        "expected_design_digest": None,
    }
    payload.update(overrides)
    return payload


def post_json(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    result: dict[str, object],
) -> None:
    response = client.post(path, headers=headers(), json=payload)
    result.update(status=response.status_code, body=response.json())


def test_authoritative_catalog_endpoint_is_read_only_and_proposal_is_unapproved(
    proposal_api,
):
    client, model, app = proposal_api()
    session = seed_interview(app)

    catalog_response = client.get("/api/interviews/catalog", headers=headers())
    response = generate(client, session)

    assert catalog_response.status_code == 200
    assert catalog_response.json()["catalog"] == load_json(ROOT / "catalog/catalog.json")
    assert response.status_code == 201, response.text
    proposal = response.json()["proposal"]
    assert proposal["catalog"] == catalog_response.json()["catalog"]
    assert proposal["workflow"].get("approved") is None
    assert proposal["profile"]["facts"] == [
        {
            "id": "fact-1",
            "statement": "Acceptance ambiguity is the confirmed bottleneck.",
            "evidence": "Confirmed during interview.",
        }
    ]
    assert "This unconfirmed statement must not become a fact." not in {
        fact["statement"] for fact in proposal["profile"]["facts"]
    }
    assert "Repository permissions are still unknown." in proposal["profile"]["unknowns"]
    assert model.proposal_calls[0][1] == catalog_response.json()["catalog"]


def test_generate_rejects_malformed_persisted_scope_before_model_call(proposal_api):
    client, model, app = proposal_api()
    session = seed_interview(app, scope="review_bottleneck")
    request_id = str(uuid4())

    rejected = generate(client, session, request_id)

    assert rejected.status_code == 409
    assert rejected.json()["code"] == "scope_invalid"
    assert model.proposal_calls == []
    with app.state.session_factory() as db:
        assert (
            db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.session_id == session.id,
                    InterviewOperation.request_id == request_id,
                )
            )
            is None
        )


def test_proposal_detail_is_tenant_scoped_expiry_guarded_and_digest_checked(
    proposal_api,
):
    client, _, app = proposal_api()
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]

    loaded = client.get(
        f"/api/interviews/{session.id}/proposals/{proposal['id']}",
        headers=headers(),
    )
    cross_tenant = client.get(
        f"/api/interviews/{session.id}/proposals/{proposal['id']}",
        headers=headers("org-other"),
    )
    unauthorized = client.get(
        f"/api/interviews/{session.id}/proposals/{proposal['id']}",
        headers={
            "X-HF-Organization": "org-acme",
            "X-HF-Subject": "viewer-1",
            "X-HF-Roles": "viewer",
        },
    )

    assert loaded.status_code == 200
    assert loaded.json()["proposal"] == proposal
    assert cross_tenant.status_code == 404
    assert unauthorized.status_code == 403

    with app.state.session_factory.begin() as db:
        stored = db.get(InterviewProposal, proposal["id"])
        assert stored is not None
        candidate = deepcopy(stored.candidate_json)
        candidate["workflow"]["goal"] = "Tampered after persistence"
        stored.candidate_json = candidate
    tampered = client.get(
        f"/api/interviews/{session.id}/proposals/{proposal['id']}",
        headers=headers(),
    )
    assert tampered.status_code == 409
    assert tampered.json()["code"] == "stale_proposal"

    with app.state.session_factory.begin() as db:
        db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session.id)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    expired = client.get(
        f"/api/interviews/{session.id}/proposals/{proposal['id']}",
        headers=headers(),
    )
    assert expired.status_code == 404


def test_missing_scope_remains_actionable_and_apply_requires_confirmation(proposal_api):
    client, _, app = proposal_api()
    session = seed_interview(app, scope=None)
    proposal_response = generate(client, session)

    assert proposal_response.status_code == 201
    proposal = proposal_response.json()["proposal"]
    assert any(
        finding["code"] == "scope-not-selected" for finding in proposal["findings"]
    )
    rejected = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json={**apply_payload(proposal), "confirm_scope": False},
    )

    assert rejected.status_code == 422


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["workflow"]["steps"][0].update(
            {"skill": "invented-skill"}
        ),
        lambda value: value["workflow"]["steps"][0].update(
            {"tools": ["github.admin-write"]}
        ),
    ],
)
def test_invalid_model_catalog_references_are_rejected_not_filtered(
    proposal_api, mutation
):
    value = candidate_value()
    mutation(value)
    client, _, app = proposal_api(DraftCandidate.model_validate(value))
    session = seed_interview(app)

    response = generate(client, session)

    assert response.status_code == 503
    assert response.json()["code"] == "llm_invalid_result"
    with app.state.session_factory() as db:
        assert db.scalars(select(InterviewProposal)).all() == []


def test_proposal_rejects_unselected_sdlc_entries_even_for_fake_model(proposal_api):
    client, model, app = proposal_api()
    session = seed_interview(app, selected_stages=["review"])

    response = generate(client, session)

    assert response.status_code == 503
    assert response.json()["code"] == "llm_invalid_result"
    assert model.proposal_calls[0][0].selected_stages == ("review",)
    with app.state.session_factory() as db:
        assert db.scalars(select(InterviewProposal)).all() == []


def test_review_only_browser_fixture_proposal_remains_applyable(proposal_api):
    fixture_model = ReviewOnlyFixtureModel(ROOT / "examples")
    candidate = asyncio.run(
        fixture_model.propose_design(
            InterviewContext(
                session_id="fixture-session",
                revision=1,
                turns=(),
                confirmed_evidence=(),
                stage="review",
                selected_scope="issue-to-reviewed-pr",
                selected_stages=("review",),
            ),
            {},
        )
    )
    client, _, app = proposal_api(candidate)
    session = seed_interview(app, selected_stages=["review"])

    proposal_response = generate(client, session)

    assert proposal_response.status_code == 201, proposal_response.text
    proposal = proposal_response.json()["proposal"]
    assert [item["stage"] for item in proposal["profile"]["sdlc"]] == ["review"]
    applied = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(proposal),
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["design"]["workflow"]["id"] == "issue-to-reviewed-pr"


def test_model_forged_approval_and_catalog_are_rejected(proposal_api):
    forged = candidate_value()
    forged["workflow"]["approved"] = {"by": "model", "at": "now"}
    forged["catalog"] = {"skills": []}
    client, _, app = proposal_api(forged)
    session = seed_interview(app)

    response = generate(client, session)

    assert response.status_code == 503
    assert response.json()["code"] == "llm_invalid_result"


def test_incomplete_candidate_is_persisted_with_actionable_findings(proposal_api):
    value = candidate_value()
    value["scenarios"]["workflow"] = "missing-workflow"
    client, _, app = proposal_api(DraftCandidate.model_validate(value))
    session = seed_interview(app)

    response = generate(client, session)

    assert response.status_code == 201
    proposal = response.json()["proposal"]
    assert proposal["scenarios"]["workflow"] == "missing-workflow"
    assert any(
        finding["code"] == "incomplete-design"
        and "workflow" in finding["message"]
        for finding in proposal["findings"]
    )


def test_apply_uses_exact_persisted_proposal_and_is_idempotent(proposal_api):
    client, _, app = proposal_api()
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    payload = apply_payload(proposal)

    applied = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(subject_id="consultant-7"),
        json=payload,
    )
    duplicate = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(subject_id="consultant-7"),
        json=payload,
    )

    assert applied.status_code == 200, applied.text
    assert duplicate.status_code == 200
    assert duplicate.json() == applied.json()
    design = applied.json()["design"]
    assert design["status"] == "draft"
    assert design["workflow"]["approved"]["by"] == "consultant-7"
    assert datetime.fromisoformat(design["workflow"]["approved"]["at"]).tzinfo
    with app.state.session_factory() as db:
        assert len(db.scalars(select(HarnessDesign)).all()) == 1
        stored = db.get(InterviewProposal, proposal["id"])
        assert stored is not None
        assert stored.status == "accepted"


@pytest.mark.parametrize("operation_kind", ["proposal", "answer"])
def test_apply_rejects_live_operation_without_invalidating_its_lease(
    proposal_concurrency_api,
    operation_kind,
):
    client, model, app, _ = proposal_concurrency_api
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    model.arm(operation_kind)
    operation_result: dict[str, object] = {}
    if operation_kind == "proposal":
        path = f"/api/interviews/{session.id}/proposals"
        payload = {
            "expected_revision": proposal["revision"],
            "request_id": str(uuid4()),
        }
    else:
        path = f"/api/interviews/{session.id}/turns"
        payload = {
            "expected_revision": proposal["revision"],
            "request_id": str(uuid4()),
            "answer": "Continue the interview.",
        }
    operation_thread = Thread(
        target=post_json,
        args=(client, path, payload, operation_result),
    )
    operation_thread.start()
    assert model.entered.wait(2)

    with app.state.session_factory() as db:
        active = db.scalar(
            select(InterviewOperation).where(
                InterviewOperation.session_id == session.id,
                InterviewOperation.request_id == payload["request_id"],
            )
        )
        assert active is not None
        active_token = active.ownership_token
        active_lease = active.lease_expires_at

    rejected = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(proposal),
    )

    assert rejected.status_code == 409
    assert rejected.json()["code"] == "interview_busy"
    with app.state.session_factory() as db:
        active = db.scalar(
            select(InterviewOperation).where(
                InterviewOperation.session_id == session.id,
                InterviewOperation.request_id == payload["request_id"],
            )
        )
        assert active is not None
        assert active.status == "running"
        assert active.ownership_token == active_token
        assert active.lease_expires_at == active_lease
        assert db.get(InterviewProposal, proposal["id"]).status == "draft"

    model.release.set()
    operation_thread.join(5)
    assert operation_result["status"] in {200, 201}


def test_expired_proposal_is_retryable_and_late_owner_cannot_overwrite(
    proposal_concurrency_api,
):
    client, model, app, _ = proposal_concurrency_api
    session = seed_interview(app)
    request_id = str(uuid4())
    payload = {
        "expected_revision": session.revision,
        "request_id": request_id,
    }
    model.arm("proposal")
    first_result: dict[str, object] = {}
    first_thread = Thread(
        target=post_json,
        args=(
            client,
            f"/api/interviews/{session.id}/proposals",
            payload,
            first_result,
        ),
    )
    first_thread.start()
    assert model.entered.wait(2)

    expired_lease = datetime.now(UTC) - timedelta(seconds=1)
    with app.state.session_factory.begin() as db:
        db.execute(
            update(InterviewOperation)
            .where(
                InterviewOperation.session_id == session.id,
                InterviewOperation.request_id == request_id,
            )
            .values(lease_expires_at=expired_lease)
        )
        db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session.id)
            .values(last_operation_lease_expires_at=expired_lease)
        )

    expired = client.get(
        f"/api/interviews/{session.id}", headers=headers()
    )
    assert expired.status_code == 200
    assert expired.json()["session"]["last_operation"]["lease_expired"] is True

    model.block = None
    retried = client.post(
        f"/api/interviews/{session.id}/proposals",
        headers=headers(),
        json=payload,
    )
    assert retried.status_code == 201, retried.text
    assert len(model.proposal_calls) == 1

    model.release.set()
    first_thread.join(5)
    assert first_result["status"] == 409
    assert first_result["body"]["code"] == "operation_superseded"
    with app.state.session_factory() as db:
        assert len(
            db.scalars(
                select(InterviewProposal).where(
                    InterviewProposal.session_id == session.id
                )
            ).all()
        ) == 1


def test_apply_cas_rejects_operation_claimed_after_session_read(
    proposal_concurrency_api,
):
    client, model, app, proposal_service = proposal_concurrency_api
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    proposal_service.arm_advance_pause()
    apply_result: dict[str, object] = {}
    apply_thread = Thread(
        target=post_json,
        args=(
            client,
            f"/api/interviews/{session.id}/apply",
            apply_payload(proposal),
            apply_result,
        ),
    )
    apply_thread.start()
    assert proposal_service.advance_entered.wait(2)

    model.arm("answer")
    answer_result: dict[str, object] = {}
    request_id = str(uuid4())
    answer_thread = Thread(
        target=post_json,
        args=(
            client,
            f"/api/interviews/{session.id}/turns",
            {
                "expected_revision": proposal["revision"],
                "request_id": request_id,
                "answer": "Claim after the apply read.",
            },
            answer_result,
        ),
    )
    answer_thread.start()
    assert model.entered.wait(2)
    proposal_service.advance_release.set()
    apply_thread.join(5)

    assert apply_result["status"] == 409
    assert apply_result["body"]["code"] == "interview_busy"
    with app.state.session_factory() as db:
        operation = db.scalar(
            select(InterviewOperation).where(
                InterviewOperation.session_id == session.id,
                InterviewOperation.request_id == request_id,
            )
        )
        assert operation is not None
        assert operation.status == "running"
        assert db.get(InterviewProposal, proposal["id"]).status == "draft"
        assert db.scalars(select(HarnessDesign)).all() == []

    model.release.set()
    answer_thread.join(5)
    assert answer_result["status"] == 200


def test_exact_duplicate_apply_remains_idempotent_during_live_operation(
    proposal_concurrency_api,
):
    client, model, app, _ = proposal_concurrency_api
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    payload = apply_payload(proposal)
    applied = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=payload,
    )
    assert applied.status_code == 200

    model.arm("answer")
    answer_result: dict[str, object] = {}
    answer_thread = Thread(
        target=post_json,
        args=(
            client,
            f"/api/interviews/{session.id}/turns",
            {
                "expected_revision": proposal["revision"] + 1,
                "request_id": str(uuid4()),
                "answer": "Continue after acceptance.",
            },
            answer_result,
        ),
    )
    answer_thread.start()
    assert model.entered.wait(2)

    duplicate = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=payload,
    )

    assert duplicate.status_code == 200
    assert duplicate.json() == applied.json()
    with app.state.session_factory() as db:
        operation = db.scalar(
            select(InterviewOperation).where(
                InterviewOperation.session_id == session.id,
                InterviewOperation.status == "running",
            )
        )
        assert operation is not None

    model.release.set()
    answer_thread.join(5)
    assert answer_result["status"] == 200


def test_proposal_tamper_stale_revision_and_cross_tenant_target_are_rejected(
    proposal_api,
):
    client, _, app = proposal_api()
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]

    tampered = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(proposal, expected_proposal_digest="f" * 64),
    )
    with app.state.session_factory.begin() as db:
        other_design = HarnessDesign(
            id=str(uuid4()),
            organization_id="org-other",
            customer_id="example-team",
            name="Other",
            profile_json=deepcopy(proposal["profile"]),
            workflow_json={
                **deepcopy(proposal["workflow"]),
                "approved": {
                    "by": "other",
                    "at": datetime.now(UTC).isoformat(),
                },
            },
            scenarios_json=deepcopy(proposal["scenarios"]),
            catalog_json=deepcopy(proposal["catalog"]),
            revision=1,
            digest="e" * 64,
            status="draft",
            created_by="other",
        )
        db.add(other_design)
    cross_tenant = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(
            proposal,
            design_id=other_design.id,
            expected_design_digest=other_design.digest,
        ),
    )
    with app.state.session_factory.begin() as db:
        db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session.id)
            .values(revision=proposal["revision"] + 1)
        )
    stale = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(proposal),
    )

    assert tampered.status_code == 409
    assert tampered.json()["code"] == "stale_proposal"
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_revision"
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["code"] == "target_design_not_found"


def test_stored_proposal_body_tamper_is_detected_before_apply(proposal_api):
    client, _, app = proposal_api()
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    with app.state.session_factory.begin() as db:
        stored = db.get(InterviewProposal, proposal["id"])
        assert stored is not None
        candidate = deepcopy(stored.candidate_json)
        candidate["workflow"]["goal"] = "Substituted after review."
        stored.candidate_json = candidate

    response = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(proposal),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_proposal"
    with app.state.session_factory() as db:
        assert db.scalars(select(HarnessDesign)).all() == []


def test_concurrent_design_edit_makes_apply_stale_and_preserves_edit(proposal_api):
    client, _, app = proposal_api()
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    created = client.post(
        "/api/designs",
        headers=headers(),
        json={
            "customer_id": proposal["profile"]["customer_id"],
            "name": proposal["profile"]["name"],
            "profile": proposal["profile"],
            "workflow": {
                **proposal["workflow"],
                "approved": {
                    "by": "author-1",
                    "at": datetime.now(UTC).isoformat(),
                },
            },
            "scenarios": proposal["scenarios"],
            "catalog": proposal["catalog"],
        },
    ).json()["design"]
    edit = deepcopy(created)
    edit["workflow"]["goal"] = "Concurrent author edit"
    edit_request = {
        key: edit[key]
        for key in (
            "customer_id",
            "name",
            "profile",
            "workflow",
            "scenarios",
            "catalog",
        )
    }
    edit_request["expected_digest"] = created["digest"]
    changed = client.put(
        f"/api/designs/{created['id']}",
        headers=headers(),
        json=edit_request,
    ).json()["design"]

    stale_apply = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(
            proposal,
            design_id=created["id"],
            expected_design_digest=created["digest"],
        ),
    )

    assert changed["status"] == "draft"
    assert stale_apply.status_code == 409
    assert stale_apply.json()["code"] == "stale_digest"
    current = client.get(
        f"/api/designs/{created['id']}", headers=headers()
    ).json()["design"]
    assert current["workflow"]["goal"] == "Concurrent author edit"


def test_existing_design_apply_clears_prior_approval_records(proposal_api):
    client, _, app = proposal_api()
    session = seed_interview(app)
    proposal = generate(client, session).json()["proposal"]
    created = client.post(
        "/api/designs",
        headers=headers(),
        json={
            "customer_id": proposal["profile"]["customer_id"],
            "name": proposal["profile"]["name"],
            "profile": proposal["profile"],
            "workflow": proposal["workflow"],
            "scenarios": proposal["scenarios"],
            "catalog": proposal["catalog"],
        },
    ).json()["design"]
    with app.state.session_factory.begin() as db:
        db.add(
            Approval(
                id=str(uuid4()),
                organization_id="org-acme",
                subject_type=APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                subject_id=created["id"],
                subject_digest=created["digest"],
                decision="approved",
                actor_subject_id="reviewer-1",
            )
        )

    applied = client.post(
        f"/api/interviews/{session.id}/apply",
        headers=headers(),
        json=apply_payload(
            proposal,
            design_id=created["id"],
            expected_design_digest=created["digest"],
        ),
    )

    assert applied.status_code == 200, applied.text
    assert applied.json()["design"]["status"] == "draft"
    with app.state.session_factory() as db:
        approvals = db.scalars(
            select(Approval).where(
                Approval.organization_id == "org-acme",
                Approval.subject_id == created["id"],
            )
        ).all()
        assert approvals == []
