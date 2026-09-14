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
