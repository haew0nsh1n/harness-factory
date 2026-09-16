from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from web.api.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_interview_sessions_org_id",
        ),
        UniqueConstraint(
            "organization_id",
            "creation_request_id",
            name="uq_interview_sessions_org_creation_request",
        ),
        Index(
            "ix_interview_sessions_org_expiry",
            "organization_id",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_subject_id: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovery"
    )
    selected_scope: Mapped[str | None] = mapped_column(String(256), nullable=True)
    proposed_evidence_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    confirmed_evidence_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    creation_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    creation_input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    last_operation_request_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    last_operation_kind: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    last_operation_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    last_operation_token: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    last_operation_base_revision: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    last_operation_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class InterviewOperation(Base):
    __tablename__ = "interview_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["interview_sessions.organization_id", "interview_sessions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "session_id",
            "request_id",
            name="uq_interview_operations_request",
        ),
        UniqueConstraint(
            "organization_id",
            "session_id",
            "id",
            name="uq_interview_operations_org_session_id",
        ),
        Index(
            "ix_interview_operations_session",
            "organization_id",
            "session_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    ownership_token: Mapped[str] = mapped_column(String(36), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["interview_sessions.organization_id", "interview_sessions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "session_id", "operation_id"],
            [
                "interview_operations.organization_id",
                "interview_operations.session_id",
                "interview_operations.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "session_id",
            "sequence",
            name="uq_interview_turns_sequence",
        ),
        Index(
            "ix_interview_turns_session",
            "organization_id",
            "session_id",
            "sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class InterviewProposal(Base):
    __tablename__ = "interview_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["interview_sessions.organization_id", "interview_sessions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "accepted_design_id"],
            ["harness_designs.organization_id", "harness_designs.id"],
            name="fk_interview_proposals_accepted_design",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_interview_proposals_session",
            "organization_id",
            "session_id",
            "created_at",
        ),
        UniqueConstraint(
            "organization_id",
            "session_id",
            "generation_request_id",
            name="uq_interview_proposals_generation_request",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    generation_request_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    candidate_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    findings_json: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    apply_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_design_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    accepted_design_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    accepted_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
