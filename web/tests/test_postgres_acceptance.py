"""PostgreSQL acceptance coverage.

Enabled only when ``HF_POSTGRES_TEST_URL`` points at a reachable PostgreSQL
database, for example the Compose database published on loopback::

    HF_POSTGRES_TEST_URL=postgresql+psycopg://hf:hf@127.0.0.1:5432/harness_factory \\
        .venv/bin/pytest web/tests/test_postgres_acceptance.py -v

The Compose stack itself is exercised with::

    docker compose exec api python -m web.acceptance.postgres_flow
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.acceptance.distribution_flow import (
    run_distribution_flow,
    running_http_app,
)
from web.acceptance.postgres_flow import HttpResult, run_flow
from web.api.builds.worker import BuildWorker
from web.api.config import Settings
from web.api.db import Base
from web.api.main import create_app
from web.api.organizations.bootstrap import bootstrap_development_tenant

FIXTURE_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_URL = os.environ.get("HF_POSTGRES_TEST_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set HF_POSTGRES_TEST_URL to run the PostgreSQL acceptance flow",
)


def client_transport(client: TestClient):
    def transport(
        method: str, path: str, headers: dict[str, str], body: object | None
    ) -> HttpResult:
        response = client.request(
            method,
            path,
            headers=headers,
            content=None if body is None else json.dumps(body),
        )
        payload = response.json() if response.content else None
        return HttpResult(response.status_code, payload)

    return transport


def test_full_lifecycle_against_postgresql(tmp_path) -> None:
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=POSTGRES_URL,
        catalog_root=FIXTURE_ROOT / "catalog",
        artifact_root=tmp_path / "artifacts",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        bootstrap_development_tenant(session, settings)
        session.commit()

    worker = BuildWorker(settings)
    try:
        with TestClient(app) as client:
            result = run_flow(
                settings=settings,
                examples_root=FIXTURE_ROOT / "examples",
                transport=client_transport(client),
                on_build_poll=worker.run_once,
                timeout_seconds=60.0,
            )
    finally:
        worker.dispose()
        app.state.engine.dispose()

    assert result["ok"] is True
    assert result["database"] == "postgresql"
    assert result["channel"] == "stable"


def test_http_cli_distribution_against_postgresql(tmp_path, packaged_cli) -> None:
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=POSTGRES_URL,
        catalog_root=FIXTURE_ROOT / "catalog",
        artifact_root=tmp_path / "artifacts",
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        bootstrap_development_tenant(session, settings)
        session.commit()

    worker = BuildWorker(settings)
    try:
        with running_http_app(app) as base_url:
            result = run_distribution_flow(
                settings=settings,
                workspace=tmp_path / "distribution",
                hf_executable=str(packaged_cli.hf),
                python_executable=str(packaged_cli.python),
                base_url=base_url,
                timeout_seconds=60,
                examples_root=FIXTURE_ROOT / "examples",
                on_build_poll=worker.run_once,
            )
    finally:
        worker.dispose()
        app.state.engine.dispose()

    assert result["database"] == "postgresql"
    assert result["installed"] is True
    assert result["ready"] is False
    assert result["customer_evaluation"] == {"status": "missing"}
    assert result["cross_tenant"] == "not_found"
    assert result["revoked_install"] == "rejected"
    assert Path(packaged_cli.origins["hf_cli"]).is_relative_to(packaged_cli.root)
    assert Path(packaged_cli.origins["harness_factory"]).is_relative_to(
        packaged_cli.root
    )
