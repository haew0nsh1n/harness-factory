"""enforce tenant-scoped accepted proposal designs

Revision ID: 0007_proposal_design_fk
Revises: 0006_proposal_acceptance
"""

from alembic import op


revision = "0007_proposal_design_fk"
down_revision = "0006_proposal_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("harness_designs") as batch:
        batch.create_unique_constraint(
            "uq_harness_designs_org_id",
            ["organization_id", "id"],
        )
    with op.batch_alter_table("interview_proposals") as batch:
        batch.create_foreign_key(
            "fk_interview_proposals_accepted_design",
            "harness_designs",
            ["organization_id", "accepted_design_id"],
            ["organization_id", "id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_proposals") as batch:
        batch.drop_constraint(
            "fk_interview_proposals_accepted_design",
            type_="foreignkey",
        )
    with op.batch_alter_table("harness_designs") as batch:
        batch.drop_constraint(
            "uq_harness_designs_org_id",
            type_="unique",
        )
