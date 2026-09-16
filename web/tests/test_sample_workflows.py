from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harness_factory import load_json, validate, validate_scenarios
from web.api.builds.models import BuildJob
from web.api.config import Settings
from web.api.db import Base, create_session_factory
from web.api.designs.digest import design_digest
from web.api.designs.models import Approval, HarnessDesign
from web.api.designs.samples import (
    SAMPLE_TEMPLATE_KEYS,
    SampleDesignSeedInvalid,
    sample_design_id,
    seed_sample_designs,
)
from web.api.organizations.models import Membership, Organization
from web.api.registry.models import Asset, AssetVersion

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROOT = ROOT / "examples" / "sample-workflows"


@pytest.fixture
def sample_database(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'samples.db'}"
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=database_url,
    )
    engine, factory = create_session_factory(settings)
    Base.metadata.create_all(engine)
    with factory.begin() as session:
        session.add_all(
            [
                Organization(
                    id="local-dev",
                    entra_tenant_id="development-local-dev",
                    name="Local Development",
                ),
                Organization(
                    id="user-tenant",
                    entra_tenant_id="tenant-user",
                    name="Existing User Tenant",
                ),
            ]
        )
    yield engine, factory
    engine.dispose()


def _seed(factory, organization_id: str = "local-dev"):
    with factory.begin() as session:
        return seed_sample_designs(
            session,
            organization_id=organization_id,
            actor_id="portal-dev",
        )


def test_sample_source_fixtures_validate_against_full_catalog() -> None:
    catalog_path = ROOT / "catalog" / "catalog.json"
    catalog = load_json(catalog_path)

    for template_key in SAMPLE_TEMPLATE_KEYS:
        fixture_root = SAMPLE_ROOT / template_key
        profile = load_json(fixture_root / "profile.json")
        workflow = load_json(fixture_root / "workflow.json")
        scenarios = load_json(fixture_root / "scenarios.json")

        validate(profile, workflow, catalog, catalog_path.parent)
        validate_scenarios(scenarios, workflow)
        assert workflow["approved"] == {
            "by": "fictional-fixture-author-not-customer-approval",
            "at": "2026-09-16T00:00:00+09:00",
        }


def test_seed_creates_four_draft_revision_one_designs(sample_database) -> None:
    engine, factory = sample_database
    results = _seed(factory)

    assert [result.template_key for result in results] == list(SAMPLE_TEMPLATE_KEYS)
    assert all(result.created for result in results)

    with Session(engine) as session:
        designs = session.scalars(
            select(HarnessDesign).order_by(HarnessDesign.name)
        ).all()
        assert len(designs) == 4
        assert {design.name for design in designs} == {
            "이슈 명확화와 실행 계획",
            "테스트 우선 구현",
            "근거 기반 코드 리뷰",
            "리뷰 후 수동 PR 인계",
        }
        for design in designs:
            assert design.status == "draft"
            assert design.revision == 1
            assert design.validation_findings_json is None
            assert design.created_by == "portal-dev"
            assert design.digest == design_digest(
                design.profile_json,
                design.workflow_json,
                design.scenarios_json,
                design.catalog_json,
            )
            assert design.catalog_json == load_json(ROOT / "catalog" / "catalog.json")

        assert session.scalar(select(func.count()).select_from(Approval)) == 0
        assert session.scalar(select(func.count()).select_from(BuildJob)) == 0
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(AssetVersion)) == 0


def test_repeat_and_partial_seed_preserve_existing_edits(sample_database) -> None:
    engine, factory = sample_database
    _seed(factory)
    edited_id = sample_design_id("local-dev", "issue-planning")
    missing_id = sample_design_id("local-dev", "code-review")
    edited_at = datetime(2025, 1, 2, 3, 4, tzinfo=UTC)

    with factory.begin() as session:
        edited = session.get(HarnessDesign, edited_id)
        edited.name = "사용자가 바꾼 이름"
        edited.status = "validated"
        edited.revision = 7
        edited.digest = "a" * 64
        edited.created_at = edited_at
        edited.updated_at = edited_at
        session.delete(session.get(HarnessDesign, missing_id))

    results = _seed(factory)
    assert [result.template_key for result in results if result.created] == [
        "code-review"
    ]

    with Session(engine) as session:
        edited = session.get(HarnessDesign, edited_id)
        assert edited.name == "사용자가 바꾼 이름"
        assert edited.status == "validated"
        assert edited.revision == 7
        assert edited.digest == "a" * 64
        assert edited.created_at == edited_at.replace(tzinfo=None)
        assert edited.updated_at == edited_at.replace(tzinfo=None)
        assert session.scalar(select(func.count()).select_from(HarnessDesign)) == 4


def test_concurrent_sqlite_seed_is_duplicate_free(sample_database) -> None:
    engine, factory = sample_database
    barrier = Barrier(2)

    def run_seed() -> list[bool]:
        with factory() as session:
            barrier.wait()
            results = seed_sample_designs(
                session,
                organization_id="local-dev",
                actor_id="portal-dev",
            )
            session.commit()
            return [result.created for result in results]

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: run_seed(), range(2)))

    assert sum(sum(outcome) for outcome in outcomes) == 4
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(HarnessDesign)) == 4


def test_seed_is_tenant_isolated_and_preserves_other_data(sample_database) -> None:
    engine, factory = sample_database
    existing = HarnessDesign(
        id="11111111-1111-4111-8111-111111111111",
        organization_id="user-tenant",
        customer_id="real-customer",
        name="Existing user design",
        profile_json={"kept": True},
        workflow_json={"kept": True},
        scenarios_json={"kept": True},
        catalog_json={"kept": True},
        validation_findings_json=[{"field": "x", "code": "y", "message": "z"}],
        revision=9,
        digest="b" * 64,
        status="validated",
        created_by="real-user",
    )
    with factory.begin() as session:
        session.add(existing)

    _seed(factory)

    with Session(engine) as session:
        stored = session.get(HarnessDesign, existing.id)
        assert stored.name == "Existing user design"
        assert stored.revision == 9
        assert stored.digest == "b" * 64
        assert (
            session.scalar(
                select(func.count())
                .select_from(HarnessDesign)
                .where(HarnessDesign.organization_id == "user-tenant")
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(HarnessDesign)
                .where(HarnessDesign.organization_id == "local-dev")
            )
            == 4
        )


def test_seed_rejects_non_development_tenant_marker(sample_database) -> None:
    engine, factory = sample_database

    with factory.begin() as session:
        with pytest.raises(SampleDesignSeedInvalid):
            seed_sample_designs(
                session,
                organization_id="user-tenant",
                actor_id="portal-dev",
            )

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(HarnessDesign)) == 0


def test_seed_rejects_deterministic_id_collision(sample_database) -> None:
    engine, factory = sample_database
    collision_id = sample_design_id("local-dev", "issue-planning")
    with factory.begin() as session:
        session.add(
            HarnessDesign(
                id=collision_id,
                organization_id="user-tenant",
                customer_id="real-customer",
                name="Unrelated design",
                profile_json={"kept": True},
                workflow_json={"kept": True},
                scenarios_json={"kept": True},
                catalog_json={"kept": True},
                validation_findings_json=None,
                revision=1,
                digest="c" * 64,
                status="draft",
                created_by="real-user",
            )
        )

    with factory.begin() as session:
        with pytest.raises(SampleDesignSeedInvalid):
            seed_sample_designs(
                session,
                organization_id="local-dev",
                actor_id="portal-dev",
            )

    with Session(engine) as session:
        collision = session.get(HarnessDesign, collision_id)
        assert collision.organization_id == "user-tenant"
        assert collision.name == "Unrelated design"
        assert (
            session.scalar(
                select(func.count())
                .select_from(HarnessDesign)
                .where(HarnessDesign.organization_id == "local-dev")
            )
            == 0
        )


def test_later_seed_collision_rolls_back_earlier_sample_inserts(
    sample_database,
) -> None:
    engine, factory = sample_database
    collision_id = sample_design_id("local-dev", "code-review")
    with factory.begin() as session:
        session.add(
            Membership(
                organization_id="local-dev",
                subject_id="portal-dev",
                roles_json=["author"],
            )
        )
        session.add(
            HarnessDesign(
                id=collision_id,
                organization_id="user-tenant",
                customer_id="real-customer",
                name="Unrelated design",
                profile_json={"kept": True},
                workflow_json={"kept": True},
                scenarios_json={"kept": True},
                catalog_json={"kept": True},
                validation_findings_json=None,
                revision=1,
                digest="d" * 64,
                status="draft",
                created_by="real-user",
            )
        )

    with factory() as session:
        with pytest.raises(SampleDesignSeedInvalid):
            seed_sample_designs(
                session,
                organization_id="local-dev",
                actor_id="portal-dev",
            )
        session.rollback()

    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(HarnessDesign)
                .where(HarnessDesign.organization_id == "local-dev")
            )
            == 0
        )
        assert session.get(HarnessDesign, collision_id).name == "Unrelated design"
