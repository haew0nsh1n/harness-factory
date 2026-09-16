from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from web.api.audit.service import AuditService
from web.api.db import get_session
from web.api.designs.repository import HarnessDesignRepository
from web.api.designs.schemas import (
    DesignReviewRequest,
    HarnessDesignRequest,
    to_design_response,
)
from web.api.designs.service import (
    DesignService,
    DesignValidationFailure,
    InvalidDesignLifecycle,
    StaleDesignDigest,
)
from web.api.identity.dependencies import get_actor, require_roles
from web.api.identity.models import Actor

router = APIRouter(prefix="/api/designs", tags=["designs"])


def get_design_service(
    request: Request,
    session: Session = Depends(get_session),
) -> DesignService:
    return DesignService(
        repository=HarnessDesignRepository(session),
        settings=request.app.state.settings,
        audit_service=AuditService(session),
    )


@router.post("", status_code=201)
def create_design(
    design_request: HarnessDesignRequest,
    actor: Actor = Depends(require_roles("author")),
    service: DesignService = Depends(get_design_service),
) -> dict[str, object]:
    design = service.create(
        actor.organization_id,
        actor.subject_id,
        design_request,
    )
    return {"ok": True, "design": to_design_response(design).model_dump(mode="json")}


@router.get("")
def list_designs(
    actor: Actor = Depends(get_actor),
    service: DesignService = Depends(get_design_service),
) -> dict[str, object]:
    items = [
        to_design_response(design).model_dump(mode="json")
        for design in service.list(actor.organization_id)
    ]
    return {"ok": True, "items": items}


@router.get("/{design_id}")
def get_design(
    design_id: str,
    actor: Actor = Depends(get_actor),
    service: DesignService = Depends(get_design_service),
) -> dict[str, object]:
    design = service.get(actor.organization_id, design_id)
    if design is None:
        raise HTTPException(status_code=404, detail="design not found")
    return {"ok": True, "design": to_design_response(design).model_dump(mode="json")}


@router.put("/{design_id}")
def replace_design(
    design_id: str,
    design_request: HarnessDesignRequest,
    actor: Actor = Depends(require_roles("author")),
    service: DesignService = Depends(get_design_service),
) -> dict[str, object]:
    try:
        design = service.replace_draft(
            actor.organization_id, design_id, design_request
        )
    except StaleDesignDigest as exc:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": exc.message,
                "code": "stale_digest",
            },
        )
    if design is None:
        raise HTTPException(status_code=404, detail="design not found")
    return {"ok": True, "design": to_design_response(design).model_dump(mode="json")}


@router.post("/{design_id}/validate")
def validate_design(
    design_id: str,
    actor: Actor = Depends(require_roles("author")),
    service: DesignService = Depends(get_design_service),
):
    try:
        design = service.validate(actor.organization_id, design_id)
    except DesignValidationFailure as exc:
        content = {
            "ok": False,
            "error": "design validation failed",
            "code": "invalid_design",
            "finding": exc.finding,
        }
        if exc.design is not None:
            content["design"] = to_design_response(exc.design).model_dump(mode="json")
        return JSONResponse(status_code=422, content=content)
    if design is None:
        raise HTTPException(status_code=404, detail="design not found")
    return {"ok": True, "design": to_design_response(design).model_dump(mode="json")}


@router.post("/{design_id}/reviews")
def review_design(
    design_id: str,
    review_request: DesignReviewRequest,
    actor: Actor = Depends(require_roles("reviewer")),
    service: DesignService = Depends(get_design_service),
):
    try:
        design = service.approve_design(
            actor.organization_id,
            actor.subject_id,
            design_id,
            review_request.expected_digest,
            review_request.decision,
        )
    except InvalidDesignLifecycle as exc:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "error": exc.message,
                "code": "invalid_lifecycle",
            },
        )
    except StaleDesignDigest as exc:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": exc.message,
                "code": "stale_digest",
            },
        )
    if design is None:
        raise HTTPException(status_code=404, detail="design not found")
    return {"ok": True, "design": to_design_response(design).model_dump(mode="json")}
