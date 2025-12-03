from __future__ import annotations

import os
import warnings

import pytest

from cv_search.ingestion.async_pipeline import QUEUE_DLQ, QUEUE_ENRICH_TASK, QUEUE_EXTRACT_TASK
from cv_search.ingestion.redis_client import InMemoryRedisClient, RedisClient

# Use an isolated Redis DB for tests by default; override with REDIS_URL if set.
DEFAULT_REDIS_URL = "redis://localhost:6379/15"


@pytest.fixture()
def redis_client() -> RedisClient:
    """Provide a Redis-backed client for integration tests.

    Falls back to an in-memory stub when Redis is unavailable or auth-protected
    so the pipeline can still be exercised in constrained environments.
    """
    redis_url = os.getenv("REDIS_URL", DEFAULT_REDIS_URL)
    force_in_memory = os.getenv("USE_IN_MEMORY_REDIS", "").lower() in {"1", "true", "yes"}
    client: RedisClient | None = None
    ping_error: Exception | None = None

    if not force_in_memory:
        try:
            client = RedisClient(redis_url=redis_url)
            client.client.ping()
        except Exception as exc:
            ping_error = exc
            if client:
                client.close()
            client = None

    if client is None:
        client = InMemoryRedisClient()
        if ping_error and not force_in_memory:
            warnings.warn(f"Using in-memory Redis fallback for tests: {ping_error}", RuntimeWarning)

    client.client.flushdb()
    try:
        yield client
    finally:
        client.clear_queues([QUEUE_EXTRACT_TASK, QUEUE_ENRICH_TASK, QUEUE_DLQ])
        client.client.flushdb()
        client.close()
