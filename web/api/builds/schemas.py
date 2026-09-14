from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from web.api.builds.models import BuildJob
from web.api.validation import require_sha256_digest


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class BuildSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_digest: str = Field(min_length=64, max_length=64)

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str) -> str:
        return require_sha256_digest(value, "expected_digest")


class BuildJobResponse(BaseModel):
    id: str
    organization_id: str
    design_id: str
    design_digest: str
    status: str
    attempts: int
    artifact_key: str | None
    artifact_digest: str | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


def to_build_response(job: BuildJob) -> BuildJobResponse:
    return BuildJobResponse(
        id=job.id,
        organization_id=job.organization_id,
        design_id=job.design_id,
        design_digest=job.design_digest,
        status=job.status,
        attempts=job.attempts,
        artifact_key=job.artifact_key,
        artifact_digest=job.artifact_digest,
        error_code=job.error_code,
        created_at=_normalize_timestamp(job.created_at),
        started_at=_normalize_timestamp(job.started_at),
        finished_at=_normalize_timestamp(job.finished_at),
        updated_at=_normalize_timestamp(job.updated_at),
    )
