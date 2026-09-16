from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from web.api.identity.dependencies import require_roles_short_session
from web.api.identity.models import Actor
from web.api.designs.schemas import to_design_response

from .privacy import SecretDetected
from .proposals import ProposalService
from .schemas import (
    AnswerRequest,
    ApplyProposalRequest,
    ConfirmationRequest,
    ProposalRequest,
    StartInterviewRequest,
)
from .service import (
    InterviewConflict,
    InterviewInferenceFailure,
    InterviewNotFound,
    InterviewService,
    InterviewTargetNotFound,
)

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


def _service(request: Request) -> InterviewService:
    return InterviewService(
        request.app.state.session_factory,
        request.app.state.settings,
        request.app.state.interview_model,
    )


def _proposal_service(request: Request) -> ProposalService:
    return ProposalService(
        request.app.state.session_factory,
        request.app.state.settings,
        request.app.state.interview_model,
    )


def _session_payload(session) -> dict[str, object]:
    return {"ok": True, "session": session.model_dump(mode="json")}


def _conflict(exc: InterviewConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"ok": False, "error": exc.message, "code": exc.code},
    )


def _inference_failure(exc: InterviewInferenceFailure) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "error": "interview inference did not complete",
            "code": exc.code,
        },
    )


def _secret_failure(exc: SecretDetected) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": str(exc), "code": "secret_detected"},
    )


@router.post("")
async def start_interview(
    body: StartInterviewRequest,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        session, created = await _service(request).start(actor, body)
    except SecretDetected as exc:
        return _secret_failure(exc)
    except InterviewConflict as exc:
        return _conflict(exc)
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    except InterviewInferenceFailure as exc:
        return _inference_failure(exc)
    return JSONResponse(
        status_code=201 if created else 200,
        content=_session_payload(session),
    )


@router.get("")
def list_interviews(
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    return {
        "ok": True,
        "items": [
            session.model_dump(mode="json")
            for session in _service(request).list(actor)
        ],
    }


@router.get("/catalog")
def get_authoritative_catalog(
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    del actor
    return {"ok": True, "catalog": _proposal_service(request).catalog()}


@router.get("/{session_id}")
def get_interview(
    session_id: str,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        session = _service(request).get(actor, session_id)
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    return _session_payload(session)


@router.post("/{session_id}/proposals")
async def generate_proposal(
    session_id: str,
    body: ProposalRequest,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        proposal, created = await _proposal_service(request).generate(
            actor, session_id, body
        )
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    except InterviewConflict as exc:
        return _conflict(exc)
    except InterviewInferenceFailure as exc:
        return _inference_failure(exc)
    return JSONResponse(
        status_code=201 if created else 200,
        content={
            "ok": True,
            "proposal": proposal.model_dump(mode="json"),
        },
    )


@router.get("/{session_id}/proposals/{proposal_id}")
def get_proposal(
    session_id: str,
    proposal_id: str,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        proposal = _proposal_service(request).get(
            actor,
            session_id,
            proposal_id,
        )
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="proposal not found") from None
    except InterviewConflict as exc:
        return _conflict(exc)
    return {
        "ok": True,
        "proposal": proposal.model_dump(mode="json"),
    }


@router.post("/{session_id}/apply")
def apply_proposal(
    session_id: str,
    body: ApplyProposalRequest,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        design = _proposal_service(request).apply(actor, session_id, body)
    except InterviewTargetNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "ok": False,
                "error": "target design not found",
                "code": "target_design_not_found",
            },
        )
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    except InterviewConflict as exc:
        return _conflict(exc)
    return {
        "ok": True,
        "design": to_design_response(design).model_dump(mode="json"),
    }


@router.post("/{session_id}/turns")
async def answer_interview(
    session_id: str,
    body: AnswerRequest,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        session = await _service(request).answer(actor, session_id, body)
    except SecretDetected as exc:
        return _secret_failure(exc)
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    except InterviewConflict as exc:
        return _conflict(exc)
    except InterviewInferenceFailure as exc:
        return _inference_failure(exc)
    return _session_payload(session)


@router.post("/{session_id}/confirmations")
def confirm_evidence(
    session_id: str,
    body: ConfirmationRequest,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        session = _service(request).confirm(actor, session_id, body)
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    except InterviewConflict as exc:
        return _conflict(exc)
    return _session_payload(session)


@router.delete("/{session_id}")
def delete_interview(
    session_id: str,
    request: Request,
    actor: Actor = Depends(require_roles_short_session("author", "org-admin")),
):
    try:
        _service(request).delete(actor, session_id)
    except InterviewNotFound:
        raise HTTPException(status_code=404, detail="interview not found") from None
    return {"ok": True, "deleted": True}
