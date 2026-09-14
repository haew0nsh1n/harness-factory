"""web authoring registry schema

Revision ID: 0001_web_registry
Revises:
Create Date: 2026-09-14 13:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_web_registry"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("entra_tenant_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entra_tenant_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("actor_subject_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_organization_id",
        "audit_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_resource",
        "audit_events",
        ["organization_id", "resource_type", "resource_id"],
        unique=False,
    )
    op.create_table(
        "harness_designs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("customer_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("profile_json", sa.JSON(), nullable=False),
        sa.Column("workflow_json", sa.JSON(), nullable=False),
        sa.Column("scenarios_json", sa.JSON(), nullable=False),
        sa.Column("catalog_json", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_harness_designs_organization_id",
        "harness_designs",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "memberships",
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("subject_id", sa.String(length=80), nullable=False),
        sa.Column("roles_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("organization_id", "subject_id"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("subject_digest", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("actor_subject_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approvals_organization_id",
        "approvals",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_approvals_subject",
        "approvals",
        ["organization_id", "subject_type", "subject_id"],
        unique=False,
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("owner_subject_id", sa.String(length=80), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("lifecycle", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_assets_org_slug"),
    )
    op.create_index(
        "ix_assets_organization_id",
        "assets",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "asset_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("artifact_key", sa.String(length=500), nullable=False),
        sa.Column("artifact_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "version",
            name="uq_asset_versions_asset_version",
        ),
    )
    op.create_index(
        "ix_asset_versions_organization_id",
        "asset_versions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_asset_versions_asset_id",
        "asset_versions",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_asset_versions_status",
        "asset_versions",
        ["status"],
        unique=False,
    )
    op.create_table(
        "build_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=80), nullable=False),
        sa.Column("design_id", sa.String(length=36), nullable=False),
        sa.Column("design_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("artifact_key", sa.String(length=500), nullable=True),
        sa.Column("artifact_digest", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["design_id"], ["harness_designs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_build_jobs_organization_id",
        "build_jobs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_build_jobs_design_id",
        "build_jobs",
        ["design_id"],
        unique=False,
    )
    op.create_index(
        "ix_build_jobs_status",
        "build_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_build_jobs_status", table_name="build_jobs")
    op.drop_index("ix_build_jobs_design_id", table_name="build_jobs")
    op.drop_index("ix_build_jobs_organization_id", table_name="build_jobs")
    op.drop_table("build_jobs")
    op.drop_index("ix_asset_versions_status", table_name="asset_versions")
    op.drop_index("ix_asset_versions_asset_id", table_name="asset_versions")
    op.drop_index("ix_asset_versions_organization_id", table_name="asset_versions")
    op.drop_table("asset_versions")
    op.drop_index("ix_assets_organization_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_approvals_subject", table_name="approvals")
    op.drop_index("ix_approvals_organization_id", table_name="approvals")
    op.drop_table("approvals")
    op.drop_table("memberships")
    op.drop_index(
        "ix_harness_designs_organization_id",
        table_name="harness_designs",
    )
    op.drop_table("harness_designs")
    op.drop_index("ix_audit_events_resource", table_name="audit_events")
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("organizations")
