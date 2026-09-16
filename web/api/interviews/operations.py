from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from .models import InterviewOperation, InterviewSession


class OperationClaimConflict(Exception):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _matches(column, value):
    return column.is_(None) if value is None else column == value


def session_operation_lease_expired(
    session: InterviewSession, *, now: datetime
) -> bool:
    return (
        session.last_operation_status == "running"
        and (
            session.last_operation_lease_expires_at is None
            or _aware(session.last_operation_lease_expires_at) <= now
        )
    )


def session_operation_is_live(
    session: InterviewSession, *, now: datetime
) -> bool:
    return (
        session.last_operation_status == "running"
        and not session_operation_lease_expired(session, now=now)
    )


def operation_lease_expired(
    operation: InterviewOperation, *, now: datetime
) -> bool:
    return (
        operation.status == "running"
        and _aware(operation.lease_expires_at) <= now
    )


def claim_session_operation(
    db: Session,
    session: InterviewSession,
    *,
    request_id: str,
    kind: str,
    token: str,
    base_revision: int,
    lease_expires_at: datetime,
    retention_expires_at: datetime,
    now: datetime,
) -> None:
    if session_operation_is_live(session, now=now):
        raise OperationClaimConflict()

    claimed = db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.organization_id == session.organization_id,
            InterviewSession.id == session.id,
            InterviewSession.revision == base_revision,
            InterviewSession.expires_at > now,
            _matches(
                InterviewSession.last_operation_request_id,
                session.last_operation_request_id,
            ),
            _matches(
                InterviewSession.last_operation_kind,
                session.last_operation_kind,
            ),
            _matches(
                InterviewSession.last_operation_status,
                session.last_operation_status,
            ),
            _matches(
                InterviewSession.last_operation_token,
                session.last_operation_token,
            ),
            _matches(
                InterviewSession.last_operation_base_revision,
                session.last_operation_base_revision,
            ),
            _matches(
                InterviewSession.last_operation_lease_expires_at,
                session.last_operation_lease_expires_at,
            ),
        )
        .execution_options(synchronize_session=False)
        .values(
            last_operation_request_id=request_id,
            last_operation_kind=kind,
            last_operation_status="running",
            last_operation_token=token,
            last_operation_base_revision=base_revision,
            last_operation_lease_expires_at=lease_expires_at,
            last_error_code=None,
            updated_at=now,
            expires_at=retention_expires_at,
        )
    )
    if claimed.rowcount != 1:
        raise OperationClaimConflict()
    db.refresh(session)


def advance_session_without_live_operation(
    db: Session,
    session: InterviewSession,
    *,
    base_revision: int,
    status: str,
    retention_expires_at: datetime,
    now: datetime,
) -> None:
    if session_operation_is_live(session, now=now):
        raise OperationClaimConflict()

    advanced = db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.organization_id == session.organization_id,
            InterviewSession.id == session.id,
            InterviewSession.revision == base_revision,
            InterviewSession.status == status,
            InterviewSession.expires_at > now,
            or_(
                InterviewSession.last_operation_status.is_(None),
                InterviewSession.last_operation_status != "running",
                InterviewSession.last_operation_lease_expires_at.is_(None),
                InterviewSession.last_operation_lease_expires_at <= now,
            ),
            _matches(
                InterviewSession.last_operation_request_id,
                session.last_operation_request_id,
            ),
            _matches(
                InterviewSession.last_operation_kind,
                session.last_operation_kind,
            ),
            _matches(
                InterviewSession.last_operation_status,
                session.last_operation_status,
            ),
            _matches(
                InterviewSession.last_operation_token,
                session.last_operation_token,
            ),
            _matches(
                InterviewSession.last_operation_base_revision,
                session.last_operation_base_revision,
            ),
            _matches(
                InterviewSession.last_operation_lease_expires_at,
                session.last_operation_lease_expires_at,
            ),
        )
        .execution_options(synchronize_session=False)
        .values(
            revision=base_revision + 1,
            updated_at=now,
            expires_at=retention_expires_at,
        )
    )
    if advanced.rowcount != 1:
        raise OperationClaimConflict()
    db.refresh(session)


def reclaim_operation(
    db: Session,
    session: InterviewSession,
    operation: InterviewOperation,
    *,
    token: str,
    lease_expires_at: datetime,
    retention_expires_at: datetime,
    now: datetime,
    claim: Callable[..., None] = claim_session_operation,
) -> None:
    if operation.status == "running" and not operation_lease_expired(
        operation, now=now
    ):
        raise OperationClaimConflict()
    previous_status = operation.status
    previous_token = operation.ownership_token
    previous_lease_expires_at = operation.lease_expires_at
    claim(
        db,
        session,
        request_id=operation.request_id,
        kind=operation.kind,
        token=token,
        base_revision=operation.base_revision,
        lease_expires_at=lease_expires_at,
        retention_expires_at=retention_expires_at,
        now=now,
    )
    claimed = db.execute(
        update(InterviewOperation)
        .where(
            InterviewOperation.id == operation.id,
            InterviewOperation.organization_id == operation.organization_id,
            InterviewOperation.session_id == operation.session_id,
            InterviewOperation.base_revision == operation.base_revision,
            InterviewOperation.status == previous_status,
            InterviewOperation.ownership_token == previous_token,
            InterviewOperation.lease_expires_at == previous_lease_expires_at,
        )
        .execution_options(synchronize_session=False)
        .values(
            status="running",
            ownership_token=token,
            error_code=None,
            lease_expires_at=lease_expires_at,
            updated_at=now,
        )
    )
    if claimed.rowcount != 1:
        raise OperationClaimConflict()
    db.refresh(operation)
