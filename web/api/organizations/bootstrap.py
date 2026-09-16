"""Idempotent development tenant bootstrap.

The Compose development stack starts with an empty database. Every authoring
write references ``organizations.id``, so the configured development
organization and its subject membership must exist before the first request.

This module refuses to run outside development mode.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.api.config import Settings, get_settings
from web.api.db import session_scope
from web.api.designs.repository import ensure_sqlite_write_transaction
from web.api.designs.samples import SampleDesignSeedInvalid, seed_sample_designs
from web.api.identity.models import ROLES
from web.api.organizations.models import Membership, Organization


class DevelopmentBootstrapNotAllowed(RuntimeError):
    """Raised when the bootstrap is attempted outside development mode."""


class DevelopmentBootstrapInvalid(ValueError):
    """Raised when the configured development identity is not usable."""


def _require_development_mode(settings: Settings) -> None:
    if settings.auth_mode != "development":
        raise DevelopmentBootstrapNotAllowed(
            "development bootstrap requires HF_AUTH_MODE=development"
        )
    if not settings.allow_insecure_development_auth:
        raise DevelopmentBootstrapNotAllowed(
            "development bootstrap requires "
            "HF_ALLOW_INSECURE_DEVELOPMENT_AUTH=true"
        )


def parse_development_roles(raw_roles: str) -> list[str]:
    roles = [role.strip() for role in raw_roles.split(",") if role.strip()]
    if not roles:
        raise DevelopmentBootstrapInvalid(
            "HF_DEVELOPMENT_ROLES must list at least one role"
        )
    unknown = sorted(set(roles) - ROLES)
    if unknown:
        raise DevelopmentBootstrapInvalid(
            f"unknown development roles: {', '.join(unknown)}"
        )
    return sorted(set(roles))


def bootstrap_development_tenant(
    session: Session, settings: Settings
) -> dict[str, object]:
    _require_development_mode(settings)
    roles = parse_development_roles(settings.development_roles)
    organization_id = settings.development_organization_id
    subject_id = settings.development_subject_id
    ensure_sqlite_write_transaction(session)

    organization = session.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
    )
    created_organization = organization is None
    if organization is None:
        try:
            with session.begin_nested():
                organization = Organization(
                    id=organization_id,
                    entra_tenant_id=f"development-{organization_id}",
                    name=settings.development_organization_name,
                )
                session.add(organization)
                session.flush()
        except IntegrityError:
            session.expire_all()
            organization = session.scalar(
                select(Organization)
                .where(Organization.id == organization_id)
                .with_for_update()
            )
            if organization is None:
                raise
            created_organization = False
    if organization.entra_tenant_id != f"development-{organization_id}":
        raise DevelopmentBootstrapInvalid(
            "configured development organization has a conflicting tenant marker"
        )

    membership = session.get(Membership, (organization_id, subject_id))
    created_membership = membership is None
    if membership is None:
        session.add(
            Membership(
                organization_id=organization_id,
                subject_id=subject_id,
                roles_json=roles,
            )
        )
    else:
        membership.roles_json = roles
    session.flush()

    return {
        "ok": True,
        "organization_id": organization_id,
        "subject_id": subject_id,
        "roles": roles,
        "created_organization": created_organization,
        "created_membership": created_membership,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def parser() -> argparse.ArgumentParser:
    result = _Parser(
        description="Create the development organization and membership.",
    )
    result.add_argument(
        "--with-sample-designs",
        action="store_true",
        help="insert missing fictional draft sample designs",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        settings = get_settings()
        _require_development_mode(settings)
        if args.with_sample_designs:
            roles = parse_development_roles(settings.development_roles)
            if "author" not in roles:
                raise DevelopmentBootstrapInvalid(
                    "--with-sample-designs requires the configured development "
                    "identity to have the author role"
                )
        with session_scope() as session:
            result = bootstrap_development_tenant(session, settings)
            if args.with_sample_designs:
                samples = seed_sample_designs(
                    session,
                    organization_id=settings.development_organization_id,
                    actor_id=settings.development_subject_id,
                )
                result["sample_designs"] = [
                    {
                        "id": sample.design_id,
                        "template": sample.template_key,
                        "created": sample.created,
                    }
                    for sample in samples
                ]
    except (
        DevelopmentBootstrapNotAllowed,
        DevelopmentBootstrapInvalid,
        SampleDesignSeedInvalid,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "code": "development-bootstrap-refused",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
