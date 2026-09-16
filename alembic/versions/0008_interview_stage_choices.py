"""add selected interview stages and resumable choices

Revision ID: 0008_interview_stage_choices
Revises: 0007_proposal_design_fk
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_interview_stage_choices"
down_revision = "0007_proposal_design_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch:
        batch.add_column(sa.Column("selected_stages_json", sa.JSON(), nullable=True))
    with op.batch_alter_table("interview_turns") as batch:
        batch.add_column(sa.Column("options_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("allow_custom_answer", sa.Boolean(), nullable=True))
        batch.add_column(
            sa.Column("choice_question_turn_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(
            sa.Column("choice_option_id", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch:
        batch.drop_column("choice_option_id")
        batch.drop_column("choice_question_turn_id")
        batch.drop_column("allow_custom_answer")
        batch.drop_column("options_json")
    with op.batch_alter_table("interview_sessions") as batch:
        batch.drop_column("selected_stages_json")
