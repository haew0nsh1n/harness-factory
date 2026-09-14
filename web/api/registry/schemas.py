from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from web.api.registry.models import Asset, AssetVersion
from web.api.validation import SHA256_HEX_RE, require_sha256_digest

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = SHA256_HEX_RE
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["workflow"]
    slug: str
    name: str
    description: str
    owner_subject_id: str

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if not SLUG_RE.fullmatch(value):
            raise ValueError("slug must be a lowercase hyphen identifier")
        return value


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    design_id: str
    design_digest: str = Field(min_length=64, max_length=64)
    version: str

    @field_validator("design_digest")
    @classmethod
    def validate_design_digest(cls, value: str) -> str:
        return require_sha256_digest(value, "design_digest")

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("version must be MAJOR.MINOR.PATCH")
        return value


class VersionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_digest: str = Field(min_length=64, max_length=64)
    decision: Literal["approved", "rejected"]

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str) -> str:
        return require_sha256_digest(value, "expected_digest")


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_digest: str = Field(min_length=64, max_length=64)
    channel: Literal["pilot", "stable"]

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str) -> str:
        return require_sha256_digest(value, "expected_digest")


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_digest: str = Field(min_length=64, max_length=64)

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str) -> str:
        return require_sha256_digest(value, "expected_digest")


class VersionSummaryResponse(BaseModel):
    id: str
    version: str
    digest: str
    status: str
    channel: str
    artifact_sha256: str


class AssetSummaryResponse(BaseModel):
    id: str
    type: str
    slug: str
    name: str
    description: str | None
    versions: list[VersionSummaryResponse]


class AssetResponse(BaseModel):
    id: str
    organization_id: str
    type: str
    slug: str
    name: str
    description: str | None
    owner_subject_id: str
    visibility: str
    lifecycle: str
    versions: list[VersionSummaryResponse]


class AssetVersionResponse(BaseModel):
    id: str
    organization_id: str
    asset_id: str
    version: str
    digest: str
    status: str
    channel: str
    artifact_sha256: str
    manifest: dict[str, Any]


def to_version_summary_response(version: AssetVersion) -> VersionSummaryResponse:
    return VersionSummaryResponse(
        id=version.id,
        version=version.version,
        digest=version.digest,
        status=version.status,
        channel=version.channel,
        artifact_sha256=version.artifact_digest,
    )


def to_asset_summary_response(
    asset: Asset, versions: list[AssetVersion]
) -> AssetSummaryResponse:
    return AssetSummaryResponse(
        id=asset.id,
        type=asset.kind,
        slug=asset.slug,
        name=asset.name,
        description=asset.description,
        versions=[to_version_summary_response(version) for version in versions],
    )


def to_asset_response(asset: Asset, versions: list[AssetVersion]) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        organization_id=asset.organization_id,
        type=asset.kind,
        slug=asset.slug,
        name=asset.name,
        description=asset.description,
        owner_subject_id=asset.owner_subject_id,
        visibility=asset.visibility,
        lifecycle=asset.lifecycle,
        versions=[to_version_summary_response(version) for version in versions],
    )


def to_asset_version_response(version: AssetVersion) -> AssetVersionResponse:
    return AssetVersionResponse(
        id=version.id,
        organization_id=version.organization_id,
        asset_id=version.asset_id,
        version=version.version,
        digest=version.digest,
        status=version.status,
        channel=version.channel,
        artifact_sha256=version.artifact_digest,
        manifest=version.manifest_json,
    )
