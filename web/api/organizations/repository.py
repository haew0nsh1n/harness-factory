from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from web.api.organizations.models import Membership, Organization


@dataclass(frozen=True)
class OrganizationBoundary:
    organization_id: str


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_entra_tenant_id(
        self, entra_tenant_id: str
    ) -> OrganizationBoundary | None:
        organization_id = self._session.scalar(
            select(Organization.id).where(
                Organization.entra_tenant_id == entra_tenant_id
            )
        )
        if organization_id is None:
            return None
        return OrganizationBoundary(organization_id=organization_id)


class MembershipRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_subject_id(
        self, organization_id: str, subject_id: str
    ) -> Membership | None:
        return self._session.scalar(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.subject_id == subject_id,
            )
        )
