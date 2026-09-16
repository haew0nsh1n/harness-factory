from contextlib import asynccontextmanager
from collections.abc import Callable

from fastapi import FastAPI

from harness_factory import __version__

from web.api.audit.routes import router as audit_router
from web.api.builds.routes import router as builds_router
from web.api.builds.storage import FileArtifactStorage
from web.api.config import Settings, get_settings
from web.api.db import create_session_factory
from web.api.designs.routes import router as designs_router
from web.api.distribution.routes import router as distribution_router
from web.api.errors import install_exception_handlers
from web.api.identity.entra import EntraTokenValidator
from web.api.identity.routes import router as identity_router
from web.api.interviews.azure import AzureOpenAIInterviewModel
from web.api.interviews.model import InterviewModel
from web.api.interviews.routes import router as interviews_router
from web.api.registry.routes import router as registry_router


class InsecureDevelopmentAuthNotAllowed(RuntimeError):
    """Raised when development auth is requested without an explicit opt-in."""


def _require_development_auth_opt_in(settings: Settings) -> None:
    if settings.auth_mode != "development":
        return
    if settings.allow_insecure_development_auth:
        return
    raise InsecureDevelopmentAuthNotAllowed(
        "HF_AUTH_MODE=development accepts unverified request headers as identity. "
        "Set HF_ALLOW_INSECURE_DEVELOPMENT_AUTH=true to opt in on a trusted "
        "loopback-only host, or use HF_AUTH_MODE=entra."
    )


def create_app(
    settings: Settings | None = None,
    *,
    interview_model_factory: Callable[[Settings], InterviewModel] = (
        AzureOpenAIInterviewModel
    ),
) -> FastAPI:
    configured_settings = settings or get_settings()
    interview_model = interview_model_factory(configured_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await interview_model.close()

    app = FastAPI(title="Harness Factory Web", lifespan=lifespan)
    install_exception_handlers(app)
    app.state.settings = configured_settings
    app.state.interview_model = interview_model
    _require_development_auth_opt_in(app.state.settings)
    app.state.artifact_storage = FileArtifactStorage(app.state.settings.artifact_root)
    app.state.engine, app.state.session_factory = create_session_factory(
        app.state.settings
    )
    app.state.entra_validator = (
        EntraTokenValidator.from_settings(app.state.settings)
        if app.state.settings.auth_mode == "entra"
        else None
    )
    app.include_router(identity_router)
    app.include_router(builds_router)
    app.include_router(designs_router)
    app.include_router(registry_router)
    app.include_router(distribution_router)
    app.include_router(interviews_router)
    if app.state.settings.auth_mode == "development":
        app.include_router(audit_router)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "service": "harness-factory-web",
            "version": __version__,
        }

    return app
