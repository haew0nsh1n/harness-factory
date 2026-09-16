"""Deterministic real API fixture for the Playwright interview integration."""

from pathlib import Path

from harness_factory import load_json
from sqlalchemy import func, select
from web.acceptance.interview_flow import StructuredFakeInterviewModel
from web.api.audit.service import AuditService
from web.api.config import Settings
from web.api.db import Base
from web.api.designs.repository import HarnessDesignRepository
from web.api.designs.schemas import HarnessDesignRequest
from web.api.designs.service import DesignService
from web.api.designs.models import (
    APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
    Approval,
)
from web.api.identity.models import Actor
from web.api.interviews.schemas import (
    DraftCandidate,
    InterviewReply,
    SuggestedEvidence,
)
from web.api.main import create_app
from web.api.organizations.bootstrap import bootstrap_development_tenant


ROOT = Path(__file__).resolve().parents[2]
TARGET_NAME = "Existing synthetic design"


class ReviewOnlyFixtureModel(StructuredFakeInterviewModel):
    async def next_question(self, context):
        self.question_calls += 1
        if not context.turns:
            return InterviewReply(
                question="검토 단계에서 가장 큰 병목은 무엇인가요?",
                stage="review",
                evidence=[],
                proposed_scope=None,
                ready_for_review=False,
                options=[
                    {"id": "unclear-criteria", "label": "불명확한 검토 기준"},
                    {"id": "approval-wait", "label": "승인 대기"},
                    {"id": "manual-handoff", "label": "수동 인계"},
                ],
                allow_custom_answer=True,
            )
        return InterviewReply(
            question="이 검토 워크플로 범위로 진행할까요?",
            stage="summary",
            evidence=[
                SuggestedEvidence(
                    id="fixture-review-bottleneck",
                    statement=(
                        f"검토 단계의 병목으로 '{context.turns[-1].text}'을(를) "
                        "선택했습니다."
                    ),
                    kind="fact",
                    source_turn_ids=[context.turns[-1].id],
                )
            ],
            proposed_scope="issue-to-reviewed-pr",
            ready_for_review=True,
            options=[
                {"id": "continue", "label": "이 범위로 계속"},
                {"id": "refine", "label": "범위를 더 구체화"},
            ],
            allow_custom_answer=True,
        )

    async def propose_design(self, context, catalog):
        candidate = await super().propose_design(context, catalog)
        value = candidate.model_dump()
        value["profile"]["sdlc"] = [
            item for item in value["profile"]["sdlc"] if item["stage"] == "review"
        ]
        return DraftCandidate.model_validate(value)


def create_integration_app():
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=(
            "sqlite+pysqlite:///"
            + str(ROOT / ".harness-factory/playwright-interview.db")
        ),
        catalog_root=ROOT / "catalog",
        artifact_root=ROOT / ".harness-factory/playwright-artifacts",
    )
    app = create_app(
        settings,
        interview_model_factory=lambda _: ReviewOnlyFixtureModel(
            ROOT / "examples"
        ),
    )
    Base.metadata.create_all(app.state.engine)
    actor = Actor(
        organization_id=settings.development_organization_id,
        subject_id=settings.development_subject_id,
        roles=frozenset({"author", "reviewer", "org-admin"}),
    )
    with app.state.session_factory.begin() as db:
        bootstrap_development_tenant(db, settings)
        profile = load_json(ROOT / "examples/github-issue/profile.json")
        workflow = load_json(ROOT / "examples/github-issue/workflow.json")
        scenarios = load_json(ROOT / "examples/github-issue/scenarios.json")
        catalog = load_json(ROOT / "catalog/catalog.json")
        profile["customer_id"] = "synthetic-team"
        profile["name"] = TARGET_NAME
        workflow["customer_id"] = "synthetic-team"
        service = DesignService(
            HarnessDesignRepository(db),
            settings,
            AuditService(db),
        )
        design = service.create(
            actor.organization_id,
            actor.subject_id,
            HarnessDesignRequest(
                customer_id="synthetic-team",
                name=TARGET_NAME,
                profile=profile,
                workflow=workflow,
                scenarios=scenarios,
                catalog=catalog,
            ),
        )
        validated = service.validate(actor.organization_id, design.id)
        if validated is None:
            raise RuntimeError("integration target validation failed")
        service.approve_design(
            actor.organization_id,
            actor.subject_id,
            validated.id,
            validated.digest,
            "approved",
        )

    @app.get("/api/acceptance/designs/{design_id}/approval-count")
    def approval_count(design_id: str) -> dict[str, object]:
        with app.state.session_factory() as db:
            count = db.scalar(
                select(func.count())
                .select_from(Approval)
                .where(
                    Approval.organization_id == actor.organization_id,
                    Approval.subject_type
                    == APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                    Approval.subject_id == design_id,
                )
            )
        return {
            "ok": True,
            "design_id": design_id,
            "approval_count": count,
            "database": "sqlite",
        }

    return app
