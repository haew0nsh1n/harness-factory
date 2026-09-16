"""add durable tenant-scoped interviews

Revision ID: 0005_interviews
Revises: 0004_published_channel
Create Date: 2026-09-15 14:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_interviews"
down_revision: str | None = "0004_published_channel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("owner_subject_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("customer_id", sa.String(length=80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("selected_scope", sa.String(length=256), nullable=True),
        sa.Column("proposed_evidence_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_evidence_json", sa.JSON(), nullable=False),
        sa.Column("creation_request_id", sa.String(length=36), nullable=False),
        sa.Column("creation_input_digest", sa.String(length=64), nullable=False),
        sa.Column("last_operation_request_id", sa.String(length=36), nullable=True),
        sa.Column("last_operation_kind", sa.String(length=32), nullable=True),
        sa.Column("last_operation_status", sa.String(length=16), nullable=True),
        sa.Column("last_operation_token", sa.String(length=36), nullable=True),
        sa.Column("last_operation_base_revision", sa.Integer(), nullable=True),
        sa.Column(
            "last_operation_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name="uq_interview_sessions_org_id",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "creation_request_id",
            name="uq_interview_sessions_org_creation_request",
        ),
    )
    op.create_index(
        "ix_interview_sessions_org_expiry",
        "interview_sessions",
        ["organization_id", "expires_at"],
        unique=False,
    )
    op.create_table(
        "interview_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ownership_token", sa.String(length=36), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["interview_sessions.organization_id", "interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "session_id",
            "request_id",
            name="uq_interview_operations_request",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "session_id",
            "id",
            name="uq_interview_operations_org_session_id",
        ),
    )
    op.create_index(
        "ix_interview_operations_session",
        "interview_operations",
        ["organization_id", "session_id"],
        unique=False,
    )
    op.create_table(
        "interview_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["interview_sessions.organization_id", "interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "session_id", "operation_id"],
            [
                "interview_operations.organization_id",
                "interview_operations.session_id",
                "interview_operations.id",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "session_id",
            "sequence",
            name="uq_interview_turns_sequence",
        ),
    )
    op.create_index(
        "ix_interview_turns_session",
        "interview_turns",
        ["organization_id", "session_id", "sequence"],
        unique=False,
    )
    op.create_table(
        "interview_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("candidate_json", sa.JSON(), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["interview_sessions.organization_id", "interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_proposals_session",
        "interview_proposals",
        ["organization_id", "session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_proposals_session", table_name="interview_proposals"
    )
    op.drop_table("interview_proposals")
    op.drop_index("ix_interview_turns_session", table_name="interview_turns")
    op.drop_table("interview_turns")
    op.drop_index(
        "ix_interview_operations_session", table_name="interview_operations"
    )
    op.drop_table("interview_operations")
    op.drop_index(
        "ix_interview_sessions_org_expiry", table_name="interview_sessions"
    )
    op.drop_table("interview_sessions")
