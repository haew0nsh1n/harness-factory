from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from web.api.audit.service import AuditService
from web.api.config import Settings
from web.api.identity.models import Actor

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
    claim_session_operation,
    reclaim_operation,
)
from .privacy import reject_recognizable_secrets
from .schemas import (
    AnswerRequest,
    ConfirmationRequest,
    InterviewReply,
    InterviewSessionResponse,
    StartInterviewRequest,
)


@dataclass
class InterviewNotFound(Exception):
    pass


@dataclass
class InterviewTargetNotFound(Exception):
    pass


@dataclass
class InterviewConflict(Exception):
    code: str
    message: str


@dataclass
class InterviewInferenceFailure(Exception):
    code: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(value: dict[str, object]) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(payload).hexdigest()


class InterviewService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        model: InterviewModel,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._model = model

    async def start(
        self, actor: Actor, request: StartInterviewRequest
    ) -> tuple[InterviewSessionResponse, bool]:
        reject_recognizable_secrets(request.name, request.customer_id)
        request_id = str(request.request_id)
        input_digest = _digest(
            {
                "kind": "start",
                "name": request.name,
                "customer_id": request.customer_id,
                "consent_version": request.consent_version,
            }
        )
        created = False
        try:
            session_id, token, should_call = self._claim_start(
                actor, request, request_id, input_digest
            )
            created = should_call
        except IntegrityError as exc:
            try:
                session_id, token, should_call = self._claim_existing_start(
                    actor, request_id, input_digest
                )
            except InterviewNotFound:
                raise exc

        if not should_call:
            return self.get(actor, session_id), False

        context = InterviewContext(
            session_id=session_id,
            revision=0,
            turns=(),
            confirmed_evidence=(),
            stage="discovery",
            selected_scope=None,
        )
        await self._run_model_operation(
            actor.organization_id,
            session_id,
            request_id,
            token,
            0,
            context,
        )
        return self.get(actor, session_id), created

    def _claim_start(
        self,
        actor: Actor,
        request: StartInterviewRequest,
        request_id: str,
        input_digest: str,
    ) -> tuple[str, str, bool]:
        now = _utcnow()
        session_id = str(uuid4())
        token = str(uuid4())
        with self._session_factory.begin() as db:
            session = InterviewSession(
                id=session_id,
                organization_id=actor.organization_id,
                owner_subject_id=actor.subject_id,
                name=request.name,
                customer_id=request.customer_id,
                revision=0,
                status="active",
                consent_version=request.consent_version,
                consented_at=now,
                stage="discovery",
                selected_scope=None,
                proposed_evidence_json=[],
                confirmed_evidence_json=[],
                creation_request_id=request_id,
                creation_input_digest=input_digest,
                last_operation_request_id=request_id,
                last_operation_kind="start",
                last_operation_status="running",
                last_operation_token=token,
                last_operation_base_revision=0,
                last_operation_lease_expires_at=self._lease_expiry(now),
                last_error_code=None,
                created_at=now,
                updated_at=now,
                expires_at=self._retention_expiry(now),
            )
            db.add(session)
            db.flush()
            db.add(
                InterviewOperation(
                    id=str(uuid4()),
                    organization_id=actor.organization_id,
                    session_id=session_id,
                    request_id=request_id,
                    kind="start",
                    input_digest=input_digest,
                    status="running",
                    ownership_token=token,
                    base_revision=0,
                    error_code=None,
                    lease_expires_at=self._lease_expiry(now),
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()
        return session_id, token, True

    def _claim_existing_start(
        self,
        actor: Actor,
        request_id: str,
        input_digest: str,
    ) -> tuple[str, str, bool]:
        with self._session_factory.begin() as db:
            session = db.scalar(
                select(InterviewSession).where(
                    InterviewSession.organization_id == actor.organization_id,
                    InterviewSession.creation_request_id == request_id,
                )
            )
            if session is None or self._expired(session):
                raise InterviewNotFound()
            if session.creation_input_digest != input_digest:
                raise InterviewConflict(
                    "request_id_reused", "request ID was reused with different input"
                )
            operation = self._operation(db, actor.organization_id, session.id, request_id)
            if operation.status == "succeeded":
                return session.id, operation.ownership_token, False
            now = _utcnow()
            token = self._reclaim_operation(db, session, operation, now)
            return session.id, token, True

    async def answer(
        self, actor: Actor, session_id: str, request: AnswerRequest
    ) -> InterviewSessionResponse:
        reject_recognizable_secrets(request.answer)
        request_id = str(request.request_id)
        input_digest = _digest(
            {
                "kind": "answer",
                "expected_revision": request.expected_revision,
                "answer": request.answer,
            }
        )
        token, context, should_call = self._claim_answer(
            actor,
            session_id,
            request,
            request_id,
            input_digest,
        )
        if not should_call:
            return self.get(actor, session_id)
        await self._run_model_operation(
            actor.organization_id,
            session_id,
            request_id,
            token,
            request.expected_revision,
            context,
        )
        return self.get(actor, session_id)

    def _claim_answer(
        self,
        actor: Actor,
        session_id: str,
        request: AnswerRequest,
        request_id: str,
        input_digest: str,
    ) -> tuple[str, InterviewContext, bool]:
        now = _utcnow()
        with self._session_factory.begin() as db:
            session = self._required_session(db, actor.organization_id, session_id)
            existing = db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.organization_id == actor.organization_id,
                    InterviewOperation.session_id == session_id,
                    InterviewOperation.request_id == request_id,
                )
            )
            if existing is not None:
                if existing.kind != "answer" or existing.input_digest != input_digest:
                    raise InterviewConflict(
                        "request_id_reused",
                        "request ID was reused with different input",
                    )
                if existing.status == "succeeded":
                    return existing.ownership_token, self._context(db, session), False
                if session.revision != existing.base_revision:
                    raise InterviewConflict(
                        "stale_revision", "interview revision is stale"
                    )
                token = self._reclaim_operation(db, session, existing, now)
                return token, self._context(db, session), True

            if session.revision != request.expected_revision:
                raise InterviewConflict("stale_revision", "interview revision is stale")
            if (
                session.last_operation_status == "running"
                and session.last_operation_lease_expires_at is not None
                and _aware(session.last_operation_lease_expires_at) > now
            ):
                raise InterviewConflict("interview_busy", "interview operation is busy")
            turn_count = db.scalar(
                select(func.count())
                .select_from(StoredTurn)
                .where(
                    StoredTurn.organization_id == actor.organization_id,
                    StoredTurn.session_id == session_id,
                )
            )
            if int(turn_count or 0) + 2 > 60:
                raise InterviewConflict(
                    "turn_limit", "interview turn limit has been reached"
                )

            token = str(uuid4())
            lease_expires_at = self._lease_expiry(now)
            self._claim_session_operation(
                db,
                session,
                request_id=request_id,
                kind="answer",
                token=token,
                base_revision=request.expected_revision,
                lease_expires_at=lease_expires_at,
                now=now,
            )
            operation = InterviewOperation(
                id=str(uuid4()),
                organization_id=actor.organization_id,
                session_id=session_id,
                request_id=request_id,
                kind="answer",
                input_digest=input_digest,
                status="running",
                ownership_token=token,
                base_revision=request.expected_revision,
                error_code=None,
                lease_expires_at=lease_expires_at,
                created_at=now,
                updated_at=now,
            )
            db.add(operation)
            db.add(
                StoredTurn(
                    id=str(uuid4()),
                    organization_id=actor.organization_id,
                    session_id=session_id,
                    operation_id=operation.id,
                    sequence=int(turn_count or 0) + 1,
                    role="user",
                    text=request.answer,
                    created_at=now,
                )
            )
            db.flush()
            return token, self._context(db, session), True

    async def _run_model_operation(
        self,
        organization_id: str,
        session_id: str,
        request_id: str,
        token: str,
        base_revision: int,
        context: InterviewContext,
    ) -> None:
        try:
            reply = await self._model.next_question(context)
        except InterviewModelError as exc:
            recorded = self._record_failure(
                organization_id, session_id, request_id, token, exc.code
            )
            if not recorded:
                raise InterviewConflict(
                    "operation_superseded", "interview operation was superseded"
                ) from None
            raise InterviewInferenceFailure(exc.code) from None
        turn_ids = {turn.id for turn in context.turns}
        if any(
            source_id not in turn_ids
            for evidence in reply.evidence
            for source_id in evidence.source_turn_ids
        ):
            recorded = self._record_failure(
                organization_id,
                session_id,
                request_id,
                token,
                "llm_invalid_result",
            )
            if not recorded:
                raise InterviewConflict(
                    "operation_superseded", "interview operation was superseded"
                )
            raise InterviewInferenceFailure("llm_invalid_result")
        self._finish_operation(
            organization_id,
            session_id,
            request_id,
            token,
            base_revision,
            reply,
        )

    def _finish_operation(
        self,
        organization_id: str,
        session_id: str,
        request_id: str,
        token: str,
        base_revision: int,
        reply: InterviewReply,
    ) -> bool:
        now = _utcnow()
        with self._session_factory.begin() as db:
            session = db.scalar(
                select(InterviewSession).where(
                    InterviewSession.organization_id == organization_id,
                    InterviewSession.id == session_id,
                    InterviewSession.expires_at > now,
                )
            )
            operation = db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.organization_id == organization_id,
                    InterviewOperation.session_id == session_id,
                    InterviewOperation.request_id == request_id,
                    InterviewOperation.status == "running",
                    InterviewOperation.ownership_token == token,
                    InterviewOperation.base_revision == base_revision,
                    InterviewOperation.lease_expires_at > now,
                )
            )
            if session is None or operation is None:
                raise InterviewConflict(
                    "operation_superseded", "interview operation was superseded"
                )
            proposed = [
                {
                    "id": str(uuid4()),
                    "statement": item.statement,
                    "kind": item.kind,
                    "source_turn_ids": item.source_turn_ids,
                }
                for item in reply.evidence
            ]
            turn_count = db.scalar(
                select(func.count())
                .select_from(StoredTurn)
                .where(
                    StoredTurn.organization_id == organization_id,
                    StoredTurn.session_id == session_id,
                )
            )
            advanced = db.execute(
                update(InterviewSession)
                .where(
                    InterviewSession.organization_id == organization_id,
                    InterviewSession.id == session_id,
                    InterviewSession.revision == base_revision,
                    InterviewSession.last_operation_token == token,
                    InterviewSession.last_operation_lease_expires_at > now,
                    InterviewSession.expires_at > now,
                )
                .execution_options(synchronize_session=False)
                .values(
                    revision=base_revision + 1,
                    status=(
                        "awaiting-confirmation"
                        if proposed
                        else ("completed" if reply.ready_for_review else "active")
                    ),
                    stage=reply.stage,
                    selected_scope=reply.proposed_scope,
                    proposed_evidence_json=proposed,
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
            db.add(
                StoredTurn(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    session_id=session_id,
                    operation_id=operation.id,
                    sequence=int(turn_count or 0) + 1,
                    role="assistant",
                    text=reply.question,
                    created_at=now,
                )
            )
            operation.status = "succeeded"
            operation.error_code = None
            operation.updated_at = now

    def _record_failure(
        self,
        organization_id: str,
        session_id: str,
        request_id: str,
        token: str,
        code: str,
    ) -> None:
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
            persisted = db.execute(
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
            if persisted.rowcount != 1:
                return False
            operation.status = "failed"
            operation.error_code = code
            operation.updated_at = now
            return True

    def confirm(
        self,
        actor: Actor,
        session_id: str,
        request: ConfirmationRequest,
    ) -> InterviewSessionResponse:
        request_id = str(request.request_id)
        input_digest = _digest(
            {
                "kind": "confirmation",
                "expected_revision": request.expected_revision,
                "decisions": [
                    {
                        "evidence_id": str(item.evidence_id),
                        "decision": item.decision,
                    }
                    for item in request.decisions
                ],
            }
        )
        now = _utcnow()
        with self._session_factory.begin() as db:
            session = self._required_session(db, actor.organization_id, session_id)
            existing = db.scalar(
                select(InterviewOperation).where(
                    InterviewOperation.organization_id == actor.organization_id,
                    InterviewOperation.session_id == session_id,
                    InterviewOperation.request_id == request_id,
                )
            )
            if existing is not None:
                if (
                    existing.kind != "confirmation"
                    or existing.input_digest != input_digest
                ):
                    raise InterviewConflict(
                        "request_id_reused",
                        "request ID was reused with different input",
                    )
                if existing.status == "succeeded":
                    return self._snapshot(db, session)
            if session.revision != request.expected_revision:
                raise InterviewConflict("stale_revision", "interview revision is stale")
            if existing is not None:
                token = self._reclaim_operation(db, session, existing, now)
            else:
                token = str(uuid4())
                lease_expires_at = self._lease_expiry(now)
                self._claim_session_operation(
                    db,
                    session,
                    request_id=request_id,
                    kind="confirmation",
                    token=token,
                    base_revision=request.expected_revision,
                    lease_expires_at=lease_expires_at,
                    now=now,
                )
                existing = InterviewOperation(
                    id=str(uuid4()),
                    organization_id=actor.organization_id,
                    session_id=session_id,
                    request_id=request_id,
                    kind="confirmation",
                    input_digest=input_digest,
                    status="running",
                    ownership_token=token,
                    base_revision=request.expected_revision,
                    error_code=None,
                    lease_expires_at=lease_expires_at,
                    created_at=now,
                    updated_at=now,
                )
                db.add(existing)
            proposed_by_id = {
                item["id"]: item for item in session.proposed_evidence_json
            }
            decision_ids = {str(item.evidence_id) for item in request.decisions}
            if not decision_ids.issubset(proposed_by_id):
                raise InterviewConflict(
                    "unknown_evidence", "evidence proposal was not found"
                )
            confirmed = list(session.confirmed_evidence_json)
            for decision in request.decisions:
                evidence = proposed_by_id[str(decision.evidence_id)]
                if decision.decision == "confirm":
                    confirmed.append(evidence)
            session.confirmed_evidence_json = confirmed
            session.proposed_evidence_json = [
                item
                for item in session.proposed_evidence_json
                if item["id"] not in decision_ids
            ]
            session.revision += 1
            session.status = (
                "awaiting-confirmation"
                if session.proposed_evidence_json
                else "active"
            )
            session.last_operation_request_id = request_id
            session.last_operation_kind = "confirmation"
            session.last_operation_status = "succeeded"
            session.last_operation_token = token
            session.last_operation_base_revision = request.expected_revision
            session.last_operation_lease_expires_at = now
            session.last_error_code = None
            session.updated_at = now
            session.expires_at = self._retention_expiry(now)
            existing.status = "succeeded"
            existing.error_code = None
            existing.lease_expires_at = now
            existing.updated_at = now
            db.flush()
            return self._snapshot(db, session)

    def list(self, actor: Actor) -> list[InterviewSessionResponse]:
        now = _utcnow()
        with self._session_factory() as db:
            sessions = db.scalars(
                select(InterviewSession)
                .where(
                    InterviewSession.organization_id == actor.organization_id,
                    InterviewSession.expires_at > now,
                )
                .order_by(InterviewSession.updated_at.desc())
            ).all()
            return [self._snapshot(db, session) for session in sessions]

    def get(self, actor: Actor, session_id: str) -> InterviewSessionResponse:
        with self._session_factory() as db:
            session = self._required_session(db, actor.organization_id, session_id)
            return self._snapshot(db, session)

    def delete(self, actor: Actor, session_id: str) -> None:
        with self._session_factory.begin() as db:
            session = self._required_session(db, actor.organization_id, session_id)
            turn_count = db.scalar(
                select(func.count())
                .select_from(StoredTurn)
                .where(
                    StoredTurn.organization_id == actor.organization_id,
                    StoredTurn.session_id == session_id,
                )
            )
            proposal_count = db.scalar(
                select(func.count())
                .select_from(InterviewProposal)
                .where(
                    InterviewProposal.organization_id == actor.organization_id,
                    InterviewProposal.session_id == session_id,
                )
            )
            AuditService(db).append(
                organization_id=actor.organization_id,
                actor_id=actor.subject_id,
                action="interview.deleted",
                resource_type="interview-session",
                resource_id=session_id,
                summary={
                    "turn_count": int(turn_count or 0),
                    "proposal_count": int(proposal_count or 0),
                },
            )
            db.delete(session)

    def _required_session(
        self, db: Session, organization_id: str, session_id: str
    ) -> InterviewSession:
        session = db.scalar(
            select(InterviewSession).where(
                InterviewSession.organization_id == organization_id,
                InterviewSession.id == session_id,
            )
        )
        if session is None or self._expired(session):
            raise InterviewNotFound()
        return session

    @staticmethod
    def _operation(
        db: Session, organization_id: str, session_id: str, request_id: str
    ) -> InterviewOperation:
        operation = db.scalar(
            select(InterviewOperation).where(
                InterviewOperation.organization_id == organization_id,
                InterviewOperation.session_id == session_id,
                InterviewOperation.request_id == request_id,
            )
        )
        if operation is None:
            raise InterviewConflict(
                "operation_superseded", "interview operation was superseded"
            )
        return operation

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
                InterviewTurn(id=turn.id, role=turn.role, text=turn.text)
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
            ),
            stage=session.stage,
            selected_scope=session.selected_scope,
        )

    def _snapshot(
        self, db: Session, session: InterviewSession
    ) -> InterviewSessionResponse:
        turns = db.scalars(
            select(StoredTurn)
            .where(
                StoredTurn.organization_id == session.organization_id,
                StoredTurn.session_id == session.id,
            )
            .order_by(StoredTurn.sequence)
        ).all()
        proposals = db.scalars(
            select(InterviewProposal)
            .where(
                InterviewProposal.organization_id == session.organization_id,
                InterviewProposal.session_id == session.id,
            )
            .order_by(InterviewProposal.created_at)
        ).all()
        last_operation = None
        if session.last_operation_request_id is not None:
            last_operation = {
                "request_id": session.last_operation_request_id,
                "kind": session.last_operation_kind,
                "status": session.last_operation_status,
            }
        return InterviewSessionResponse.model_validate(
            {
                "id": session.id,
                "organization_id": session.organization_id,
                "owner_subject_id": session.owner_subject_id,
                "name": session.name,
                "customer_id": session.customer_id,
                "revision": session.revision,
                "status": session.status,
                "consent_version": session.consent_version,
                "consented_at": _aware(session.consented_at),
                "stage": session.stage,
                "scope": session.selected_scope,
                "proposed_evidence": session.proposed_evidence_json,
                "confirmed_evidence": session.confirmed_evidence_json,
                "turns": [
                    {
                        "id": turn.id,
                        "role": turn.role,
                        "text": turn.text,
                        "sequence": turn.sequence,
                        "created_at": _aware(turn.created_at),
                    }
                    for turn in turns
                ],
                "proposals": [
                    {
                        "id": proposal.id,
                        "revision": proposal.revision,
                        "digest": proposal.digest,
                        "status": proposal.status,
                        "findings": proposal.findings_json,
                        "created_at": _aware(proposal.created_at),
                        "updated_at": _aware(proposal.updated_at),
                    }
                    for proposal in proposals
                ],
                "last_operation": last_operation,
                "last_error_code": session.last_error_code,
                "created_at": _aware(session.created_at),
                "updated_at": _aware(session.updated_at),
                "expires_at": _aware(session.expires_at),
            }
        )

    def _claim_session_operation(
        self,
        db: Session,
        session: InterviewSession,
        *,
        request_id: str,
        kind: str,
        token: str,
        base_revision: int,
        lease_expires_at: datetime,
        now: datetime,
    ) -> None:
        try:
            claim_session_operation(
                db,
                session,
                request_id=request_id,
                kind=kind,
                token=token,
                base_revision=base_revision,
                lease_expires_at=lease_expires_at,
                retention_expires_at=self._retention_expiry(now),
                now=now,
            )
        except OperationClaimConflict:
            raise InterviewConflict("interview_busy", "interview operation is busy")

    def _reclaim_operation(
        self,
        db: Session,
        session: InterviewSession,
        operation: InterviewOperation,
        now: datetime,
    ) -> str:
        token = str(uuid4())
        lease_expires_at = self._lease_expiry(now)
        try:
            reclaim_operation(
                db,
                session,
                operation,
                token=token,
                lease_expires_at=lease_expires_at,
                retention_expires_at=self._retention_expiry(now),
                now=now,
                claim=lambda db, session, **kwargs: self._claim_session_operation(
                    db,
                    session,
                    request_id=kwargs["request_id"],
                    kind=kwargs["kind"],
                    token=kwargs["token"],
                    base_revision=kwargs["base_revision"],
                    lease_expires_at=kwargs["lease_expires_at"],
                    now=kwargs["now"],
                ),
            )
        except OperationClaimConflict:
            raise InterviewConflict("interview_busy", "interview operation is busy")
        return token

    def _expired(self, session: InterviewSession) -> bool:
        return _aware(session.expires_at) <= _utcnow()

    def _retention_expiry(self, now: datetime) -> datetime:
        return now + timedelta(days=self._settings.interview_retention_days)

    def _lease_expiry(self, now: datetime) -> datetime:
        return now + timedelta(
            seconds=self._settings.interview_operation_lease_seconds
        )


def delete_expired_interviews(
    session_factory: sessionmaker[Session], now: datetime | None = None
) -> int:
    cutoff = now or _utcnow()
    with session_factory.begin() as db:
        result = db.execute(
            delete(InterviewSession).where(InterviewSession.expires_at <= cutoff)
        )
        return int(result.rowcount or 0)
