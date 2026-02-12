"""API exception definitions and handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("cv_search.api.exceptions")


class APIException(Exception):
    """Base exception for API errors."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        detail: str | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class CriteriaValidationError(APIException):
    """Raised when search criteria validation fails."""

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message, "INVALID_CRITERIA", 400, detail)


class SearchExecutionError(APIException):
    """Raised when search execution fails."""

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message, "SEARCH_FAILED", 500, detail)


class RunNotFoundError(APIException):
    """Raised when a search run is not found."""

    def __init__(self, run_id: str):
        super().__init__(f"Run '{run_id}' not found", "RUN_NOT_FOUND", 404)


class DatabaseConnectionError(APIException):
    """Raised when database connection fails."""

    def __init__(self, message: str = "Database connection failed"):
        super().__init__(message, "DB_CONNECTION_ERROR", 503)


class AuthenticationError(APIException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(message, "AUTH_FAILED", 401)


class PlannerError(APIException):
    """Raised when planner operations fail."""

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message, "PLANNER_ERROR", 500, detail)


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI app."""

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
        logger.warning(
            "%s %s -> %s [%d]: %s",
            request.method,
            request.url.path,
            exc.code,
            exc.status_code,
            exc.message,
        )
        content = {
            "error": exc.message,
            "code": exc.code,
        }
        if exc.detail:
            content["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "%s %s -> unhandled exception: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "detail": str(exc) if app.debug else None,
            },
        )
