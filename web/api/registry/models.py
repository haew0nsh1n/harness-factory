from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from web.api.db import Base

ASSET_KIND_SKILL = "skill"
ASSET_KIND_PLUGIN = "plugin"
ASSET_KIND_WORKFLOW = "workflow"
ASSET_KINDS = frozenset({ASSET_KIND_SKILL, ASSET_KIND_PLUGIN, ASSET_KIND_WORKFLOW})

ASSET_VISIBILITY_INTERNAL = "internal"
ASSET_VISIBILITIES = frozenset({ASSET_VISIBILITY_INTERNAL})

ASSET_LIFECYCLE_ACTIVE = "active"
ASSET_LIFECYCLE_ARCHIVED = "archived"
ASSET_LIFECYCLES = frozenset(
    {ASSET_LIFECYCLE_ACTIVE, ASSET_LIFECYCLE_ARCHIVED}
)

ASSET_VERSION_STATUS_DRAFT = "draft"
ASSET_VERSION_STATUS_VALIDATED = "validated"
ASSET_VERSION_STATUS_IN_REVIEW = "in-review"
ASSET_VERSION_STATUS_APPROVED = "approved"
ASSET_VERSION_STATUS_PUBLISHED = "published"
ASSET_VERSION_STATUS_DEPRECATED = "deprecated"
ASSET_VERSION_STATUS_REVOKED = "revoked"
ASSET_VERSION_STATUSES = frozenset(
    {
        ASSET_VERSION_STATUS_DRAFT,
        ASSET_VERSION_STATUS_VALIDATED,
        ASSET_VERSION_STATUS_IN_REVIEW,
        ASSET_VERSION_STATUS_APPROVED,
        ASSET_VERSION_STATUS_PUBLISHED,
        ASSET_VERSION_STATUS_DEPRECATED,
        ASSET_VERSION_STATUS_REVOKED,
    }
)

ASSET_VERSION_CHANNEL_UNPUBLISHED = "unpublished"
ASSET_VERSION_CHANNEL_PILOT = "pilot"
ASSET_VERSION_CHANNEL_STABLE = "stable"
ASSET_VERSION_CHANNELS = frozenset(
    {
        ASSET_VERSION_CHANNEL_UNPUBLISHED,
        ASSET_VERSION_CHANNEL_PILOT,
        ASSET_VERSION_CHANNEL_STABLE,
    }
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_assets_org_slug"),
        Index("ix_assets_organization_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    owner_subject_id: Mapped[str] = mapped_column(String(80), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ASSET_VISIBILITY_INTERNAL,
    )
    lifecycle: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ASSET_LIFECYCLE_ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class AssetVersion(Base):
    __tablename__ = "asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_asset_versions_asset_version"),
        Index("ix_asset_versions_organization_id", "organization_id"),
        Index("ix_asset_versions_asset_id", "asset_id"),
        Index("ix_asset_versions_status", "status"),
        Index(
            "uq_asset_versions_published_channel",
            "asset_id",
            "channel",
            unique=True,
            sqlite_where=text("status = 'published'"),
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assets.id"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_key: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ASSET_VERSION_STATUS_DRAFT,
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
