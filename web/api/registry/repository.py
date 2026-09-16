from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from web.api.builds.models import BUILD_STATUS_SUCCEEDED, BuildJob
from web.api.designs.models import (
    APPROVAL_SUBJECT_TYPE_ASSET_VERSION,
    Approval,
    HarnessDesign,
)
from web.api.registry.models import (
    ASSET_VERSION_CHANNEL_UNPUBLISHED,
    ASSET_VERSION_STATUS_PUBLISHED,
    Asset,
    AssetVersion,
)
from web.api.registry.schemas import AssetCreate


def utcnow() -> datetime:
    return datetime.now(UTC)


class RegistryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_asset(
        self,
        organization_id: str,
        request: AssetCreate,
    ) -> Asset:
        with self._session.begin_nested():
            asset = Asset(
                id=str(uuid4()),
                organization_id=organization_id,
                kind=request.type,
                slug=request.slug,
                name=request.name,
                language=request.language,
                description=request.description,
                owner_subject_id=request.owner_subject_id,
            )
            self._session.add(asset)
            self._session.flush()
        return asset

    def get_asset(self, organization_id: str, asset_id: str) -> Asset | None:
        return self._session.scalar(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.id == asset_id,
            )
        )

    def get_asset_by_slug(self, organization_id: str, slug: str) -> Asset | None:
        return self._session.scalar(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.slug == slug,
            )
        )

    def get_version_by_number(
        self,
        organization_id: str,
        asset_id: str,
        version: str,
    ) -> AssetVersion | None:
        return self._session.scalar(
            select(AssetVersion).where(
                AssetVersion.organization_id == organization_id,
                AssetVersion.asset_id == asset_id,
                AssetVersion.version == version,
            )
        )

    def create_version(
        self,
        organization_id: str,
        asset_id: str,
        version: str,
        manifest: dict[str, object],
        digest: str,
        artifact_key: str,
        artifact_digest: str,
        created_by: str,
    ) -> AssetVersion:
        with self._session.begin_nested():
            asset_version = AssetVersion(
                id=str(uuid4()),
                organization_id=organization_id,
                asset_id=asset_id,
                version=version,
                manifest_json=manifest,
                digest=digest,
                artifact_key=artifact_key,
                artifact_digest=artifact_digest,
                status="draft",
                channel=ASSET_VERSION_CHANNEL_UNPUBLISHED,
                created_by=created_by,
            )
            self._session.add(asset_version)
            self._session.flush()
        return asset_version

    def get_version(self, organization_id: str, version_id: str) -> AssetVersion | None:
        return self._session.scalar(
            select(AssetVersion).where(
                AssetVersion.organization_id == organization_id,
                AssetVersion.id == version_id,
            )
        )

    def get_design(self, organization_id: str, design_id: str) -> HarnessDesign | None:
        return self._session.scalar(
            select(HarnessDesign).where(
                HarnessDesign.organization_id == organization_id,
                HarnessDesign.id == design_id,
            )
        )

    def get_successful_build(
        self,
        organization_id: str,
        design_id: str,
        design_digest: str,
    ) -> BuildJob | None:
        return self._session.scalar(
            select(BuildJob)
            .where(
                BuildJob.organization_id == organization_id,
                BuildJob.design_id == design_id,
                BuildJob.design_digest == design_digest,
                BuildJob.status == BUILD_STATUS_SUCCEEDED,
            )
            .order_by(BuildJob.updated_at.desc(), BuildJob.id.desc())
            .limit(1)
        )

    def create_version_approval(
        self,
        organization_id: str,
        version_id: str,
        version_digest: str,
        decision: str,
        actor_id: str,
    ) -> Approval:
        approval = Approval(
            id=str(uuid4()),
            organization_id=organization_id,
            subject_type=APPROVAL_SUBJECT_TYPE_ASSET_VERSION,
            subject_id=version_id,
            subject_digest=version_digest,
            decision=decision,
            actor_subject_id=actor_id,
        )
        self._session.add(approval)
        self._session.flush()
        return approval

    def latest_version_approval(
        self,
        organization_id: str,
        version_id: str,
    ) -> Approval | None:
        return self._session.scalar(
            select(Approval)
            .where(
                Approval.organization_id == organization_id,
                Approval.subject_type == APPROVAL_SUBJECT_TYPE_ASSET_VERSION,
                Approval.subject_id == version_id,
            )
            .order_by(Approval.created_at.desc(), Approval.id.desc())
            .limit(1)
        )

    def list_assets_with_versions(
        self,
        organization_id: str,
        *,
        kind: str | None,
        query: str | None,
        channel: str | None,
        include_unpublished: bool,
    ) -> Sequence[tuple[Asset, AssetVersion | None]]:
        statement: Select[tuple[Asset, AssetVersion | None]] = select(Asset, AssetVersion)
        join_conditions = [
            AssetVersion.organization_id == organization_id,
            AssetVersion.asset_id == Asset.id,
        ]
        if not include_unpublished:
            join_conditions.append(
                AssetVersion.status == ASSET_VERSION_STATUS_PUBLISHED
            )
        if channel is not None:
            join_conditions.append(AssetVersion.channel == channel)
        if include_unpublished:
            statement = statement.outerjoin(AssetVersion, and_(*join_conditions))
        else:
            statement = statement.join(AssetVersion, and_(*join_conditions))
        statement = statement.where(Asset.organization_id == organization_id)
        if kind is not None:
            statement = statement.where(Asset.kind == kind)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    Asset.slug.ilike(pattern),
                    Asset.name.ilike(pattern),
                    Asset.description.ilike(pattern),
                )
            )
        return self._session.execute(
            statement.order_by(
                Asset.slug.asc(),
                Asset.id.asc(),
                AssetVersion.created_at.desc(),
                AssetVersion.id.desc(),
            )
        ).all()

    def list_versions_for_asset(
        self,
        organization_id: str,
        asset_id: str,
        *,
        channel: str | None = None,
        installable_only: bool,
    ) -> Sequence[AssetVersion]:
        statement: Select[tuple[AssetVersion]] = select(AssetVersion).where(
            AssetVersion.organization_id == organization_id,
            AssetVersion.asset_id == asset_id,
        )
        if installable_only:
            statement = statement.where(
                AssetVersion.status == ASSET_VERSION_STATUS_PUBLISHED
            )
        if channel is not None:
            statement = statement.where(AssetVersion.channel == channel)
        return self._session.scalars(
            statement.order_by(AssetVersion.created_at.desc(), AssetVersion.id.desc())
        ).all()

    def list_published_versions_in_channel(
        self,
        organization_id: str,
        asset_id: str,
        channel: str,
        *,
        exclude_version_id: str | None = None,
    ) -> Sequence[AssetVersion]:
        statement: Select[tuple[AssetVersion]] = select(AssetVersion).where(
            AssetVersion.organization_id == organization_id,
            AssetVersion.asset_id == asset_id,
            AssetVersion.channel == channel,
            AssetVersion.status == ASSET_VERSION_STATUS_PUBLISHED,
        )
        if exclude_version_id is not None:
            statement = statement.where(AssetVersion.id != exclude_version_id)
        return self._session.scalars(
            statement.order_by(AssetVersion.created_at.asc(), AssetVersion.id.asc())
        ).all()

    def flush(self) -> None:
        self._session.flush()
