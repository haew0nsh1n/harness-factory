"""add language tag to harness designs and registry assets

Revision ID: 0009_content_language
Revises: 0008_interview_stage_choices
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_content_language"
down_revision: str | None = "0008_interview_stage_choices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("harness_designs", "assets"):
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(
                sa.Column(
                    "language",
                    sa.String(length=8),
                    nullable=False,
                    server_default="ko",
                )
            )
        op.create_index(
            f"ix_{table_name}_language",
            table_name,
            ["language"],
            unique=False,
        )


def downgrade() -> None:
    for table_name in ("harness_designs", "assets"):
        op.drop_index(f"ix_{table_name}_language", table_name=table_name)
        with op.batch_alter_table(table_name) as batch:
            batch.drop_column("language")
