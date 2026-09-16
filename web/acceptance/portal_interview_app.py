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
from web.api.main import create_app
from web.api.organizations.bootstrap import bootstrap_development_tenant


ROOT = Path(__file__).resolve().parents[2]
TARGET_NAME = "Existing synthetic design"


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
        interview_model_factory=lambda _: StructuredFakeInterviewModel(
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
