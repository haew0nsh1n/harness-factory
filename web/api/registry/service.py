from __future__ import annotations

import hashlib
from contextlib import closing
from dataclasses import dataclass
from hmac import compare_digest
from sqlalchemy.exc import IntegrityError

from web.api.audit.service import AuditService
from web.api.builds.models import BuildJob
from web.api.builds.storage import ArtifactStorage, ArtifactStorageError
from web.api.designs.digest import canonical_json_bytes
from web.api.designs.models import APPROVAL_DECISION_APPROVED, DESIGN_STATUS_BUILT
from web.api.registry.models import (
    ASSET_VERSION_STATUS_APPROVED,
    ASSET_VERSION_STATUS_DEPRECATED,
    ASSET_VERSION_STATUS_DRAFT,
    ASSET_VERSION_STATUS_PUBLISHED,
    ASSET_VERSION_STATUS_REVOKED,
    Asset,
    AssetVersion,
)
from web.api.registry.repository import RegistryRepository
from web.api.registry.schemas import AssetCreate, PublishRequest, VersionCreate


@dataclass(frozen=True)
class AssetSlugConflict(Exception):
    message: str = "asset slug already exists"


@dataclass(frozen=True)
class AssetVersionConflict(Exception):
    message: str = "asset version already exists"


@dataclass(frozen=True)
class InvalidRegistryLifecycle(Exception):
    message: str


@dataclass(frozen=True)
class StaleRegistryDigest(Exception):
    message: str


@dataclass(frozen=True)
class ArtifactVerificationFailed(Exception):
    message: str
    code: str


class RegistryService:
    def __init__(
        self,
        repository: RegistryRepository,
        audit_service: AuditService,
        storage: ArtifactStorage,
    ) -> None:
        self._repository = repository
        self._audit_service = audit_service
        self._storage = storage

    def create_workflow_asset(
        self,
        organization_id: str,
        actor_id: str,
        request: AssetCreate,
    ) -> Asset:
        try:
            asset = self._repository.create_asset(organization_id, request)
        except IntegrityError as exc:
            if self._is_asset_slug_conflict(exc):
                raise AssetSlugConflict() from exc
            raise
        self._audit_service.append(
            organization_id=organization_id,
            actor_id=actor_id,
            action="registry.asset.created",
            resource_type="asset",
            resource_id=asset.id,
            summary={
                "asset_type": asset.kind,
                "asset_slug": asset.slug,
                "owner_subject_id": asset.owner_subject_id,
            },
        )
        return asset

    def create_workflow_version(
        self,
        organization_id: str,
        actor_id: str,
        asset_id: str,
        request: VersionCreate,
    ) -> AssetVersion | None:
        asset = self._repository.get_asset(organization_id, asset_id)
        if asset is None:
            return None
        design = self._repository.get_design(organization_id, request.design_id)
        if design is None:
            raise InvalidRegistryLifecycle("built design artifact required")
        if not compare_digest(design.digest, request.design_digest):
            raise StaleRegistryDigest("design digest is stale")
        if design.status != DESIGN_STATUS_BUILT:
            raise InvalidRegistryLifecycle("built design artifact required")
        build = self._repository.get_successful_build(
            organization_id,
            request.design_id,
            request.design_digest,
        )
        self._require_built_artifact(build)
        self._verify_built_artifact(build)
        assert build is not None

        manifest = self._build_manifest(asset, request.version, request.design_digest, build)
        digest = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
        try:
            version = self._repository.create_version(
                organization_id=organization_id,
                asset_id=asset.id,
                version=request.version,
                manifest=manifest,
                digest=digest,
                artifact_key=build.artifact_key,
                artifact_digest=build.artifact_digest,
                created_by=actor_id,
            )
        except IntegrityError as exc:
            if self._is_asset_version_conflict(exc):
                raise AssetVersionConflict() from exc
            raise
        self._audit_service.append(
            organization_id=organization_id,
            actor_id=actor_id,
            action="registry.version.created",
            resource_type="asset-version",
            resource_id=version.id,
            summary={
                "asset_slug": asset.slug,
                "version": version.version,
                "version_digest": version.digest,
                "design_digest": request.design_digest,
            },
        )
        return version

    def review_version(
        self,
        organization_id: str,
        actor_id: str,
        version_id: str,
        expected_digest: str,
        decision: str,
    ) -> AssetVersion | None:
        version = self._repository.get_version(organization_id, version_id)
        if version is None:
            return None
        if version.status not in {ASSET_VERSION_STATUS_DRAFT, ASSET_VERSION_STATUS_APPROVED}:
            raise InvalidRegistryLifecycle("version lifecycle does not allow review")
        if not compare_digest(version.digest, expected_digest):
            raise StaleRegistryDigest("version digest is stale")

        self._repository.create_version_approval(
            organization_id=organization_id,
            version_id=version.id,
            version_digest=version.digest,
            decision=decision,
            actor_id=actor_id,
        )
        version.status = (
            ASSET_VERSION_STATUS_APPROVED
            if decision == APPROVAL_DECISION_APPROVED
            else ASSET_VERSION_STATUS_DRAFT
        )
        self._audit_service.append(
            organization_id=organization_id,
            actor_id=actor_id,
            action="registry.version.reviewed",
            resource_type="asset-version",
            resource_id=version.id,
            summary={
                "decision": decision,
                "version_digest": version.digest,
                "resulting_status": version.status,
            },
        )
        return version

    def publish_workflow_version(
        self,
        organization_id: str,
        actor_id: str,
        version_id: str,
        request: PublishRequest,
    ) -> AssetVersion | None:
        version = self._repository.get_version(organization_id, version_id)
        if version is None:
            return None
        if version.status != ASSET_VERSION_STATUS_APPROVED:
            raise InvalidRegistryLifecycle("version lifecycle does not allow publish")
        if not compare_digest(version.digest, request.expected_digest):
            raise StaleRegistryDigest("version digest is stale")
        approval = self._repository.latest_version_approval(organization_id, version.id)
        if approval is None or approval.decision != APPROVAL_DECISION_APPROVED:
            raise InvalidRegistryLifecycle("version lifecycle does not allow publish")
        if not compare_digest(approval.subject_digest, version.digest):
            raise InvalidRegistryLifecycle("version lifecycle does not allow publish")

        self._demote_previously_published(
            organization_id=organization_id,
            actor_id=actor_id,
            asset_id=version.asset_id,
            channel=request.channel,
            promoted_version_id=version.id,
        )
        version.status = ASSET_VERSION_STATUS_PUBLISHED
        version.channel = request.channel
        self._repository.flush()
        self._audit_service.append(
            organization_id=organization_id,
            actor_id=actor_id,
            action="registry.version.published",
            resource_type="asset-version",
            resource_id=version.id,
            summary={
                "channel": version.channel,
                "version_digest": version.digest,
                "version": version.version,
            },
        )
        return version

    def revoke_version(
        self,
        organization_id: str,
        actor_id: str,
        version_id: str,
        expected_digest: str,
    ) -> AssetVersion | None:
        version = self._repository.get_version(organization_id, version_id)
        if version is None:
            return None
        if version.status != ASSET_VERSION_STATUS_PUBLISHED:
            raise InvalidRegistryLifecycle("version lifecycle does not allow revoke")
        if not compare_digest(version.digest, expected_digest):
            raise StaleRegistryDigest("version digest is stale")
        version.status = ASSET_VERSION_STATUS_REVOKED
        self._audit_service.append(
            organization_id=organization_id,
            actor_id=actor_id,
            action="registry.version.revoked",
            resource_type="asset-version",
            resource_id=version.id,
            summary={
                "channel": version.channel,
                "version_digest": version.digest,
                "version": version.version,
            },
        )
        return version

    def search_assets(
        self,
        organization_id: str,
        *,
        kind: str | None,
        query: str | None,
        channel: str | None,
        include_unpublished: bool,
    ) -> list[tuple[Asset, list[AssetVersion]]]:
        rows = self._repository.list_assets_with_versions(
            organization_id,
            kind=kind,
            query=query,
            channel=channel,
            include_unpublished=include_unpublished,
        )
        items: list[tuple[Asset, list[AssetVersion]]] = []
        current_asset: Asset | None = None
        current_versions: list[AssetVersion] = []

        def flush_current() -> None:
            nonlocal current_asset, current_versions
            if current_asset is None:
                return
            current_versions.sort(key=self._version_sort_key, reverse=True)
            versions = current_versions
            if not include_unpublished and channel is not None and versions:
                versions = versions[:1]
            if versions or include_unpublished:
                items.append((current_asset, versions))

        for asset, version in rows:
            if current_asset is None or asset.id != current_asset.id:
                flush_current()
                current_asset = asset
                current_versions = []
            if version is not None:
                current_versions.append(version)

        flush_current()
        return items

    def get_asset_detail(
        self,
        organization_id: str,
        slug: str,
        *,
        include_unpublished: bool,
    ) -> tuple[Asset, list[AssetVersion]] | None:
        asset = self._repository.get_asset_by_slug(organization_id, slug)
        if asset is None:
            return None
        versions = list(
            self._repository.list_versions_for_asset(
                organization_id,
                asset.id,
                installable_only=not include_unpublished,
            )
        )
        versions.sort(key=self._version_sort_key, reverse=True)
        if not versions and not include_unpublished:
            return None
        return asset, versions

    def get_manifest(
        self,
        organization_id: str,
        version_id: str,
        *,
        include_unpublished: bool,
    ) -> dict[str, object] | None:
        version = self._repository.get_version(organization_id, version_id)
        if version is None:
            return None
        if not include_unpublished and version.status != ASSET_VERSION_STATUS_PUBLISHED:
            return None
        return version.manifest_json

    def _demote_previously_published(
        self,
        *,
        organization_id: str,
        actor_id: str,
        asset_id: str,
        channel: str,
        promoted_version_id: str,
    ) -> None:
        for previous in self._repository.list_published_versions_in_channel(
            organization_id,
            asset_id,
            channel,
            exclude_version_id=promoted_version_id,
        ):
            previous.status = ASSET_VERSION_STATUS_DEPRECATED
            self._audit_service.append(
                organization_id=organization_id,
                actor_id=actor_id,
                action="registry.version.deprecated",
                resource_type="asset-version",
                resource_id=previous.id,
                summary={
                    "channel": previous.channel,
                    "version_digest": previous.digest,
                    "version": previous.version,
                    "superseded_by_version_id": promoted_version_id,
                },
            )
        self._repository.flush()

    @staticmethod
    def _require_built_artifact(build: BuildJob | None) -> None:
        if (
            build is None
            or build.artifact_key is None
            or build.artifact_digest is None
        ):
            raise InvalidRegistryLifecycle("built design artifact required")

    def _verify_built_artifact(self, build: BuildJob | None) -> None:
        self._require_built_artifact(build)
        assert build is not None
        assert build.artifact_key is not None
        assert build.artifact_digest is not None
        try:
            with closing(self._storage.open(build.artifact_key)) as stream:
                artifact_digest = self._hash_stream(stream)
        except (ArtifactStorageError, OSError):
            raise ArtifactVerificationFailed(
                message="built design artifact is unavailable",
                code="artifact_unavailable",
            ) from None
        if not compare_digest(artifact_digest, build.artifact_digest):
            raise ArtifactVerificationFailed(
                message="built design artifact failed integrity check",
                code="artifact_corrupted",
            )

    @staticmethod
    def _build_manifest(
        asset: Asset,
        version: str,
        design_digest: str,
        build: BuildJob,
    ) -> dict[str, object]:
        assert build.artifact_key is not None
        assert build.artifact_digest is not None
        return {
            "schema_version": 1,
            "asset": {
                "type": asset.kind,
                "slug": asset.slug,
            },
            "version": version,
            "runtime": "copilot-cli",
            "design_digest": design_digest,
            "artifact": {
                "sha256": build.artifact_digest,
                "key": build.artifact_key,
            },
            "dependencies": [],
        }

    @staticmethod
    def _version_sort_key(version: AssetVersion) -> tuple[int, int, int]:
        major, minor, patch = version.version.split(".")
        return (int(major), int(minor), int(patch))

    @staticmethod
    def _hash_stream(stream) -> str:
        hasher = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
        return hasher.hexdigest()

    def _is_asset_slug_conflict(self, error: IntegrityError) -> bool:
        return self._is_expected_unique_violation(
            error,
            constraint_name="uq_assets_org_slug",
            sqlite_columns=("assets.organization_id", "assets.slug"),
        )

    def _is_asset_version_conflict(self, error: IntegrityError) -> bool:
        return self._is_expected_unique_violation(
            error,
            constraint_name="uq_asset_versions_asset_version",
            sqlite_columns=("asset_versions.asset_id", "asset_versions.version"),
        )

    @staticmethod
    def _is_expected_unique_violation(
        error: IntegrityError,
        *,
        constraint_name: str,
        sqlite_columns: tuple[str, ...],
    ) -> bool:
        original = getattr(error, "orig", None)
        if original is None:
            return False
        diagnostic = getattr(original, "diag", None)
        if diagnostic is not None and getattr(diagnostic, "constraint_name", None) == constraint_name:
            return True
        if getattr(original, "constraint_name", None) == constraint_name:
            return True
        message = str(original)
        sqlite_signature = f"UNIQUE constraint failed: {', '.join(sqlite_columns)}"
        return sqlite_signature in message
