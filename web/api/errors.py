from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

MAX_VALIDATION_DETAILS = 10
MAX_VALIDATION_MESSAGE_LENGTH = 200
MISSING_REFERENCE_MESSAGE = "referenced tenant or resource does not exist"


def _error_code(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    return "error"


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": str(exc.detail),
            "code": _error_code(exc.status_code),
        },
    )


def _safe_text(value: object) -> str:
    text = str(value)
    printable = "".join(
        character
        for character in text
        if character.isascii() and (character.isprintable() or character == " ")
    )
    collapsed = " ".join(printable.split())
    if len(collapsed) > MAX_VALIDATION_MESSAGE_LENGTH:
        return f"{collapsed[:MAX_VALIDATION_MESSAGE_LENGTH]}..."
    return collapsed


def _safe_field(location: object) -> str:
    if not isinstance(location, (list, tuple)):
        return _safe_text(location)
    return _safe_text(".".join(str(part) for part in location))


def bounded_validation_detail(
    errors: list[dict[str, object]]
) -> list[dict[str, str]]:
    return [
        {
            "field": _safe_field(error.get("loc", ())),
            "code": _safe_text(error.get("type", "invalid")),
            "message": _safe_text(error.get("msg", "invalid value")),
        }
        for error in errors[:MAX_VALIDATION_DETAILS]
    ]


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": "request validation failed",
            "code": "invalid_request",
            "detail": bounded_validation_detail(list(exc.errors())),
        },
    )


def is_foreign_key_violation(exc: IntegrityError) -> bool:
    original = getattr(exc, "orig", None)
    if original is None:
        return False
    if getattr(original, "sqlstate", None) == "23503":
        return True
    if getattr(original, "pgcode", None) == "23503":
        return True
    diagnostic = getattr(original, "diag", None)
    if getattr(diagnostic, "sqlstate", None) == "23503":
        return True
    if type(original).__name__ == "ForeignKeyViolation":
        return True
    return "FOREIGN KEY constraint failed" in str(original)


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    del request
    if is_foreign_key_violation(exc):
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "error": MISSING_REFERENCE_MESSAGE,
                "code": "missing_reference",
            },
        )
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": "internal server error",
            "code": "internal_error",
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    del request, exc
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error": "internal server error",
            "code": "internal_error",
        },
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, request_validation_exception_handler
    )
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
