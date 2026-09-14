"""enforce unique build job design identity

Revision ID: 0003_build_identity
Revises: 0002_validation_findings
Create Date: 2026-09-14 14:50:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_build_identity"
down_revision: str | None = "0002_validation_findings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _collapse_duplicate_build_job_design_identities() -> None:
    build_jobs = sa.table(
        "build_jobs",
        sa.column("id", sa.String(length=36)),
        sa.column("organization_id", sa.String(length=80)),
        sa.column("design_id", sa.String(length=36)),
        sa.column("design_digest", sa.String(length=64)),
        sa.column("status", sa.String(length=16)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    status_rank = sa.case(
        (build_jobs.c.status == "succeeded", 0),
        (build_jobs.c.status == "running", 1),
        (build_jobs.c.status == "queued", 2),
        (build_jobs.c.status == "failed", 3),
        else_=4,
    )
    ranked_build_jobs = sa.select(
        build_jobs.c.id.label("id"),
        sa.func.row_number()
        .over(
            partition_by=[
                build_jobs.c.organization_id,
                build_jobs.c.design_id,
                build_jobs.c.design_digest,
            ],
            order_by=[
                status_rank.asc(),
                build_jobs.c.updated_at.desc(),
                build_jobs.c.created_at.desc(),
                build_jobs.c.id.asc(),
            ],
        )
        .label("row_number"),
    ).cte("ranked_build_jobs")

    op.execute(
        sa.delete(build_jobs).where(
            build_jobs.c.id.in_(
                sa.select(ranked_build_jobs.c.id).where(
                    ranked_build_jobs.c.row_number > 1
                )
            )
        )
    )


def upgrade() -> None:
    _collapse_duplicate_build_job_design_identities()
    with op.batch_alter_table("build_jobs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_build_jobs_design_identity",
            ["organization_id", "design_id", "design_digest"],
        )


def downgrade() -> None:
    with op.batch_alter_table("build_jobs") as batch_op:
        batch_op.drop_constraint(
            "uq_build_jobs_design_identity",
            type_="unique",
        )
