from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from harness_factory import validate, validate_scenarios
from harness_factory.errors import EvaluationError, ValidationError
from web.api.config import Settings
from web.api.designs.digest import canonical_json_bytes, design_digest
from web.api.designs.models import HarnessDesign
from web.api.designs.repository import HarnessDesignRepository, StaleDraftDigest
from web.api.designs.schemas import HarnessDesignRequest
from web.api.identity.models import Actor

from .catalog import AuthoritativeCatalogService, validate_catalog_references
from .errors import InterviewModelError
from .model import ConfirmedEvidence, InterviewContext, InterviewModel, InterviewTurn
from .models import (
    InterviewOperation,
    InterviewProposal,
    InterviewSession,
    InterviewTurn as StoredTurn,
)
from .operations import (
    OperationClaimConflict,
    advance_session_without_live_operation,
    claim_session_operation,
    reclaim_operation,
)
from .schemas import (
    ApplyProposalRequest,
    DraftCandidate,
    InterviewProposalDetailResponse,
    ProposalRequest,
    WORKFLOW_ID_PATTERN,
)
from .service import (
    InterviewConflict,
    InterviewInferenceFailure,
    InterviewNotFound,
    InterviewTargetNotFound,
)
from .stages import stored_stages


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _sha256(value: object) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class ProposalService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        model: InterviewModel,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._model = model
        self._catalog = AuthoritativeCatalogService(settings.catalog_root)

    def catalog(self) -> dict[str, object]:
        return self._catalog.load()

    def get(
        self,
        actor: Actor,
        session_id: str,
        proposal_id: str,
    ) -> InterviewProposalDetailResponse:
        now = _utcnow()
        with self._session_factory() as db:
            self._required_session(db, actor.organization_id, session_id, now)
            proposal = db.scalar(
                select(InterviewProposal).where(
                    InterviewProposal.organization_id == actor.organization_id,
                    InterviewProposal.session_id == session_id,
                    InterviewProposal.id == proposal_id,
                )
            )
            if proposal is None:
                raise InterviewNotFound()
            self._require_untampered_proposal(proposal)
            return self._response(proposal)

    async def generate(
        self,
        actor: Actor,
        session_id: str,
        request: ProposalRequest,
    ) -> tuple[InterviewProposalDetailResponse, bool]:
        request_id = str(request.request_id)
        input_digest = _sha256(
            {
                "kind": "proposal",
                "expected_revision": request.expected_revision,
            }
        )
        token, context, existing = self._claim_generation(
            actor,
            session_id,
            request,
            request_id,
            input_digest,
        )
        if existing is not None:
            return existing, False

        catalog = self._catalog.load()
        try:
            raw_candidate = await self._model.propose_design(context, catalog)
            candidate = DraftCandidate.model_validate(raw_candidate)
            candidate_stages = tuple(item.stage for item in candidate.profile.sdlc)
            if candidate_stages != context.selected_stages:
                raise InterviewModelError(
                    "llm_invalid_result",
                    "The model returned SDLC stages outside the selected scope.",
                )
            validate_catalog_references(candidate, catalog)
        except (InterviewModelError, PydanticValidationError) as exc:
            code = (
                exc.code
                if isinstance(exc, InterviewModelError)
                else "llm_invalid_result"
            )
            recorded = self._record_failure(
                actor.organization_id,
                session_id,
                request_id,
                token,
                code,
            )
            if not recorded:
                raise InterviewConflict(
                    "operation_superseded",
                    "interview operation was superseded",
                ) from None
            raise InterviewInferenceFailure(code) from None

        proposal = self._finish_generation(
            actor,
            session_id,
            request_id,
            token,
            request.expected_revision,
            candidate,
            catalog,
        )
        return proposal, True

    def apply(
        self,
        actor: Actor,
        session_id: str,
        request: ApplyProposalRequest,
    ) -> HarnessDesign:
        now = _utcnow()
        apply_digest = _sha256(
            {
                **request.model_dump(mode="json"),
                "actor_id": actor.subject_id,
            }
        )
        with self._session_factory.begin() as db:
            session = self._required_session(
                db, actor.organization_id, session_id, now
            )
            proposal = db.scalar(
                select(InterviewProposal).where(
                    InterviewProposal.organization_id == actor.organization_id,
                    InterviewProposal.session_id == session_id,
                    InterviewProposal.id == str(request.proposal_id),
                )
            )
            if proposal is None:
                raise InterviewNotFound()
            if proposal.status == "accepted":
                return self._accepted_duplicate(
                    db, actor, proposal, apply_digest
                )

            candidate = proposal.candidate_json
            profile = self._required_document(candidate, "profile")
            workflow = self._required_document(candidate, "workflow")
            scenarios = self._required_document(candidate, "scenarios")
            catalog = self._required_document(candidate, "catalog")
            self._require_untampered_proposal(proposal)
            if not compare_digest(
                proposal.digest, request.expected_proposal_digest
            ):
                raise InterviewConflict(
                    "stale_proposal", "proposal digest is stale"
                )
            if (
                session.revision != request.expected_revision
                or proposal.revision != request.expected_revision
                or session.status != "completed"
            ):
                raise InterviewConflict(
                    "stale_revision", "interview revision is stale"
                )
            if session.selected_scope is None:
                raise InterviewConflict(
                    "scope_not_selected",
                    "workflow scope must be selected before applying",
                )
            if workflow.get("id") != session.selected_scope:
                raise InterviewConflict(
                    "scope_mismatch",
                    "proposal does not match the selected workflow scope",
                )
            if "approved" in workflow:
                raise InterviewConflict(
                    "stale_proposal", "proposal contains forbidden approval data"
                )

            applied_workflow = {
                **workflow,
                "approved": {
                    "by": actor.subject_id,
                    "at": now.isoformat(),
                },
            }
            design_request = HarnessDesignRequest(
                expected_digest=request.expected_design_digest,
                customer_id=str(profile["customer_id"]),
                name=str(profile["name"]),
                language=request.language,
                profile=profile,
                workflow=applied_workflow,
                scenarios=scenarios,
                catalog=catalog,
            )
            try:
                self._advance_session_for_apply(
                    db,
                    session,
                    base_revision=request.expected_revision,
                    now=now,
                )
            except OperationClaimConflict:
                raise InterviewConflict(
                    "interview_busy", "interview operation is busy"
                ) from None

            repository = HarnessDesignRepository(db)
            if request.design_id is None:
                design = repository.create(
                    actor.organization_id,
                    actor.subject_id,
                    design_request,
                )
            else:
                try:
                    design = repository.replace_draft(
                        actor.organization_id,
                        str(request.design_id),
                        design_request,
                    )
                except StaleDraftDigest:
                    raise InterviewConflict(
                        "stale_digest", "design digest is stale"
                    ) from None
                if design is None:
                    raise InterviewTargetNotFound()
                repository.clear_approvals(
                    actor.organization_id,
                    str(request.design_id),
                )
            design.validation_findings_json = [
                finding
                for finding in proposal.findings_json
                if finding["code"] != "scope-confirmation-required"
            ]

            accepted = db.execute(
                update(InterviewProposal)
                .where(
                    InterviewProposal.organization_id == actor.organization_id,
                    InterviewProposal.session_id == session_id,
                    InterviewProposal.id == proposal.id,
                    InterviewProposal.revision == request.expected_revision,
                    InterviewProposal.digest == request.expected_proposal_digest,
                    InterviewProposal.status == "draft",
                )
                .execution_options(synchronize_session=False)
                .values(
                    status="accepted",
                    apply_digest=apply_digest,
                    accepted_design_id=design.id,
                    accepted_design_digest=design.digest,
                    accepted_by=actor.subject_id,
                    accepted_at=now,
                    updated_at=now,
                )
            )
            if accepted.rowcount != 1:
                raise InterviewConflict(
                    "stale_revision", "interview revision is stale"
                )
            return design

    def _require_untampered_proposal(
        self,
        proposal: InterviewProposal,
    ) -> None:
        candidate = proposal.candidate_json
        actual_digest = design_digest(
            self._required_document(candidate, "profile"),
            self._required_document(candidate, "workflow"),
            self._required_document(candidate, "scenarios"),
            self._required_document(candidate, "catalog"),
        )
        if not compare_digest(proposal.digest, actual_digest):
            raise InterviewConflict(
                "stale_proposal", "proposal digest is stale"
            )

    def _advance_session_for_apply(
        self,
        db: Session,
        session: InterviewSession,
        *,
        base_revision: int,
        now: datetime,
    ) -> None:
        advance_session_without_live_operation(
            db,
            session,
            base_revision=base_revision,
            status="completed",
            retention_expires_at=self._retention_expiry(now),
            now=now,
        )

    def _claim_generation(
        self,
        actor: Actor,
        session_id: str,
        request: ProposalRequest,
        request_id: str,
        input_digest: str,
    ) -> tuple[
        str,
        InterviewContext,
        InterviewProposalDetailResponse | None,
    ]:
        now = _utcnow()
        with self._session_factory.begin() as db:
            session = self._required_session(
                db, actor.organization_id, session_id, now
            )
            if session.selected_scope is not None and re.fullmatch(
                WORKFLOW_ID_PATTERN, session.selected_scope
            ) is None:
                raise InterviewConflict(
                    "scope_invalid",
                    "selected scope is not a canonical workflow ID",
                )
            operation = db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.organization_id == actor.organization_id,
                    InterviewOperation.session_id == session_id,
                    InterviewOperation.request_id == request_id,
                )
            )
            if operation is not None:
                if (
                    operation.kind != "proposal"
                    or operation.input_digest != input_digest
                ):
                    raise InterviewConflict(
                        "request_id_reused",
                        "request ID was reused with different input",
                    )
                if operation.status == "succeeded":
                    proposal = db.scalar(
                        select(InterviewProposal).where(
                            InterviewProposal.organization_id
                            == actor.organization_id,
                            InterviewProposal.session_id == session_id,
                            InterviewProposal.generation_request_id == request_id,
                        )
                    )
                    if proposal is None:
                        raise InterviewConflict(
                            "operation_superseded",
                            "interview operation was superseded",
                        )
                    return (
                        operation.ownership_token,
                        self._context(db, session),
                        self._response(proposal),
                    )
                if session.revision != operation.base_revision:
                    raise InterviewConflict(
                        "stale_revision", "interview revision is stale"
                    )
                token = str(uuid4())
                try:
                    reclaim_operation(
                        db,
                        session,
                        operation,
                        token=token,
                        lease_expires_at=self._lease_expiry(now),
                        retention_expires_at=self._retention_expiry(now),
                        now=now,
                    )
                except OperationClaimConflict:
                    raise InterviewConflict(
                        "interview_busy", "interview operation is busy"
                    ) from None
                return token, self._context(db, session), None

            if session.revision != request.expected_revision:
                raise InterviewConflict(
                    "stale_revision", "interview revision is stale"
                )
            token = str(uuid4())
            lease_expires_at = self._lease_expiry(now)
            try:
                claim_session_operation(
                    db,
                    session,
                    request_id=request_id,
                    kind="proposal",
                    token=token,
                    base_revision=request.expected_revision,
                    lease_expires_at=lease_expires_at,
                    retention_expires_at=self._retention_expiry(now),
                    now=now,
                )
            except OperationClaimConflict:
                raise InterviewConflict(
                    "interview_busy", "interview operation is busy"
                ) from None
            db.add(
                InterviewOperation(
                    id=str(uuid4()),
                    organization_id=actor.organization_id,
                    session_id=session_id,
                    request_id=request_id,
                    kind="proposal",
                    input_digest=input_digest,
                    status="running",
                    ownership_token=token,
                    base_revision=request.expected_revision,
                    error_code=None,
                    lease_expires_at=lease_expires_at,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()
            return token, self._context(db, session), None

    def _finish_generation(
        self,
        actor: Actor,
        session_id: str,
        request_id: str,
        token: str,
        base_revision: int,
        candidate: DraftCandidate,
        catalog: dict[str, object],
    ) -> InterviewProposalDetailResponse:
        now = _utcnow()
        with self._session_factory.begin() as db:
            session = self._required_session(
                db, actor.organization_id, session_id, now
            )
            operation = db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.organization_id == actor.organization_id,
                    InterviewOperation.session_id == session_id,
                    InterviewOperation.request_id == request_id,
                    InterviewOperation.status == "running",
                    InterviewOperation.ownership_token == token,
                    InterviewOperation.base_revision == base_revision,
                    InterviewOperation.lease_expires_at > now,
                )
            )
            if operation is None:
                raise InterviewConflict(
                    "operation_superseded", "interview operation was superseded"
                )
            documents, findings = self._assemble(
                session, candidate, catalog, now
            )
            proposal_digest = design_digest(
                documents["profile"],
                documents["workflow"],
                documents["scenarios"],
                documents["catalog"],
            )
            advanced = db.execute(
                update(InterviewSession)
                .where(
                    InterviewSession.organization_id == actor.organization_id,
                    InterviewSession.id == session_id,
                    InterviewSession.revision == base_revision,
                    InterviewSession.last_operation_token == token,
                    InterviewSession.last_operation_lease_expires_at > now,
                    InterviewSession.expires_at > now,
                )
                .execution_options(synchronize_session=False)
                .values(
                    revision=base_revision + 1,
                    status="completed",
                    last_operation_status="succeeded",
                    last_error_code=None,
                    updated_at=now,
                    expires_at=self._retention_expiry(now),
                )
            )
            if advanced.rowcount != 1:
                raise InterviewConflict(
                    "operation_superseded", "interview operation was superseded"
                )
            proposal = InterviewProposal(
                id=str(uuid4()),
                organization_id=actor.organization_id,
                session_id=session_id,
                generation_request_id=request_id,
                revision=base_revision + 1,
                digest=proposal_digest,
                status="draft",
                candidate_json=documents,
                findings_json=findings,
                created_at=now,
                updated_at=now,
            )
            db.add(proposal)
            operation.status = "succeeded"
            operation.error_code = None
            operation.updated_at = now
            db.flush()
            return self._response(proposal)

    def _assemble(
        self,
        session: InterviewSession,
        candidate: DraftCandidate,
        catalog: dict[str, object],
        now: datetime,
    ) -> tuple[dict[str, dict[str, object]], list[dict[str, str]]]:
        value = candidate.model_dump()
        profile = value["profile"]
        workflow = value["workflow"]
        scenarios = value["scenarios"]
        profile["customer_id"] = session.customer_id
        profile["name"] = session.name
        workflow["customer_id"] = session.customer_id
        profile["facts"] = [
            {
                "id": f"fact-{index}",
                "statement": str(item["statement"]),
                "evidence": "Confirmed during interview.",
            }
            for index, item in enumerate(
                (
                    item
                    for item in session.confirmed_evidence_json
                    if item.get("kind") == "fact"
                ),
                start=1,
            )
        ]
        profile["assumptions"] = self._merge_evidence(
            profile["assumptions"],
            session,
            "assumption",
        )
        profile["unknowns"] = self._merge_evidence(
            profile["unknowns"],
            session,
            "unknown",
        )
        documents = {
            "profile": profile,
            "workflow": workflow,
            "scenarios": scenarios,
            "catalog": catalog,
        }
        findings: list[dict[str, str]] = []
        confirmed_statements = {
            str(item["statement"])
            for item in session.confirmed_evidence_json
            if item.get("kind") == "fact"
        }
        for fact in candidate.profile.facts:
            if fact.statement not in confirmed_statements:
                findings.append(
                    {
                        "field": "profile.facts",
                        "code": "unconfirmed-model-fact",
                        "message": fact.statement,
                    }
                )
        if session.selected_scope is None:
            findings.append(
                {
                    "field": "workflow.approved",
                    "code": "scope-not-selected",
                    "message": (
                        "Select and confirm the generation scope before applying "
                        "this proposal."
                    ),
                }
            )
        elif workflow["id"] != session.selected_scope:
            findings.append(
                {
                    "field": "workflow.id",
                    "code": "scope-mismatch",
                    "message": "The proposed workflow does not match the selected scope.",
                }
            )
        else:
            findings.append(
                {
                    "field": "workflow.approved",
                    "code": "scope-confirmation-required",
                    "message": (
                        "Applying this exact proposal confirms only its generation "
                        "scope; exact-digest design review remains separate."
                    ),
                }
            )
        for item in session.proposed_evidence_json:
            if item.get("kind") == "fact":
                findings.append(
                    {
                        "field": "profile.facts",
                        "code": "unconfirmed-fact",
                        "message": str(item["statement"]),
                    }
                )
        validation_workflow = {
            **workflow,
            "approved": {
                "by": "proposal-contract-check",
                "at": now.isoformat(),
            },
        }
        try:
            validate(
                profile,
                validation_workflow,
                catalog,
                self._settings.catalog_root,
            )
            validate_scenarios(scenarios, validation_workflow)
        except (ValidationError, EvaluationError) as exc:
            findings.append(
                {
                    "field": "contract",
                    "code": "incomplete-design",
                    "message": str(exc),
                }
            )
        return documents, findings

    @staticmethod
    def _merge_evidence(
        existing: list[str],
        session: InterviewSession,
        kind: str,
    ) -> list[str]:
        values = list(existing)
        for item in (
            *session.confirmed_evidence_json,
            *session.proposed_evidence_json,
        ):
            statement = str(item["statement"])
            if item.get("kind") == kind and statement not in values:
                values.append(statement)
        return values

    def _record_failure(
        self,
        organization_id: str,
        session_id: str,
        request_id: str,
        token: str,
        code: str,
    ) -> bool:
        now = _utcnow()
        with self._session_factory.begin() as db:
            operation = db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.organization_id == organization_id,
                    InterviewOperation.session_id == session_id,
                    InterviewOperation.request_id == request_id,
                    InterviewOperation.status == "running",
                    InterviewOperation.ownership_token == token,
                )
            )
            if operation is None:
                return False
            recorded = db.execute(
                update(InterviewSession)
                .where(
                    InterviewSession.organization_id == organization_id,
                    InterviewSession.id == session_id,
                    InterviewSession.last_operation_token == token,
                    InterviewSession.expires_at > now,
                )
                .execution_options(synchronize_session=False)
                .values(
                    last_operation_status="failed",
                    last_error_code=code,
                    updated_at=now,
                )
            )
            if recorded.rowcount != 1:
                return False
            operation.status = "failed"
            operation.error_code = code
            operation.updated_at = now
            return True

    def _accepted_duplicate(
        self,
        db: Session,
        actor: Actor,
        proposal: InterviewProposal,
        apply_digest: str,
    ) -> HarnessDesign:
        if (
            proposal.apply_digest != apply_digest
            or proposal.accepted_by != actor.subject_id
            or proposal.accepted_design_id is None
            or proposal.accepted_design_digest is None
        ):
            raise InterviewConflict(
                "proposal_already_applied",
                "proposal was already applied with different input",
            )
        design = db.scalar(
            select(HarnessDesign).where(
                HarnessDesign.organization_id == actor.organization_id,
                HarnessDesign.id == proposal.accepted_design_id,
                HarnessDesign.digest == proposal.accepted_design_digest,
            )
        )
        if design is None:
            raise InterviewConflict(
                "stale_digest", "accepted design has changed"
            )
        return design

    def _required_session(
        self,
        db: Session,
        organization_id: str,
        session_id: str,
        now: datetime,
    ) -> InterviewSession:
        session = db.scalar(
            select(InterviewSession).where(
                InterviewSession.organization_id == organization_id,
                InterviewSession.id == session_id,
                InterviewSession.expires_at > now,
            )
        )
        if session is None:
            raise InterviewNotFound()
        return session

    @staticmethod
    def _required_document(
        candidate: dict[str, object], field: str
    ) -> dict[str, object]:
        value = candidate.get(field)
        if not isinstance(value, dict):
            raise InterviewConflict(
                "stale_proposal", "stored proposal is invalid"
            )
        return value

    def _context(
        self, db: Session, session: InterviewSession
    ) -> InterviewContext:
        turns = db.scalars(
            select(StoredTurn)
            .where(
                StoredTurn.organization_id == session.organization_id,
                StoredTurn.session_id == session.id,
            )
            .order_by(StoredTurn.sequence)
        ).all()
        return InterviewContext(
            session_id=session.id,
            revision=session.revision,
            turns=tuple(
                InterviewTurn(
                    id=turn.id,
                    role=turn.role,
                    text=turn.text,
                    options=tuple(turn.options_json or []),
                    allow_custom_answer=(
                        True
                        if turn.allow_custom_answer is None
                        else turn.allow_custom_answer
                    ),
                    choice_question_turn_id=turn.choice_question_turn_id,
                    choice_option_id=turn.choice_option_id,
                )
                for turn in turns
            ),
            confirmed_evidence=tuple(
                ConfirmedEvidence(
                    id=str(item["id"]),
                    statement=str(item["statement"]),
                    source_turn_ids=tuple(
                        str(source_id) for source_id in item["source_turn_ids"]
                    ),
                )
                for item in session.confirmed_evidence_json
                if item.get("kind") == "fact"
            ),
            stage=session.stage,
            selected_scope=session.selected_scope,
            selected_stages=stored_stages(session.selected_stages_json),
        )

    @staticmethod
    def _response(
        proposal: InterviewProposal,
    ) -> InterviewProposalDetailResponse:
        return InterviewProposalDetailResponse.model_validate(
            {
                "id": proposal.id,
                "revision": proposal.revision,
                "digest": proposal.digest,
                "status": proposal.status,
                "findings": proposal.findings_json,
                "profile": proposal.candidate_json["profile"],
                "workflow": proposal.candidate_json["workflow"],
                "scenarios": proposal.candidate_json["scenarios"],
                "catalog": proposal.candidate_json["catalog"],
                "created_at": _aware(proposal.created_at),
                "updated_at": _aware(proposal.updated_at),
            }
        )

    def _retention_expiry(self, now: datetime) -> datetime:
        return now + timedelta(days=self._settings.interview_retention_days)

    def _lease_expiry(self, now: datetime) -> datetime:
        return now + timedelta(
            seconds=self._settings.interview_operation_lease_seconds
        )
