"""Shared FastAPI dependencies for dependency injection."""

from __future__ import annotations

import os
from typing import Annotated, Generator

from fastapi import Depends, HTTPException, Request

from cv_search.clients.openai_client import (
    LiveOpenAIBackend,
    OpenAIClient,
    StubOpenAIBackend,
)
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
from cv_search.planner.service import Planner
from cv_search.search.processor import SearchProcessor

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    """Check if an environment variable is truthy."""
    value = os.environ.get(name)
    return value is not None and str(value).lower() in _TRUTHY


def build_openai_backend(settings: Settings):
    """Build the appropriate OpenAI backend based on environment."""
    force_stub = _env_flag("USE_OPENAI_STUB") or _env_flag("HF_HUB_OFFLINE")
    if force_stub or not settings.openai_api_key_str:
        return StubOpenAIBackend(settings)
    return LiveOpenAIBackend(settings)


# -----------------------------------------------------------------------------
# Stateless service dependencies (cached at app startup via app.state)
# -----------------------------------------------------------------------------


def get_settings(request: Request) -> Settings:
    """Get Settings instance from app state."""
    return request.app.state.settings


def get_openai_client(request: Request) -> OpenAIClient:
    """Get OpenAIClient instance from app state."""
    return request.app.state.client


def get_planner(request: Request) -> Planner:
    """Get Planner instance from app state."""
    return request.app.state.planner


# -----------------------------------------------------------------------------
# Per-request dependencies (create fresh, cleanup after request)
# -----------------------------------------------------------------------------


def get_db(request: Request) -> Generator[CVDatabase, None, None]:
    """
    Get a CVDatabase connection for the request.
    Connection is returned to pool after request completes.
    """
    settings: Settings = request.app.state.settings
    db = CVDatabase(settings)
    try:
        yield db
    finally:
        db.close()


def get_search_processor(
    db: Annotated[CVDatabase, Depends(get_db)],
    client: Annotated[OpenAIClient, Depends(get_openai_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchProcessor:
    """
    Get a SearchProcessor instance for the request.
    Combines DB, client, and settings.
    """
    return SearchProcessor(db, client, settings)


# -----------------------------------------------------------------------------
# Authentication dependencies
# -----------------------------------------------------------------------------


async def verify_api_key(request: Request) -> str | None:
    """
    Verify API key if configured in settings.
    Returns the API key if valid, or None if no key is required.

    The header is read from request.headers directly (not via Header/APIKeyHeader)
    so that FastAPI does NOT generate a per-endpoint parameter in the OpenAPI spec.
    The Swagger UI "Authorize" button is powered by the global security scheme
    defined in main.py's custom_openapi().
    """
    settings: Settings = request.app.state.settings
    expected_key = getattr(settings, "api_key", None)

    # If no API key is configured, allow all requests
    if not expected_key:
        return None

    # Get secret value if it's a SecretStr
    expected = (
        expected_key.get_secret_value()
        if hasattr(expected_key, "get_secret_value")
        else expected_key
    )

    x_api_key = request.headers.get("X-API-Key")

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_api_key


# -----------------------------------------------------------------------------
# Type aliases for cleaner route signatures
# -----------------------------------------------------------------------------

SettingsDep = Annotated[Settings, Depends(get_settings)]
DBDep = Annotated[CVDatabase, Depends(get_db)]
ClientDep = Annotated[OpenAIClient, Depends(get_openai_client)]
PlannerDep = Annotated[Planner, Depends(get_planner)]
ProcessorDep = Annotated[SearchProcessor, Depends(get_search_processor)]
