from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from web.api.db import Base

BUILD_STATUS_QUEUED = "queued"
BUILD_STATUS_RUNNING = "running"
BUILD_STATUS_SUCCEEDED = "succeeded"
BUILD_STATUS_FAILED = "failed"
BUILD_STATUSES = frozenset(
    {
        BUILD_STATUS_QUEUED,
        BUILD_STATUS_RUNNING,
        BUILD_STATUS_SUCCEEDED,
        BUILD_STATUS_FAILED,
    }
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class BuildJob(Base):
    __tablename__ = "build_jobs"
    __table_args__ = (
        Index("ix_build_jobs_organization_id", "organization_id"),
        Index("ix_build_jobs_design_id", "design_id"),
        Index("ix_build_jobs_status", "status"),
        UniqueConstraint(
            "organization_id",
            "design_id",
            "design_digest",
            name="uq_build_jobs_design_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    design_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("harness_designs.id"),
        nullable=False,
    )
    design_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=BUILD_STATUS_QUEUED,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_key: Mapped[str | None] = mapped_column(String(500))
    artifact_digest: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
