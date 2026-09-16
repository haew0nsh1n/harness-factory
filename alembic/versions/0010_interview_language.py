"""add language to interview sessions

Revision ID: 0010_interview_language
Revises: 0009_content_language
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_interview_language"
down_revision: str | None = "0009_content_language"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch:
        batch.add_column(
            sa.Column(
                "language",
                sa.String(length=8),
                nullable=False,
                server_default="ko",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch:
        batch.drop_column("language")
