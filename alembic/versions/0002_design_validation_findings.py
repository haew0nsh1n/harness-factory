"""add design validation findings

Revision ID: 0002_validation_findings
Revises: 0001_web_registry
Create Date: 2026-09-14 13:45:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_validation_findings"
down_revision: str | None = "0001_web_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("harness_designs") as batch_op:
        batch_op.add_column(
            sa.Column("validation_findings_json", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("harness_designs") as batch_op:
        batch_op.drop_column("validation_findings_json")
