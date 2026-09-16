"""interview proposal acceptance linkage

Revision ID: 0006_proposal_acceptance
Revises: 0005_interviews
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_proposal_acceptance"
down_revision = "0005_interviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interview_proposals") as batch:
        batch.add_column(
            sa.Column("generation_request_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(
            sa.Column("apply_digest", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("accepted_design_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "accepted_design_digest", sa.String(length=64), nullable=True
            )
        )
        batch.add_column(
            sa.Column("accepted_by", sa.String(length=80), nullable=True)
        )
        batch.add_column(
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_unique_constraint(
            "uq_interview_proposals_generation_request",
            ["organization_id", "session_id", "generation_request_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_proposals") as batch:
        batch.drop_constraint(
            "uq_interview_proposals_generation_request",
            type_="unique",
        )
        batch.drop_column("accepted_at")
        batch.drop_column("accepted_by")
        batch.drop_column("accepted_design_digest")
        batch.drop_column("accepted_design_id")
        batch.drop_column("apply_digest")
        batch.drop_column("generation_request_id")
