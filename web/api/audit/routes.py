from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from web.api.audit.models import AuditEvent
from web.api.db import get_session
from web.api.identity.dependencies import require_roles
from web.api.identity.models import Actor

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit")
def list_audit_events(
    actor: Actor = Depends(require_roles("org-admin")),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == actor.organization_id)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
    ).all()
    return {
        "ok": True,
        "items": [
            {
                "id": event.id,
                "organization_id": event.organization_id,
                "actor_subject_id": event.actor_subject_id,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "summary": event.summary_json,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }
