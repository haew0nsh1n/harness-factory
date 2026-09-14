"""enforce one published asset version per channel

Revision ID: 0004_published_channel
Revises: 0003_build_identity
Create Date: 2026-09-14 16:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_published_channel"
down_revision: str | None = "0003_build_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_asset_versions_published_channel"


def _deprecate_superseded_published_versions() -> None:
    asset_versions = sa.table(
        "asset_versions",
        sa.column("id", sa.String(length=36)),
        sa.column("asset_id", sa.String(length=36)),
        sa.column("channel", sa.String(length=32)),
        sa.column("status", sa.String(length=16)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    ranked = sa.select(
        asset_versions.c.id.label("id"),
        sa.func.row_number()
        .over(
            partition_by=[asset_versions.c.asset_id, asset_versions.c.channel],
            order_by=[
                asset_versions.c.created_at.desc(),
                asset_versions.c.id.desc(),
            ],
        )
        .label("rank"),
    ).where(asset_versions.c.status == "published")
    ranked_subquery = ranked.subquery()
    superseded = sa.select(ranked_subquery.c.id).where(ranked_subquery.c.rank > 1)
    op.execute(
        asset_versions.update()
        .where(asset_versions.c.id.in_(superseded))
        .values(status="deprecated")
    )


def upgrade() -> None:
    _deprecate_superseded_published_versions()
    op.create_index(
        INDEX_NAME,
        "asset_versions",
        ["asset_id", "channel"],
        unique=True,
        sqlite_where=sa.text("status = 'published'"),
        postgresql_where=sa.text("status = 'published'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="asset_versions")
