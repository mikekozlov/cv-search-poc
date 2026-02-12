"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from cv_search.api.version import BUILD_VERSION
from cv_search.db.database import CVDatabase

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = BUILD_VERSION


class ReadyResponse(BaseModel):
    """Readiness check response."""

    status: str
    database: str
    details: dict | None = None


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """
    Liveness probe - always returns 200 if the service is running.
    Use this for Kubernetes liveness checks.
    """
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
def readiness_check(request: Request) -> ReadyResponse:
    """
    Readiness probe - checks if the service can handle requests.
    Verifies database connectivity.
    Use this for Kubernetes readiness checks.
    """
    settings = request.app.state.settings
    db_status = "unknown"
    details = {}

    try:
        db = CVDatabase(settings)
        try:
            with db.conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            db_status = "connected"
        finally:
            db.close()
    except Exception as e:
        db_status = "error"
        details["database_error"] = str(e)

    overall_status = "ready" if db_status == "connected" else "not_ready"

    return ReadyResponse(
        status=overall_status,
        database=db_status,
        details=details if details else None,
    )
