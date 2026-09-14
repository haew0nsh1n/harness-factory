import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from web.api.db import get_session
from web.api.identity.entra import EntraTokenValidator
from web.api.identity.models import Actor, ROLES
from web.api.organizations.repository import (
    MembershipRepository,
    OrganizationRepository,
)

IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")


def _require_identifier(value: str | None) -> str:
    if not value:
        raise HTTPException(status_code=401, detail="authentication required")
    if not IDENTIFIER_RE.fullmatch(value):
        raise HTTPException(status_code=401, detail="authentication required")
    return value


def _require_roles(raw_roles: str | None) -> frozenset[str]:
    if not raw_roles:
        raise HTTPException(status_code=401, detail="authentication required")

    roles = frozenset(role.strip() for role in raw_roles.split(",") if role.strip())
    if not roles:
        raise HTTPException(status_code=401, detail="authentication required")
    if not roles.issubset(ROLES):
        raise HTTPException(status_code=403, detail="required role missing")
    return roles


def _get_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="authentication required")

    scheme, _, token = authorization.partition(" ")
    if scheme != "Bearer" or not token:
        raise HTTPException(status_code=401, detail="authentication required")
    return token


def _get_entra_validator(request: Request, settings) -> EntraTokenValidator:
    validator = getattr(request.app.state, "entra_validator", None)
    if validator is None:
        validator = EntraTokenValidator.from_settings(settings)
        request.app.state.entra_validator = validator
    return validator


def get_actor(
    request: Request, session: Session = Depends(get_session)
) -> Actor:
    settings = request.app.state.settings
    if settings.auth_mode == "development":
        if not settings.allow_insecure_development_auth:
            raise HTTPException(status_code=401, detail="authentication required")
        return Actor(
            organization_id=_require_identifier(
                request.headers.get("X-HF-Organization")
            ),
            subject_id=_require_identifier(request.headers.get("X-HF-Subject")),
            roles=_require_roles(request.headers.get("X-HF-Roles")),
        )

    if settings.auth_mode != "entra":
        raise HTTPException(status_code=401, detail="authentication required")

    principal = _get_entra_validator(request, settings).validate(
        _get_bearer_token(request)
    )
    organization = OrganizationRepository(session).get_by_entra_tenant_id(
        principal.tenant_id
    )
    if organization is None:
        raise HTTPException(status_code=401, detail="authentication required")

    membership = MembershipRepository(session).get_by_subject_id(
        organization.organization_id, principal.subject_id
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="required role missing")

    return Actor(
        organization_id=organization.organization_id,
        subject_id=membership.subject_id,
        roles=frozenset(
            role for role in membership.roles_json if isinstance(role, str) and role in ROLES
        ),
    )


def require_roles(*allowed: str):
    def dependency(actor: Actor = Depends(get_actor)) -> Actor:
        if not actor.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="required role missing")
        return actor

    return dependency
