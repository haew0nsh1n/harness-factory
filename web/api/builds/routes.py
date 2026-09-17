from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from web.api.builds.repository import BuildJobRepository
from web.api.builds.schemas import BuildSubmissionRequest, to_build_response
from web.api.builds.service import (
    BuildDigestMismatch,
    BuildService,
    InvalidBuildLifecycle,
)
from web.api.db import get_session
from web.api.identity.dependencies import get_actor, require_roles
from web.api.identity.models import Actor

router = APIRouter(prefix="/api", tags=["builds"])

ARTIFACT_STREAM_CHUNK_BYTES = 256 * 1024


def get_build_service(
    request: Request,
    session: Session = Depends(get_session),
) -> BuildService:
    settings = request.app.state.settings
    return BuildService(
        repository=BuildJobRepository(session),
        settings=settings,
        storage=request.app.state.artifact_storage,
    )


@router.post("/designs/{design_id}/builds", status_code=202)
def submit_build(
    design_id: str,
    build_request: BuildSubmissionRequest,
    actor: Actor = Depends(require_roles("author")),
    service: BuildService = Depends(get_build_service),
) -> dict[str, object]:
    try:
        build = service.submit(
            actor,
            design_id,
            build_request.expected_digest,
        )
    except InvalidBuildLifecycle as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": exc.message,
                "code": "invalid_lifecycle",
            },
        )
    except BuildDigestMismatch as exc:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": exc.message,
                "code": "stale_digest",
            },
        )
    if build is None:
        raise HTTPException(status_code=404, detail="design not found")
    return {"ok": True, "build": to_build_response(build).model_dump(mode="json")}


@router.get("/builds/{build_id}")
def get_build(
    build_id: str,
    actor: Actor = Depends(get_actor),
    service: BuildService = Depends(get_build_service),
) -> dict[str, object]:
    build = service.get(actor.organization_id, build_id)
    if build is None:
        raise HTTPException(status_code=404, detail="build not found")
    return {"ok": True, "build": to_build_response(build).model_dump(mode="json")}


@router.get("/designs/{design_id}/builds")
def list_design_builds(
    design_id: str,
    actor: Actor = Depends(get_actor),
    service: BuildService = Depends(get_build_service),
) -> dict[str, object]:
    builds = service.list_recent(actor.organization_id, design_id, limit=3)
    if builds is None:
        raise HTTPException(status_code=404, detail="design not found")
    return {
        "ok": True,
        "builds": [
            to_build_response(build).model_dump(mode="json") for build in builds
        ],
    }


@router.get("/designs/{design_id}/builds/artifact")
def download_build_artifact(
    design_id: str,
    actor: Actor = Depends(require_roles("author", "developer", "org-admin")),
    service: BuildService = Depends(get_build_service),
) -> StreamingResponse:
    result = service.open_artifact(actor.organization_id, design_id)
    if result is None:
        raise HTTPException(status_code=404, detail="build artifact not found")
    stream, filename = result

    def _iter() -> Iterator[bytes]:
        try:
            while chunk := stream.read(ARTIFACT_STREAM_CHUNK_BYTES):
                yield chunk
        finally:
            stream.close()

    return StreamingResponse(
        _iter(),
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
