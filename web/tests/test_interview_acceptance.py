from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from web.acceptance.distribution_flow import running_http_app
from web.acceptance.interview_flow import (
    StructuredFakeInterviewModel,
    run_interview_flow,
)
from web.api.builds.worker import BuildWorker
from web.api.audit.service import AuditService
from web.api.config import Settings
from web.api.db import Base, create_session_factory
from web.api.designs.repository import HarnessDesignRepository
from web.api.designs.service import DesignService
from web.api.interviews.azure import AzureOpenAIInterviewModel
from web.api.interviews.models import InterviewProposal, InterviewSession
from web.api.interviews.model import (
    ConfirmedEvidence,
    InterviewContext,
    InterviewTurn,
)
from web.api.interviews.proposals import ProposalService
from web.api.interviews.schemas import ApplyProposalRequest, ProposalRequest
from web.api.identity.models import Actor
from web.api.main import create_app
from web.api.organizations.bootstrap import bootstrap_development_tenant
from web.api.organizations.models import Organization


ROOT = Path(__file__).resolve().parents[2]


def _has_hangul(value: str) -> bool:
    return any("\uac00" <= character <= "\ud7a3" for character in value)


def _run(tmp_path: Path, packaged_cli, database_url: str) -> dict[str, object]:
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=database_url,
        catalog_root=ROOT / "catalog",
        artifact_root=tmp_path / "artifacts",
    )
    model = StructuredFakeInterviewModel(ROOT / "examples")
    app = create_app(settings, interview_model_factory=lambda _: model)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory.begin() as session:
        bootstrap_development_tenant(session, settings)
        session.add(
            Organization(
                id="acceptance-other",
                entra_tenant_id="acceptance-other",
                name="Other acceptance tenant",
            )
        )
    worker = BuildWorker(settings)
    try:
        with running_http_app(app) as base_url:
            result = run_interview_flow(
                settings=settings,
                workspace=tmp_path / "flow",
                hf_executable=str(packaged_cli.hf),
                python_executable=str(packaged_cli.python),
                base_url=base_url,
                examples_root=ROOT / "examples",
                on_build_poll=worker.run_once,
                require_postgres=database_url.startswith("postgresql"),
            )
    finally:
        worker.dispose()
        app.state.engine.dispose()
    assert model.question_calls == 2
    assert model.draft_calls == 1
    return result


def test_interview_to_installed_workflow_lifecycle(tmp_path, packaged_cli) -> None:
    result = _run(
        tmp_path,
        packaged_cli,
        f"sqlite+pysqlite:///{tmp_path / 'interview-acceptance.db'}",
    )

    assert result["proposed_design"]["status"] == "draft"
    assert result["validated_design"]["status"] == "validated"
    assert result["installation"]["operation"] == "install"
    assert result["ready_result"]["ready"] is False
    assert result["interview_deleted"] is True
    assert result["cross_tenant"] == "not_found"


@pytest.mark.skipif(
    not os.environ.get("HF_POSTGRES_TEST_URL"),
    reason="set HF_POSTGRES_TEST_URL for PostgreSQL interview acceptance",
)
def test_interview_to_installed_workflow_on_postgresql(
    tmp_path,
    packaged_cli,
) -> None:
    result = _run(tmp_path, packaged_cli, os.environ["HF_POSTGRES_TEST_URL"])
    assert result["database"] == "postgresql"
    assert result["installation"]["operation"] == "install"
    assert result["ready_result"]["ready"] is False


@pytest.mark.skipif(
    os.environ.get("HF_RUN_LIVE_AZURE_INTERVIEW") != "1",
    reason="set HF_RUN_LIVE_AZURE_INTERVIEW=1 for consented synthetic Azure check",
)
def test_live_azure_actual_candidate_validates() -> None:
    database_path = ROOT / ".harness-factory" / f"live-candidate-{uuid4()}.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=f"sqlite+pysqlite:///{database_path}",
        azure_openai_endpoint=os.environ["HF_AZURE_OPENAI_ENDPOINT"],
        azure_openai_deployment=os.environ["HF_AZURE_OPENAI_DEPLOYMENT"],
        catalog_root=ROOT / "catalog",
    )
    model = AzureOpenAIInterviewModel(settings)
    engine, session_factory = create_session_factory(settings)
    Base.metadata.create_all(engine)
    actor = Actor(
        organization_id=settings.development_organization_id,
        subject_id=settings.development_subject_id,
        roles=frozenset({"author", "reviewer", "org-admin"}),
    )
    now = datetime.now(UTC)
    session_id = str(uuid4())
    confirmed_statement = (
        "Fictional review criteria are clarified before implementation."
    )
    with session_factory.begin() as db:
        bootstrap_development_tenant(db, settings)
        db.add(
            InterviewSession(
                id=session_id,
                organization_id=actor.organization_id,
                owner_subject_id=actor.subject_id,
                name="Synthetic live validation",
                customer_id="synthetic-live-team",
                revision=3,
                status="active",
                consent_version="2026-09-15",
                consented_at=now,
                stage="summary",
                selected_scope="issue-to-reviewed-pr",
                proposed_evidence_json=[],
                confirmed_evidence_json=[
                    {
                        "id": str(uuid4()),
                        "statement": confirmed_statement,
                        "kind": "fact",
                        "source_turn_ids": ["turn-2"],
                    }
                ],
                creation_request_id=str(uuid4()),
                creation_input_digest="a" * 64,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
    context = InterviewContext(
        session_id=session_id,
        revision=3,
        turns=(
            InterviewTurn(
                id="turn-1",
                role="assistant",
                text="Which fictional SDLC handoff creates the most rework?",
            ),
            InterviewTurn(
                id="turn-2",
                role="user",
                text=(
                    "In a fictional team, unclear review criteria cause repeated "
                    "implementation rework. GitHub Issues is the source of truth."
                ),
            ),
        ),
        confirmed_evidence=(
            ConfirmedEvidence(
                id="evidence-1",
                statement=confirmed_statement,
                source_turn_ids=("turn-2",),
            ),
        ),
        stage="summary",
        selected_scope="issue-to-reviewed-pr",
    )
    initial_context = InterviewContext(
        session_id=str(uuid4()),
        revision=0,
        turns=(),
        confirmed_evidence=(),
        stage="discovery",
        selected_scope=None,
    )

    async def exercise():
        try:
            initial_question = await model.next_question(initial_context)
            followup_question = await model.next_question(context)
            proposal, created = await ProposalService(
                session_factory,
                settings,
                model,
            ).generate(
                actor,
                session_id,
                ProposalRequest(
                    expected_revision=3,
                    request_id=uuid4(),
                ),
            )
            return initial_question, followup_question, proposal, created
        finally:
            await model.close()

    try:
        initial_question, followup_question, proposal, created = asyncio.run(
            exercise()
        )
        assert created is True
        assert _has_hangul(initial_question.question), initial_question.question
        assert initial_question.question.count("?") <= 1
        assert _has_hangul(followup_question.question), followup_question.question
        assert followup_question.question.count("?") <= 1
        assert followup_question.evidence
        assert all(
            _has_hangul(evidence.statement)
            for evidence in followup_question.evidence
        ), followup_question.evidence
        assert all(
            source_id in {"turn-1", "turn-2"}
            for evidence in followup_question.evidence
            for source_id in evidence.source_turn_ids
        )
        if followup_question.proposed_scope is not None:
            assert not _has_hangul(followup_question.proposed_scope)
        assert proposal.workflow["id"] == "issue-to-reviewed-pr"
        assert _has_hangul(str(proposal.workflow["name"]))
        assert _has_hangul(str(proposal.workflow["goal"]))
        assert _has_hangul(str(proposal.profile["success_criteria"][0]))
        assert _has_hangul(str(proposal.scenarios["scenarios"][0]["given"]))
        assert "approved" not in proposal.workflow
        contract_findings = [
            finding
            for finding in proposal.findings
            if finding["field"] == "contract"
        ]
        assert contract_findings == [], contract_findings

        applied = ProposalService(session_factory, settings, model).apply(
            actor,
            session_id,
            ApplyProposalRequest(
                expected_revision=proposal.revision,
                proposal_id=proposal.id,
                expected_proposal_digest=proposal.digest,
                confirm_scope=True,
                design_id=None,
                expected_design_digest=None,
            ),
        )
        assert applied.status == "draft"
        assert applied.workflow_json["approved"]["by"] == actor.subject_id
        with session_factory.begin() as db:
            service = DesignService(
                HarnessDesignRepository(db),
                settings,
                AuditService(db),
            )
            validated_design = service.validate(actor.organization_id, applied.id)
            assert validated_design is not None
            assert validated_design.status == "validated"
            assert validated_design.validation_findings_json == []

        with session_factory() as db:
            stored_session = db.get(InterviewSession, session_id)
            stored_proposal = db.scalar(
                select(InterviewProposal).where(InterviewProposal.id == proposal.id)
            )
            assert stored_session is not None
            assert stored_session.consent_version == "2026-09-15"
            assert stored_session.consented_at is not None
            assert stored_proposal is not None
            assert stored_proposal.accepted_design_id == applied.id
            assert stored_proposal.accepted_design_digest == applied.digest

        print(
            json.dumps(
                {
                    "initial_question": initial_question.question,
                    "followup_question": followup_question.question,
                    "stage": followup_question.stage,
                    "evidence_count": len(followup_question.evidence),
                    "proposal_id": proposal.id,
                    "proposal_digest": proposal.digest,
                    "workflow_id": proposal.workflow["id"],
                    "contract_findings": 0,
                    "validated_design_id": applied.id,
                    "validated_design_status": "validated",
                    "server_authored_scope_approval": True,
                    "exact_digest_applied": True,
                    "consent_version": "2026-09-15",
                    "model_authored_approval": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    finally:
        engine.dispose()
        database_path.unlink(missing_ok=True)
