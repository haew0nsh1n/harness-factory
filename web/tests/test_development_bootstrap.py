from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from web.api.config import Settings, get_settings
from web.api.db import Base, create_session_factory
from web.api.organizations.bootstrap import (
    DevelopmentBootstrapInvalid,
    DevelopmentBootstrapNotAllowed,
    bootstrap_development_tenant,
    main,
)
from web.api.organizations.models import Membership, Organization


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


def test_bootstrap_cli_refuses_production_mode(
    bootstrap_database, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("HF_AUTH_MODE", "entra")
    monkeypatch.setenv("HF_DATABASE_URL", bootstrap_database)
    get_settings.cache_clear()

    try:
        assert main([]) == 1
        captured = capsys.readouterr()
    finally:
        get_settings.cache_clear()

    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "development-bootstrap-refused"
