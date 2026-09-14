from dataclasses import dataclass
from hmac import compare_digest

from harness_factory import load_json, validate, validate_scenarios
from harness_factory.errors import EvaluationError, ValidationError

from web.api.audit.service import AuditService
from web.api.config import Settings
from web.api.designs.digest import canonical_json_bytes, design_digest
from web.api.designs.models import (
    APPROVAL_DECISION_APPROVED,
    DESIGN_STATUS_APPROVED,
    DESIGN_STATUS_DRAFT,
    DESIGN_STATUS_VALIDATED,
    HarnessDesign,
)
from web.api.designs.repository import HarnessDesignRepository
from web.api.designs.schemas import HarnessDesignRequest


@dataclass(frozen=True)
class DesignValidationFailure(Exception):
    finding: dict[str, str]
    design: HarnessDesign | None = None


@dataclass(frozen=True)
class InvalidDesignLifecycle(Exception):
    message: str = "design lifecycle does not allow review"


@dataclass(frozen=True)
class StaleDesignDigest(Exception):
    message: str = "design digest is stale"


class DesignService:
    def __init__(
        self,
        repository: HarnessDesignRepository,
        settings: Settings,
        audit_service: AuditService,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._audit_service = audit_service

    def create(
        self,
        organization_id: str,
        actor_id: str,
        request: HarnessDesignRequest,
    ):
        return self._repository.create(organization_id, actor_id, request)

    def list(self, organization_id: str):
        return self._repository.list(organization_id)

    def get(self, organization_id: str, design_id: str):
        return self._repository.get(organization_id, design_id)

    def replace_draft(
        self,
        organization_id: str,
        design_id: str,
        request: HarnessDesignRequest,
    ):
        return self._repository.replace_draft(organization_id, design_id, request)

    def validate(self, organization_id: str, design_id: str):
        design = self._repository.get(organization_id, design_id)
        if design is None:
            return None

        current_digest = design_digest(
            design.profile_json,
            design.workflow_json,
            design.scenarios_json,
            design.catalog_json,
        )
        authoritative_catalog = self._load_authoritative_catalog()

        try:
            self._require_matching_catalog_snapshot(
                design.catalog_json,
                authoritative_catalog,
            )
            validate(
                design.profile_json,
                design.workflow_json,
                authoritative_catalog,
                self._settings.catalog_root,
            )
            validate_scenarios(design.scenarios_json, design.workflow_json)
        except DesignValidationFailure as exc:
            saved = self._repository.save_validation(
                organization_id,
                design_id,
                current_digest,
                False,
                exc.finding,
            )
            if saved is None:
                return None
            raise DesignValidationFailure(exc.finding, saved) from None
        except (ValidationError, EvaluationError) as exc:
            finding = self._normalized_finding(str(exc))
            saved = self._repository.save_validation(
                organization_id,
                design_id,
                current_digest,
                False,
                finding,
            )
            if saved is None:
                return None
            raise DesignValidationFailure(finding, saved) from None

        return self._repository.save_validation(
            organization_id,
            design_id,
            current_digest,
            True,
            None,
        )

    def approve_design(
        self,
        organization_id: str,
        actor_id: str,
        design_id: str,
        expected_digest: str,
        decision: str,
    ):
        design = self._repository.get(organization_id, design_id)
        if design is None:
            return None
        if design.status != DESIGN_STATUS_VALIDATED:
            raise InvalidDesignLifecycle()
        if not compare_digest(design.digest, expected_digest):
            raise StaleDesignDigest()

        self._repository.create_approval(
            organization_id=organization_id,
            design_id=design_id,
            digest=design.digest,
            decision=decision,
            actor_id=actor_id,
        )
        design.status = (
            DESIGN_STATUS_APPROVED
            if decision == APPROVAL_DECISION_APPROVED
            else DESIGN_STATUS_DRAFT
        )
        self._audit_service.append(
            organization_id=organization_id,
            actor_id=actor_id,
            action="design.reviewed",
            resource_type="harness-design",
            resource_id=design_id,
            summary={
                "decision": decision,
                "design_digest": design.digest,
                "resulting_status": design.status,
                "revision": design.revision,
            },
        )
        return design

    def _load_authoritative_catalog(self) -> dict[str, object]:
        return load_json(self._settings.catalog_root / "catalog.json")

    def _require_matching_catalog_snapshot(
        self,
        request_catalog: dict[str, object],
        authoritative_catalog: dict[str, object],
    ) -> None:
        if canonical_json_bytes(request_catalog) != canonical_json_bytes(
            authoritative_catalog
        ):
            raise DesignValidationFailure(
                self._normalized_finding(
                    "validation: catalog: request snapshot does not match server catalog"
                )
            )

    @staticmethod
    def _normalized_finding(message: str) -> dict[str, str]:
        return {
            "field": "contract",
            "code": "invalid-design",
            "message": message,
        }
