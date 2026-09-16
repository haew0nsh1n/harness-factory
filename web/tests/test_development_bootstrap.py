from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from web.api.builds.storage import FileArtifactStorage
from web.api.config import Settings, get_settings
from web.api.db import Base, create_session_factory
from web.api.designs.digest import canonical_json_bytes
from web.api.designs.models import HarnessDesign
from web.api.distribution.service import DistributionService
from web.api.main import create_app
from web.api.organizations.bootstrap import (
    DevelopmentBootstrapInvalid,
    DevelopmentBootstrapNotAllowed,
    bootstrap_development_tenant,
    main,
)
from web.api.organizations.models import Membership, Organization
from web.api.registry.models import Asset, AssetVersion
from web.api.registry.repository import RegistryRepository


def development_settings(database_url: str, **overrides) -> Settings:
    return Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=database_url,
        **overrides,
    )


@pytest.fixture
def bootstrap_database(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'bootstrap.db'}"
    settings = development_settings(database_url)
    engine, _ = create_session_factory(settings)
    Base.metadata.create_all(engine)
    engine.dispose()
    return database_url


def test_bootstrap_creates_organization_and_membership(bootstrap_database) -> None:
    settings = development_settings(bootstrap_database)
    engine, factory = create_session_factory(settings)

    with factory() as session:
        result = bootstrap_development_tenant(session, settings)
        session.commit()

    assert result["created_organization"] is True
    assert result["created_membership"] is True
    assert result["organization_id"] == "local-dev"
    assert result["subject_id"] == "portal-dev"
    assert "registry-admin" in result["roles"]

    with Session(engine) as session:
        organization = session.get(Organization, "local-dev")
        membership = session.get(Membership, ("local-dev", "portal-dev"))

    assert organization is not None
    assert organization.entra_tenant_id == "development-local-dev"
    assert membership is not None
    assert "author" in membership.roles_json
    engine.dispose()


def test_bootstrap_is_idempotent(bootstrap_database) -> None:
    settings = development_settings(bootstrap_database)
    engine, factory = create_session_factory(settings)

    with factory() as session:
        bootstrap_development_tenant(session, settings)
        session.commit()
    with factory() as session:
        second = bootstrap_development_tenant(session, settings)
        session.commit()

    assert second["created_organization"] is False
    assert second["created_membership"] is False

    with Session(engine) as session:
        assert session.query(Organization).count() == 1
        assert session.query(Membership).count() == 1
    engine.dispose()


def test_fresh_bootstrap_rolls_back_organization_and_membership(
    bootstrap_database,
) -> None:
    settings = development_settings(bootstrap_database)
    engine, factory = create_session_factory(settings)

    with factory() as session:
        bootstrap_development_tenant(session, settings)
        session.rollback()

    with Session(engine) as session:
        assert session.query(Organization).count() == 0
        assert session.query(Membership).count() == 0
    engine.dispose()


def test_bootstrap_with_samples_is_explicit_and_idempotent(
    bootstrap_database,
) -> None:
    settings = development_settings(bootstrap_database)
    engine, factory = create_session_factory(settings)

    with factory() as session:
        plain = bootstrap_development_tenant(session, settings)
        session.commit()

    assert "sample_designs" not in plain
    with Session(engine) as session:
        assert session.query(HarnessDesign).count() == 0

    with factory() as session:
        bootstrap_development_tenant(session, settings)
        from web.api.designs.samples import seed_sample_designs

        first = seed_sample_designs(
            session,
            organization_id=settings.development_organization_id,
            actor_id=settings.development_subject_id,
        )
        session.commit()
    with factory() as session:
        bootstrap_development_tenant(session, settings)
        second = seed_sample_designs(
            session,
            organization_id=settings.development_organization_id,
            actor_id=settings.development_subject_id,
        )
        session.commit()

    assert all(result.created for result in first)
    assert not any(result.created for result in second)
    with Session(engine) as session:
        assert session.query(HarnessDesign).count() == 4
    engine.dispose()


def test_sample_registry_seed_creates_published_assets_idempotently(
    bootstrap_database,
    tmp_path,
) -> None:
    settings = development_settings(bootstrap_database)
    artifact_root = tmp_path / "artifacts"
    engine, factory = create_session_factory(settings)

    with factory() as session:
        bootstrap_development_tenant(session, settings)
        from web.api.registry.samples import seed_sample_registry

        first = seed_sample_registry(
            session,
            organization_id=settings.development_organization_id,
            actor_id=settings.development_subject_id,
            artifact_root=artifact_root,
        )
        session.commit()
    with factory() as session:
        second = seed_sample_registry(
            session,
            organization_id=settings.development_organization_id,
            actor_id=settings.development_subject_id,
            artifact_root=artifact_root,
        )
        session.commit()

    assert [result.template_key for result in first] == [
        "issue-planning",
        "test-first-implementation",
        "code-review",
        "manual-handoff",
    ]
    assert all(result.created for result in first)
    assert not any(result.created for result in second)

    with Session(engine) as session:
        assets = session.query(Asset).order_by(Asset.slug).all()
        versions = session.query(AssetVersion).order_by(AssetVersion.asset_id).all()
        assets_by_id = {asset.id: asset for asset in assets}

        assert [asset.slug for asset in assets] == [
            "code-review",
            "issue-planning",
            "manual-handoff",
            "test-first-implementation",
        ]
        assert len(versions) == 4
        assert all(version.version == "1.0.0" for version in versions)
        assert all(version.status == "published" for version in versions)
        assert all(version.channel == "stable" for version in versions)

        service = DistributionService(
            repository=RegistryRepository(session),
            storage=FileArtifactStorage(artifact_root),
        )
        for version in versions:
            assert version.digest == hashlib.sha256(
                canonical_json_bytes(version.manifest_json)
            ).hexdigest()
            artifact_path = artifact_root / version.artifact_key
            assert artifact_path.is_file()
            assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == (
                version.artifact_digest
            )
            prepared = service.prepare("local-dev", version.id)
            assert prepared is not None
            assert prepared.metadata.slug == assets_by_id[version.asset_id].slug
            assert prepared.metadata.version == "1.0.0"
            assert prepared.metadata.artifact_sha256 == version.artifact_digest
            prepared.close()
    engine.dispose()


def test_concurrent_fresh_bootstrap_with_samples_is_duplicate_free(
    bootstrap_database,
) -> None:
    settings = development_settings(bootstrap_database)
    engine, factory = create_session_factory(settings)
    barrier = Barrier(2)

    def run_bootstrap() -> list[bool]:
        with factory() as session:
            barrier.wait()
            bootstrap_development_tenant(session, settings)
            from web.api.designs.samples import seed_sample_designs

            samples = seed_sample_designs(
                session,
                organization_id=settings.development_organization_id,
                actor_id=settings.development_subject_id,
            )
            session.commit()
            return [sample.created for sample in samples]

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: run_bootstrap(), range(2)))

    assert sum(sum(outcome) for outcome in outcomes) == 4
    with Session(engine) as session:
        assert session.query(Organization).count() == 1
        assert session.query(Membership).count() == 1
        assert session.query(HarnessDesign).count() == 4
    engine.dispose()


def test_bootstrap_refuses_outside_development_mode(bootstrap_database) -> None:
    settings = Settings(
        auth_mode="entra",
        database_url=bootstrap_database,
        entra_tenant_id="tenant-123",
        entra_client_id="client-123",
        entra_jwks_url="https://entra.example.test/discovery/keys",
    )
    _, factory = create_session_factory(settings)

    with factory() as session:
        with pytest.raises(DevelopmentBootstrapNotAllowed):
            bootstrap_development_tenant(session, settings)


def test_bootstrap_refuses_without_insecure_opt_in(bootstrap_database) -> None:
    settings = Settings(auth_mode="development", database_url=bootstrap_database)
    _, factory = create_session_factory(settings)

    with factory() as session:
        with pytest.raises(DevelopmentBootstrapNotAllowed):
            bootstrap_development_tenant(session, settings)


def test_bootstrap_rejects_unknown_roles(bootstrap_database) -> None:
    settings = development_settings(
        bootstrap_database, development_roles="author,superuser"
    )
    _, factory = create_session_factory(settings)

    with factory() as session:
        with pytest.raises(DevelopmentBootstrapInvalid):
            bootstrap_development_tenant(session, settings)


def test_bootstrap_rejects_tenant_marker_before_membership_mutation(
    bootstrap_database,
) -> None:
    settings = development_settings(bootstrap_database)
    engine, factory = create_session_factory(settings)
    with factory.begin() as session:
        session.add(
            Organization(
                id="local-dev",
                entra_tenant_id="real-tenant",
                name="Existing Organization",
            )
        )

    with factory() as session:
        with pytest.raises(DevelopmentBootstrapInvalid):
            bootstrap_development_tenant(session, settings)
        session.rollback()

    with Session(engine) as session:
        assert session.query(Membership).count() == 0
        assert session.get(Organization, "local-dev").entra_tenant_id == "real-tenant"
    engine.dispose()


def test_bootstrap_cli_reports_json(bootstrap_database, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HF_AUTH_MODE", "development")
    monkeypatch.setenv("HF_ALLOW_INSECURE_DEVELOPMENT_AUTH", "true")
    monkeypatch.setenv("HF_DATABASE_URL", bootstrap_database)
    get_settings.cache_clear()

    try:
        assert main([]) == 0
        payload = json.loads(capsys.readouterr().out)
    finally:
        get_settings.cache_clear()

    assert payload["ok"] is True
    assert payload["organization_id"] == "local-dev"
    assert "sample_designs" not in payload


def test_bootstrap_cli_with_sample_designs_reports_seed_results(
    bootstrap_database, tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HF_AUTH_MODE", "development")
    monkeypatch.setenv("HF_ALLOW_INSECURE_DEVELOPMENT_AUTH", "true")
    monkeypatch.setenv("HF_DATABASE_URL", bootstrap_database)
    monkeypatch.setenv("HF_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    try:
        assert main(["--with-sample-designs"]) == 0
        payload = json.loads(capsys.readouterr().out)
    finally:
        get_settings.cache_clear()

    assert len(payload["sample_designs"]) == 8
    assert all(sample["created"] for sample in payload["sample_designs"])
    assert {sample["language"] for sample in payload["sample_designs"]} == {"ko", "en"}
    assert [sample["template"] for sample in payload["sample_registry"]] == [
        "issue-planning",
        "test-first-implementation",
        "code-review",
        "manual-handoff",
        "issue-planning",
        "test-first-implementation",
        "code-review",
        "manual-handoff",
    ]
    assert {sample["language"] for sample in payload["sample_registry"]} == {"ko", "en"}
    assert all(sample["created"] for sample in payload["sample_registry"])


def test_bootstrap_cli_rejects_samples_without_author_before_mutation(
    bootstrap_database, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HF_AUTH_MODE", "development")
    monkeypatch.setenv("HF_ALLOW_INSECURE_DEVELOPMENT_AUTH", "true")
    monkeypatch.setenv("HF_DATABASE_URL", bootstrap_database)
    monkeypatch.setenv("HF_DEVELOPMENT_ROLES", "reviewer")
    get_settings.cache_clear()

    try:
        assert main(["--with-sample-designs"]) == 1
        captured = capsys.readouterr()
    finally:
        get_settings.cache_clear()

    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "development-bootstrap-refused"

    settings = development_settings(bootstrap_database)
    engine, _ = create_session_factory(settings)
    with Session(engine) as session:
        assert session.query(Organization).count() == 0
        assert session.query(Membership).count() == 0
        assert session.query(HarnessDesign).count() == 0
    engine.dispose()


def test_bootstrap_cli_refuses_production_mode(
    bootstrap_database, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HF_AUTH_MODE", "entra")
    monkeypatch.setenv("HF_DATABASE_URL", bootstrap_database)
    get_settings.cache_clear()

    try:
        assert main(["--with-sample-designs"]) == 1
        captured = capsys.readouterr()
    finally:
        get_settings.cache_clear()

    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "development-bootstrap-refused"


def test_bootstrapped_registry_samples_are_visible_and_downloadable_via_api(
    bootstrap_database,
    tmp_path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    settings = development_settings(
        bootstrap_database,
        artifact_root=artifact_root,
    )
    app = create_app(settings)

    with Session(app.state.engine) as session:
        bootstrap_development_tenant(session, settings)
        from web.api.registry.samples import seed_sample_registry

        seed_sample_registry(
            session,
            organization_id=settings.development_organization_id,
            actor_id=settings.development_subject_id,
            artifact_root=artifact_root,
        )
        session.commit()

    headers = {
        "X-HF-Organization": settings.development_organization_id,
        "X-HF-Subject": settings.development_subject_id,
        "X-HF-Roles": "author,registry-admin,developer",
    }
    with TestClient(app) as client:
        list_response = client.get(
            "/api/registry/assets?type=workflow",
            headers=headers,
        )
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["ok"] is True
        assets = list_data["items"]
        assert len(assets) == 4
        assert [asset["slug"] for asset in assets] == [
            "code-review",
            "issue-planning",
            "manual-handoff",
            "test-first-implementation",
        ]

        sample_asset = next(
            asset for asset in assets if asset["slug"] == "issue-planning"
        )
        assert len(sample_asset["versions"]) == 1
        version = sample_asset["versions"][0]
        assert version["version"] == "1.0.0"
        assert version["status"] == "published"
        assert version["channel"] == "stable"

        manifest_response = client.get(
            f"/api/registry/versions/{version['id']}/manifest",
            headers=headers,
        )
        assert manifest_response.status_code == 200
        manifest_payload = manifest_response.json()
        assert manifest_payload["asset"]["slug"] == "issue-planning"
        assert manifest_payload["version"] == "1.0.0"

        delivery_response = client.get(
            f"/api/registry/versions/{version['id']}/delivery",
            headers=headers,
        )
        assert delivery_response.status_code == 200
        delivery_payload = delivery_response.json()
        assert delivery_payload["ok"] is True
        assert delivery_payload["delivery"]["slug"] == "issue-planning"
        assert delivery_payload["delivery"]["version"] == "1.0.0"

        artifact_response = client.get(
            f"/api/registry/versions/{version['id']}/artifact",
            headers=headers,
        )
        assert artifact_response.status_code == 200
        assert hashlib.sha256(artifact_response.content).hexdigest() == (
            version["artifact_sha256"]
        )
