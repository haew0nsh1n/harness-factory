from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from web.api.designs.digest import design_digest
from web.api.designs.models import (
    APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
    Approval,
    DESIGN_STATUS_DRAFT,
    DESIGN_STATUS_VALIDATED,
    HarnessDesign,
)
from web.api.designs.schemas import HarnessDesignRequest


@dataclass(frozen=True)
class StaleDraftDigest(Exception):
    pass


class HarnessDesignRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        organization_id: str,
        actor_id: str,
        request: HarnessDesignRequest,
    ) -> HarnessDesign:
        design = HarnessDesign(
            id=str(uuid4()),
            organization_id=organization_id,
            customer_id=request.customer_id,
            name=request.name,
            profile_json=request.profile,
            workflow_json=request.workflow,
            scenarios_json=request.scenarios,
            catalog_json=request.catalog,
            validation_findings_json=None,
            revision=1,
            digest=design_digest(
                request.profile,
                request.workflow,
                request.scenarios,
                request.catalog,
            ),
            status=DESIGN_STATUS_DRAFT,
            created_by=actor_id,
        )
        self._session.add(design)
        self._session.flush()
        return design

    def list(self, organization_id: str) -> Sequence[HarnessDesign]:
        return self._session.scalars(
            select(HarnessDesign)
            .where(HarnessDesign.organization_id == organization_id)
            .order_by(HarnessDesign.updated_at.desc(), HarnessDesign.id.asc())
        ).all()

    def get(self, organization_id: str, design_id: str) -> HarnessDesign | None:
        return self._session.scalar(
            select(HarnessDesign).where(
                HarnessDesign.organization_id == organization_id,
                HarnessDesign.id == design_id,
            )
        )

    def replace_draft(
        self,
        organization_id: str,
        design_id: str,
        request: HarnessDesignRequest,
    ) -> HarnessDesign | None:
        if request.expected_digest is not None:
            replaced = self._session.execute(
                update(HarnessDesign)
                .where(
                    HarnessDesign.organization_id == organization_id,
                    HarnessDesign.id == design_id,
                    HarnessDesign.digest == request.expected_digest,
                )
                .execution_options(synchronize_session=False)
                .values(
                    customer_id=request.customer_id,
                    name=request.name,
                    profile_json=request.profile,
                    workflow_json=request.workflow,
                    scenarios_json=request.scenarios,
                    catalog_json=request.catalog,
                    validation_findings_json=None,
                    revision=HarnessDesign.revision + 1,
                    digest=design_digest(
                        request.profile,
                        request.workflow,
                        request.scenarios,
                        request.catalog,
                    ),
                    status=DESIGN_STATUS_DRAFT,
                    updated_at=datetime.now(UTC),
                )
            )
            if replaced.rowcount != 1:
                if self.get(organization_id, design_id) is None:
                    return None
                raise StaleDraftDigest()
            self._session.expire_all()
            return self.get(organization_id, design_id)

        design = self.get(organization_id, design_id)
        if design is None:
            return None
        design.customer_id = request.customer_id
        design.name = request.name
        design.profile_json = request.profile
        design.workflow_json = request.workflow
        design.scenarios_json = request.scenarios
        design.catalog_json = request.catalog
        design.validation_findings_json = None
        design.revision += 1
        design.digest = design_digest(
            request.profile,
            request.workflow,
            request.scenarios,
            request.catalog,
        )
        design.status = DESIGN_STATUS_DRAFT
        self._session.flush()
        return design

    def clear_approvals(self, organization_id: str, design_id: str) -> None:
        self._session.execute(
            delete(Approval).where(
                Approval.organization_id == organization_id,
                Approval.subject_type == APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                Approval.subject_id == design_id,
            )
        )

    def save_validation(
        self,
        organization_id: str,
        design_id: str,
        digest: str,
        succeeded: bool,
        finding: dict[str, str] | None,
    ) -> HarnessDesign | None:
        design = self.get(organization_id, design_id)
        if design is None:
            return None
        design.digest = digest
        design.status = (
            DESIGN_STATUS_VALIDATED if succeeded else DESIGN_STATUS_DRAFT
        )
        if succeeded:
            design.validation_findings_json = []
        else:
            if finding is None:
                raise ValueError("finding is required when validation fails")
            design.validation_findings_json = [finding]
        self._session.flush()
        return design

    def create_approval(
        self,
        organization_id: str,
        design_id: str,
        digest: str,
        decision: str,
        actor_id: str,
    ) -> Approval:
        approval = Approval(
            id=str(uuid4()),
            organization_id=organization_id,
            subject_type=APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
            subject_id=design_id,
            subject_digest=digest,
            decision=decision,
            actor_subject_id=actor_id,
        )
        self._session.add(approval)
        self._session.flush()
        return approval
