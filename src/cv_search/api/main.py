"""FastAPI application factory and configuration."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, Response

from cv_search.api.deps import build_openai_backend
from cv_search.api.exceptions import register_exception_handlers
from cv_search.api.logging_config import setup_logging
from cv_search.api.middleware import RequestLoggingMiddleware
from cv_search.api.version import BUILD_VERSION
from cv_search.clients.openai_client import OpenAIClient
from cv_search.config.settings import Settings
from cv_search.planner.service import Planner


def _load_default_env() -> None:
    """Load .env file from project root if not already loaded."""
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(dotenv_path=project_root / ".env", override=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes stateless services on startup, cleans up on shutdown.
    """
    # Load environment variables
    _load_default_env()

    # Initialize stateless services (cached for app lifetime)
    settings = Settings()
    backend = build_openai_backend(settings)
    client = OpenAIClient(settings, backend=backend)
    planner = Planner()

    # Store in app state for dependency injection
    app.state.settings = settings
    app.state.client = client
    app.state.planner = planner

    yield

    # Cleanup on shutdown (if needed)
    # Currently no cleanup required for stateless services


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    # Configure logging before anything else
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(log_level)

    app = FastAPI(
        title="CV Search API",
        description=(
            "Candidate search API for chatbot integration. "
            "Provides endpoints for single-seat search, multi-seat project search, "
            "presale team planning, and search run management."
        ),
        version=BUILD_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS for chatbot integration
    # In production, configure allowed_origins appropriately
    cors_origins = os.environ.get("API_CORS_ORIGINS", "*")
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key auth middleware (skips health/docs endpoints)
    _PUBLIC_PREFIXES = ("/health", "/ready", "/docs", "/redoc", "/openapi.json", "/")

    class ApiKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self, request: StarletteRequest, call_next: RequestResponseEndpoint
        ) -> Response:
            path = request.url.path
            # Skip auth for public endpoints
            if path in _PUBLIC_PREFIXES or path.rstrip("/") in _PUBLIC_PREFIXES:
                return await call_next(request)
            settings = request.app.state.settings
            expected_key = getattr(settings, "api_key", None)
            if not expected_key:
                return await call_next(request)
            expected = (
                expected_key.get_secret_value()
                if hasattr(expected_key, "get_secret_value")
                else expected_key
            )
            api_key = request.headers.get("X-API-Key")
            if not api_key:
                return JSONResponse({"detail": "Missing API key"}, status_code=401)
            if api_key != expected:
                return JSONResponse({"detail": "Invalid API key"}, status_code=401)
            return await call_next(request)

    app.add_middleware(ApiKeyMiddleware)

    # Request logging middleware (outermost — wraps everything)
    app.add_middleware(RequestLoggingMiddleware)

    # Register custom exception handlers
    register_exception_handlers(app)

    # Import and include routers
    from cv_search.api.health.router import router as health_router
    from cv_search.api.planner.router import router as planner_router
    from cv_search.api.runs.router import router as runs_router
    from cv_search.api.search.router import router as search_router

    # Health endpoints at root level
    app.include_router(health_router, tags=["health"])

    # API v1 endpoints
    app.include_router(search_router, prefix="/api/v1/search", tags=["search"])
    app.include_router(
        planner_router, prefix="/api/v1/planner", tags=["planner"], include_in_schema=False
    )
    app.include_router(runs_router, prefix="/api/v1/runs", tags=["runs"])

    @app.get("/", include_in_schema=False)
    def root():
        """Root endpoint - redirect to docs."""
        return {
            "message": "CV Search API",
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
        }

    # Custom OpenAPI schema with API key security
    app.openapi_schema = None  # Clear any pre-cached schema

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        openapi_schema.setdefault("components", {})["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key for authentication. Set in .env as API_KEY.",
            }
        }
        openapi_schema["security"] = [{"ApiKeyAuth": []}]
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app


# Create the app instance for uvicorn
app = create_app()
