from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.types import Receive, Scope, Send

from web.api.db import get_session
from web.api.distribution.service import (
    STREAM_CHUNK_BYTES,
    DeliveryArtifactError,
    DistributionService,
    PreparedDelivery,
)
from web.api.identity.dependencies import require_roles
from web.api.identity.models import Actor
from web.api.registry.repository import RegistryRepository

router = APIRouter(prefix="/api/registry/versions", tags=["distribution"])


def get_distribution_service(
    request: Request,
    session: Session = Depends(get_session),
) -> DistributionService:
    return DistributionService(
        repository=RegistryRepository(session),
        storage=request.app.state.artifact_storage,
    )


def _prepare_or_404(
    service: DistributionService,
    actor: Actor,
    version_id: str,
) -> PreparedDelivery:
    prepared = service.prepare(actor.organization_id, version_id)
    if prepared is None:
        raise HTTPException(status_code=404, detail="version not found")
    return prepared


def _artifact_error(error: DeliveryArtifactError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": error.message, "code": error.code},
    )


@router.get("/{version_id}/delivery")
def get_delivery_metadata(
    version_id: str,
    actor: Actor = Depends(require_roles("developer", "org-admin")),
    service: DistributionService = Depends(get_distribution_service),
):
    try:
        prepared = _prepare_or_404(service, actor, version_id)
    except DeliveryArtifactError as exc:
        return _artifact_error(exc)
    try:
        return {
            "ok": True,
            "delivery": prepared.metadata.model_dump(mode="json"),
        }
    finally:
        prepared.close()


def _stream_prepared(prepared: PreparedDelivery) -> Iterator[bytes]:
    while chunk := prepared.stream.read(STREAM_CHUNK_BYTES):
        yield chunk


class PreparedStreamingResponse(StreamingResponse):
    def __init__(self, prepared: PreparedDelivery, **kwargs) -> None:
        self._prepared = prepared
        super().__init__(_stream_prepared(prepared), **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._prepared.close()


@router.get("/{version_id}/artifact")
def download_artifact(
    version_id: str,
    actor: Actor = Depends(require_roles("developer", "org-admin")),
    service: DistributionService = Depends(get_distribution_service),
):
    try:
        prepared = _prepare_or_404(service, actor, version_id)
    except DeliveryArtifactError as exc:
        return _artifact_error(exc)
    metadata = prepared.metadata
    try:
        return PreparedStreamingResponse(
            prepared,
            media_type="application/x-tar",
            headers={
                "Content-Length": str(metadata.artifact_size),
                "Content-Disposition": (
                    f'attachment; filename="{metadata.slug}-{metadata.version}.tar"'
                ),
            },
        )
    except BaseException:
        prepared.close()
        raise
