from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from web.api.db import Base

DESIGN_STATUS_DRAFT = "draft"
DESIGN_STATUS_VALIDATED = "validated"
DESIGN_STATUS_APPROVED = "approved"
DESIGN_STATUS_BUILD_QUEUED = "build-queued"
DESIGN_STATUS_BUILT = "built"
DESIGN_STATUS_FAILED = "failed"
DESIGN_STATUSES = frozenset(
    {
        DESIGN_STATUS_DRAFT,
        DESIGN_STATUS_VALIDATED,
        DESIGN_STATUS_APPROVED,
        DESIGN_STATUS_BUILD_QUEUED,
        DESIGN_STATUS_BUILT,
        DESIGN_STATUS_FAILED,
    }
)

APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN = "harness-design"
APPROVAL_SUBJECT_TYPE_ASSET_VERSION = "asset-version"
APPROVAL_SUBJECT_TYPES = frozenset(
    {
        APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
        APPROVAL_SUBJECT_TYPE_ASSET_VERSION,
    }
)
APPROVAL_DECISION_APPROVED = "approved"
APPROVAL_DECISION_REJECTED = "rejected"
APPROVAL_DECISIONS = frozenset(
    {APPROVAL_DECISION_APPROVED, APPROVAL_DECISION_REJECTED}
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class HarnessDesign(Base):
    __tablename__ = "harness_designs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    workflow_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    scenarios_json: Mapped[list[object]] = mapped_column(JSON, nullable=False)
    catalog_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    validation_findings_json: Mapped[list[dict[str, str]] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DESIGN_STATUS_DRAFT,
    )
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_organization_id", "organization_id"),
        Index(
            "ix_approvals_subject",
            "organization_id",
            "subject_type",
            "subject_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    subject_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_subject_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
