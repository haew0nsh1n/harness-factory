from datetime import UTC, datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from web.api.validation import require_sha256_digest
from web.api.designs.models import (
    APPROVAL_DECISION_APPROVED,
    APPROVAL_DECISION_REJECTED,
    HarnessDesign,
)


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class HarnessDesignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_digest: str | None = Field(default=None, min_length=64, max_length=64)
    customer_id: str
    name: str
    profile: dict[str, Any]
    workflow: dict[str, Any]
    scenarios: dict[str, Any]
    catalog: dict[str, Any]

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return require_sha256_digest(value, "expected_digest")


class ValidationFinding(BaseModel):
    field: str
    code: str
    message: str


class DesignReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_digest: str = Field(min_length=64, max_length=64)
    decision: Literal[
        APPROVAL_DECISION_APPROVED,
        APPROVAL_DECISION_REJECTED,
    ]

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str) -> str:
        return require_sha256_digest(value, "expected_digest")


class HarnessDesignResponse(BaseModel):
    id: str
    organization_id: str
    customer_id: str
    name: str
    profile: dict[str, Any]
    workflow: dict[str, Any]
    scenarios: dict[str, Any]
    catalog: dict[str, Any]
    revision: int
    digest: str
    status: str
    validation_findings: list[ValidationFinding] | None
    created_by: str
    created_at: datetime
    updated_at: datetime


def to_design_response(design: HarnessDesign) -> HarnessDesignResponse:
    return HarnessDesignResponse(
        id=design.id,
        organization_id=design.organization_id,
        customer_id=design.customer_id,
        name=design.name,
        profile=design.profile_json,
        workflow=design.workflow_json,
        scenarios=design.scenarios_json,
        catalog=design.catalog_json,
        revision=design.revision,
        digest=design.digest,
        status=design.status,
        validation_findings=design.validation_findings_json,
        created_by=design.created_by,
        created_at=_normalize_timestamp(design.created_at),
        updated_at=_normalize_timestamp(design.updated_at),
    )
