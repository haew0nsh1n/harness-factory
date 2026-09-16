from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_factory import load_json, validate, validate_scenarios
from web.api.designs.models import CONTENT_LANGUAGE_DEFAULT, CONTENT_LANGUAGES
from web.api.designs.repository import (
    HarnessDesignRepository,
    SeedDesignIdentityCollision,
    ensure_sqlite_write_transaction,
)
from web.api.designs.schemas import HarnessDesignRequest
from web.api.organizations.models import Organization

SAMPLE_DESIGN_NAMESPACE = UUID("bd22cefa-9cd6-4a5d-9b3a-48602b494cf8")
SAMPLE_TEMPLATE_KEYS = (
    "issue-planning",
    "test-first-implementation",
    "code-review",
    "manual-handoff",
)


class SampleDesignSeedInvalid(RuntimeError):
    pass


@dataclass(frozen=True)
class SampleDesignSeedResult:
    design_id: str
    template_key: str
    created: bool


def sample_design_id(
    organization_id: str, template_key: str, language: str = CONTENT_LANGUAGE_DEFAULT
) -> str:
    # Keep the default-language id formula unchanged so existing rows stay stable.
    key = f"{organization_id}:{template_key}"
    if language != CONTENT_LANGUAGE_DEFAULT:
        key = f"{key}:{language}"
    return str(uuid5(SAMPLE_DESIGN_NAMESPACE, key))


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fixture_root(template_key: str, language: str) -> Path:
    base = _repository_root() / "examples" / "sample-workflows" / template_key
    if language == CONTENT_LANGUAGE_DEFAULT:
        return base
    return base / language


def _load_request(
    template_key: str, language: str = CONTENT_LANGUAGE_DEFAULT
) -> HarnessDesignRequest:
    root = _repository_root()
    fixture_root = _fixture_root(template_key, language)
    catalog_path = root / "catalog" / "catalog.json"
    profile = load_json(fixture_root / "profile.json")
    workflow = load_json(fixture_root / "workflow.json")
    scenarios = load_json(fixture_root / "scenarios.json")
    catalog = load_json(catalog_path)
    validate(profile, workflow, catalog, catalog_path.parent)
    validate_scenarios(scenarios, workflow)
    return HarnessDesignRequest(
        customer_id=profile["customer_id"],
        name=workflow["name"],
        language=language,
        profile=profile,
        workflow=workflow,
        scenarios=scenarios,
        catalog=catalog,
    )


def seed_sample_designs(
    session: Session,
    *,
    organization_id: str,
    actor_id: str,
    language: str = CONTENT_LANGUAGE_DEFAULT,
) -> list[SampleDesignSeedResult]:
    if language not in CONTENT_LANGUAGES:
        raise SampleDesignSeedInvalid(f"unsupported sample language: {language}")
    ensure_sqlite_write_transaction(session)
    organization = session.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
    )
    if organization is None:
        raise SampleDesignSeedInvalid(
            f"development organization does not exist: {organization_id}"
        )
    expected_tenant = f"development-{organization_id}"
    if organization.entra_tenant_id != expected_tenant:
        raise SampleDesignSeedInvalid(
            "configured development organization has a conflicting tenant marker"
        )

    repository = HarnessDesignRepository(session)
    results = []
    for template_key in SAMPLE_TEMPLATE_KEYS:
        try:
            design, created = repository.insert_seed_if_missing(
                design_id=sample_design_id(organization_id, template_key, language),
                organization_id=organization_id,
                actor_id=actor_id,
                request=_load_request(template_key, language),
            )
        except SeedDesignIdentityCollision as exc:
            raise SampleDesignSeedInvalid(
                f"sample design identity collision: {exc.design_id}"
            ) from exc
        results.append(
            SampleDesignSeedResult(
                design_id=design.id,
                template_key=template_key,
                created=created,
            )
        )
    return results
