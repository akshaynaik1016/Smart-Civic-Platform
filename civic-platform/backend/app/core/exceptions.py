"""Structured HTTP exceptions and global FastAPI exception handlers."""
from __future__ import annotations
import logging
from typing import Any
from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

class CivicAPIError(HTTPException):
    def __init__(self, status_code: int, error: str, message: str,
                 details: Any = None, headers: dict | None = None) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error = error; self.message = message; self.details = details

class BadRequestError(CivicAPIError):
    def __init__(self, message: str = "Bad request", details: Any = None):
        super().__init__(400, "bad_request", message, details)

class DuplicateComplaintError(CivicAPIError):
    def __init__(self, parent_id: str, similarity: float):
        super().__init__(409, "duplicate_complaint",
            "A similar complaint already exists in this area.",
            {"parent_complaint_id": parent_id, "similarity_score": similarity})

class UnauthorizedError(CivicAPIError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})

class TokenExpiredError(CivicAPIError):
    def __init__(self):
        super().__init__(401, "token_expired",
            "Access token has expired. Use /auth/refresh.", headers={"WWW-Authenticate": "Bearer"})

class TokenRevokedError(CivicAPIError):
    def __init__(self):
        super().__init__(401, "token_revoked",
            "Token revoked. Please log in again.", headers={"WWW-Authenticate": "Bearer"})

class ForbiddenError(CivicAPIError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(403, "forbidden", message)

class NotFoundError(CivicAPIError):
    def __init__(self, resource: str = "Resource", resource_id: str | None = None):
        msg = f"{resource} '{resource_id}' not found" if resource_id else f"{resource} not found"
        super().__init__(404, "not_found", msg)

class ConflictError(CivicAPIError):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(409, "conflict", message)

class FileTooLargeError(CivicAPIError):
    def __init__(self, max_mb: int = 10):
        super().__init__(413, "file_too_large", f"File exceeds the {max_mb} MB limit.")

class RateLimitError(CivicAPIError):
    def __init__(self, retry_after: int = 60):
        super().__init__(429, "rate_limit_exceeded",
            f"Too many requests. Retry after {retry_after}s.",
            headers={"Retry-After": str(retry_after)})

class InternalError(CivicAPIError):
    def __init__(self, message: str = "An unexpected error occurred"):
        super().__init__(500, "internal_error", message)

class AIProcessingError(CivicAPIError):
    def __init__(self, message: str = "AI analysis failed"):
        super().__init__(500, "ai_processing_error", message)

def _rid(req: Request) -> str:
    return getattr(req.state, "request_id", "unknown")

async def civic_api_error_handler(request: Request, exc: CivicAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error,
            "message": exc.message,
            "details": exc.details,
            "request_id": _rid(request),
        },
        headers=exc.headers or {},
    )

async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errs = [
        {
            "field": "→".join(str(l) for l in e["loc"]),
            "message": e["msg"],
            "type": e["type"],
        }
        for e in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Validation failed",
            "details": errs,
            "request_id": _rid(request),
        },
    )
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled: %s", exc)

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Unexpected error",
            "request_id": _rid(request),
        },
    )
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": exc.detail,
            "request_id": _rid(request),
        },
        headers=getattr(exc, "headers", None) or {},
    )
def register_exception_handlers(app) -> None:
    app.add_exception_handler(CivicAPIError, civic_api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_error_handler)
