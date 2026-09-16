from __future__ import annotations

from pathlib import Path

from web.acceptance.distribution_flow import (
    run_distribution_flow,
    running_http_app,
)
from web.api.builds.worker import BuildWorker
from web.api.config import Settings
from web.api.db import Base
from web.api.main import create_app
from web.api.organizations.bootstrap import bootstrap_development_tenant

FIXTURE_ROOT = Path(__file__).resolve().parents[2]


def test_http_backed_console_preview_apply_and_lifecycle_guards(
    tmp_path: Path,
    packaged_cli,
) -> None:
    settings = Settings(
        auth_mode="development",
        allow_insecure_development_auth=True,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'acceptance.db'}",
        catalog_root=FIXTURE_ROOT / "catalog",
        artifact_root=tmp_path / "artifacts",
        development_organization_id="local-dev",
        development_subject_id="portal-dev",
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
                require_postgres=False,
            )
    finally:
        worker.dispose()
        app.state.engine.dispose()

    assert result["operation"] == "distribution-acceptance"
    assert result["database"] == "sqlite"
    assert result["installed"] is True
    assert result["ready"] is False
    assert result["customer_evaluation"] == {"status": "missing"}
    assert result["cross_tenant"] == "not_found"
    assert result["revoked_install"] == "rejected"
    assert Path(packaged_cli.origins["hf_cli"]).is_relative_to(packaged_cli.root)
    assert Path(packaged_cli.origins["harness_factory"]).is_relative_to(
        packaged_cli.root
    )
