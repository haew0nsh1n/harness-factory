from uuid import uuid4

from sqlalchemy.orm import Session

from web.api.audit.models import AuditEvent

_SENSITIVE_SUMMARY_FRAGMENTS = frozenset(
    {
        "token",
        "password",
        "secret",
        "cookie",
        "credential",
        "prompt",
        "source_code",
        "diff",
        "content",
    }
)


class AuditService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        organization_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        summary: dict[str, str | int | bool | None],
    ) -> AuditEvent:
        self._validate_summary(summary)

        event = AuditEvent(
            id=str(uuid4()),
            organization_id=organization_id,
            actor_subject_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            summary_json=summary,
        )
        self._session.add(event)
        self._session.flush()
        return event

    @staticmethod
    def _validate_summary(summary: dict[str, str | int | bool | None]) -> None:
        for key, value in summary.items():
            lowered_key = key.lower()
            if any(
                fragment in lowered_key for fragment in _SENSITIVE_SUMMARY_FRAGMENTS
            ):
                raise ValueError("summary contains sensitive key")
            if value is None:
                continue
            if isinstance(value, bool):
                continue
            if not isinstance(value, (str, int)):
                raise ValueError("summary contains unsupported value type")
