FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy all source needed for build
COPY pyproject.toml README.md ./
COPY src/ src/
COPY data/lexicons/ data/lexicons/
COPY api_server.py ./

# Install dependencies (pip install resolves deps from pyproject.toml)
# PYTHONPATH ensures Python uses source from /app/src so REPO_ROOT paths work
ENV PYTHONPATH=/app/src
RUN uv pip install --system --no-cache .

# Bake git commit hash into image (passed via --build-arg)
ARG BUILD_COMMIT=dev
RUN echo "${BUILD_COMMIT}" > /app/BUILD_COMMIT

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run with uvicorn (4 workers for production)
CMD ["python", "-m", "uvicorn", "cv_search.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
