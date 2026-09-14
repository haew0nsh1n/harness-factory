from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from web.api.audit.service import AuditService
from web.api.db import get_session
from web.api.identity.dependencies import get_actor, require_roles
from web.api.identity.models import Actor
from web.api.registry.repository import RegistryRepository
from web.api.registry.schemas import (
    AssetCreate,
    PublishRequest,
    RevokeRequest,
    VersionCreate,
    VersionReviewRequest,
    to_asset_response,
    to_asset_summary_response,
    to_asset_version_response,
)
from web.api.registry.service import (
    ArtifactVerificationFailed,
    AssetSlugConflict,
    AssetVersionConflict,
    InvalidRegistryLifecycle,
    RegistryService,
    StaleRegistryDigest,
)

router = APIRouter(prefix="/api/registry", tags=["registry"])


def get_registry_service(
    request: Request,
    session: Session = Depends(get_session),
) -> RegistryService:
    return RegistryService(
        repository=RegistryRepository(session),
        audit_service=AuditService(session),
        storage=request.app.state.artifact_storage,
    )


def _include_unpublished(actor: Actor) -> bool:
    return bool(
        actor.roles.intersection({"author", "reviewer", "registry-admin", "org-admin"})
    )


@router.post("/assets", status_code=201)
def create_asset(
    asset_request: AssetCreate,
    actor: Actor = Depends(require_roles("registry-admin")),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    try:
        asset = service.create_workflow_asset(
            actor.organization_id,
            actor.subject_id,
            asset_request,
        )
    except AssetSlugConflict as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": exc.message, "code": "conflict"},
        )
    return {
        "ok": True,
        "asset": {
            "id": asset.id,
            "organization_id": asset.organization_id,
            "type": asset.kind,
            "slug": asset.slug,
            "name": asset.name,
            "description": asset.description,
            "owner_subject_id": asset.owner_subject_id,
            "visibility": asset.visibility,
            "lifecycle": asset.lifecycle,
        },
    }


@router.get("/assets")
def search_assets(
    query: str | None = None,
    type: Literal["workflow"] | None = None,
    channel: Literal["pilot", "stable"] | None = None,
    actor: Actor = Depends(get_actor),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    items = [
        to_asset_summary_response(asset, versions).model_dump(mode="json")
        for asset, versions in service.search_assets(
            actor.organization_id,
            kind=type,
            query=query,
            channel=channel,
            include_unpublished=_include_unpublished(actor),
        )
    ]
    return {"ok": True, "items": items}


@router.get("/assets/{slug}")
def get_asset(
    slug: str,
    actor: Actor = Depends(get_actor),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    item = service.get_asset_detail(
        actor.organization_id,
        slug,
        include_unpublished=_include_unpublished(actor),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="asset not found")
    asset, versions = item
    return {"ok": True, "asset": to_asset_response(asset, versions).model_dump(mode="json")}


@router.post("/assets/{asset_id}/versions", status_code=201)
def create_version(
    asset_id: str,
    version_request: VersionCreate,
    actor: Actor = Depends(require_roles("author", "registry-admin")),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    try:
        version = service.create_workflow_version(
            actor.organization_id,
            actor.subject_id,
            asset_id,
            version_request,
        )
    except InvalidRegistryLifecycle as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": exc.message,
                "code": "invalid_lifecycle",
            },
        )
    except StaleRegistryDigest as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": exc.message, "code": "stale_digest"},
        )
    except ArtifactVerificationFailed as exc:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": exc.message, "code": exc.code},
        )
    except AssetVersionConflict as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": exc.message, "code": "conflict"},
        )
    if version is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"ok": True, "version": to_asset_version_response(version).model_dump(mode="json")}


@router.post("/versions/{version_id}/reviews")
def review_version(
    version_id: str,
    review_request: VersionReviewRequest,
    actor: Actor = Depends(require_roles("reviewer")),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    try:
        version = service.review_version(
            actor.organization_id,
            actor.subject_id,
            version_id,
            review_request.expected_digest,
            review_request.decision,
        )
    except InvalidRegistryLifecycle as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": exc.message,
                "code": "invalid_lifecycle",
            },
        )
    except StaleRegistryDigest as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": exc.message, "code": "stale_digest"},
        )
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    return {"ok": True, "version": to_asset_version_response(version).model_dump(mode="json")}


@router.post("/versions/{version_id}/publish")
def publish_version(
    version_id: str,
    publish_request: PublishRequest,
    actor: Actor = Depends(require_roles("registry-admin")),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    try:
        version = service.publish_workflow_version(
            actor.organization_id,
            actor.subject_id,
            version_id,
            publish_request,
        )
    except InvalidRegistryLifecycle as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": exc.message,
                "code": "invalid_lifecycle",
            },
        )
    except StaleRegistryDigest as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": exc.message, "code": "stale_digest"},
        )
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    return {"ok": True, "version": to_asset_version_response(version).model_dump(mode="json")}


@router.post("/versions/{version_id}/revoke")
def revoke_version(
    version_id: str,
    revoke_request: RevokeRequest,
    actor: Actor = Depends(require_roles("registry-admin")),
    service: RegistryService = Depends(get_registry_service),
) -> dict[str, object]:
    try:
        version = service.revoke_version(
            actor.organization_id,
            actor.subject_id,
            version_id,
            revoke_request.expected_digest,
        )
    except InvalidRegistryLifecycle as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": exc.message,
                "code": "invalid_lifecycle",
            },
        )
    except StaleRegistryDigest as exc:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": exc.message, "code": "stale_digest"},
        )
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    return {"ok": True, "version": to_asset_version_response(version).model_dump(mode="json")}


@router.get("/versions/{version_id}/manifest")
def get_manifest(
    version_id: str,
    actor: Actor = Depends(
        require_roles("developer", "reviewer", "registry-admin", "org-admin")
    ),
    service: RegistryService = Depends(get_registry_service),
):
    manifest = service.get_manifest(
        actor.organization_id,
        version_id,
        include_unpublished=_include_unpublished(actor),
    )
    if manifest is None:
        raise HTTPException(status_code=404, detail="version not found")
    return manifest
