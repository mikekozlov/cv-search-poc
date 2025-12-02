# Redesign integration test to run with Redis instead of in-memory queue

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This ExecPlan must be maintained in accordance with .agent/PLANS.md.

## Purpose / Big Picture

The async ingestion integration test currently relies on an in-memory `queue.Queue` mock. After this change, a contributor should be able to start a real Redis instance (local or containerized), point the test at it via `REDIS_URL`, and watch the ingestion watcher, extractor, and enricher push and pop JSON tasks through Redis lists end-to-end. A novice should be able to run the updated test, see SQLite and FAISS artifacts materialize under the agentic paths, and confirm that no tasks leak into a dead-letter queue.

## Progress

- [x] (2025-12-02 07:08Z) Read .agent/PLANS.md and the existing async ingestion test to capture baseline behavior and goals.
- [x] (2025-12-02 07:50Z) Replaced the mock Redis plumbing with a Redis-backed pytest fixture, added RedisClient helpers for cleanup, and rewired the async ingestion integration test to consume Redis queues with short pop timeouts.
- [x] (2025-12-02 07:53Z) Validated against a running Redis instance (db 15 with password), documented proof (queues empty, DB/index populated), and updated the retrospective.

## Surprises & Discoveries

- Observation: The async ingestion integration test injects `sys.modules["redis"] = MagicMock()` and defines `MockRedisClient` around `queue.Queue`, so none of the Redis JSON serialization or blocking pop semantics are exercised today. Evidence: tests/integration/test_async_agentic.py imports `MagicMock` and constructs in-memory queues before any pipeline components load.
- Observation: `RedisClient.pop_from_queue` wraps Redis `BLPOP` with `timeout=0` default, which blocks indefinitely if a queue is empty; any test using a real Redis backend must either pre-seed the queue or pass a short timeout to avoid hanging. Evidence: src/cv_search/ingestion/redis_client.py defines `pop_from_queue` returning `self.client.blpop(queue_name, timeout=timeout)`.
- Observation: The local Redis at localhost:6379 requires authentication; `redis://localhost:6379/15` returns an AuthenticationError, while `redis://:Temp@Pass_word1@localhost:6379/15` pings successfully. Evidence: `.venv\\Scripts\\python -c "import redis; redis.from_url('redis://localhost:6379/15').ping()"` failed with AuthenticationError, and rerunning with the password returned `True`.
- Observation: `uv run` commands failed in the sandbox with `failed to open ... uv\\cache\\sdists-v9\\.git: Access is denied`; running `.venv\\Scripts\\pytest` with `PYTHONPATH` set to the repo root and `src` succeeded. Evidence: pytest initially errored on `ModuleNotFoundError: No module named 'tests'` until `PYTHONPATH="$(Get-Location);$(Get-Location)\\src"` was exported, after which `1 passed` was reported.

## Decision Log

- Decision: Use the production `RedisClient` with a dedicated Redis DB (default db 15 for tests) and flush it before/after the test to isolate from any developer queues. Rationale: keeps integration coverage aligned with runtime JSON behavior without polluting other Redis workloads. Date/Author: 2025-12-02 / assistant.
- Decision: Treat missing Redis connectivity as a fast failure with actionable guidance (not a silent skip) so contributors know to start Redis before running the integration suite. Rationale: the goal is specifically to validate the Redis path, so hiding the dependency would undercut coverage. Date/Author: 2025-12-02 / assistant.
- Decision: Added `redis_url` overrides plus `clear_queues`/`close` helpers to `RedisClient` and introduced `tests/integration/conftest.py` to manage a real Redis client per test with DB 15 defaults. Rationale: enables tests to select an isolated Redis DB, verify connectivity, and cleanly remove ingestion queues without reaching into the raw client. Date/Author: 2025-12-02 / assistant.

## Outcomes & Retrospective

Redis-backed integration now runs end-to-end: the pytest fixture pings Redis, flushes DB 15, and the async ingestion test pushes/pops tasks through Redis lists with DLQ length 0. Running `.\\.venv\\Scripts\\pytest tests/integration/test_async_agentic.py -q` with `PYTHONPATH` set to the repo root and `REDIS_URL=redis://:Temp@Pass_word1@localhost:6379/15` produced `1 passed`, created the agentic SQLite DB and FAISS index, and left queues cleared on teardown. Sandbox restrictions prevented `uv run`, so the fallback command is documented; lingering risk is the external Redis dependency and the need to export `PYTHONPATH` when invoking pytest directly.

## Context and Orientation

The async ingestion pipeline is defined in src/cv_search/ingestion/async_pipeline.py. It exposes `Watcher` (scans the inbox and enqueues extract tasks), `ExtractorWorker` (parses a file into text and enqueues enrich tasks), and `EnricherWorker` (calls the embedder and writes into SQLite/FAISS). Queue names are constants in that module: `QUEUE_EXTRACT_TASK`, `QUEUE_ENRICH_TASK`, and `QUEUE_DLQ`. Production queue operations live in src/cv_search/ingestion/redis_client.py, which wraps `redis.from_url(...)`, pushes JSON onto Redis lists with `rpush`, and pops with blocking `blpop`.

The current integration test at tests/integration/test_async_agentic.py short-circuits Redis by monkey-patching the `redis` module to a `MagicMock` and using `MockRedisClient` backed by local `queue.Queue` objects. It still drives the real Watcher, ExtractorWorker, and EnricherWorker classes, but the queues never leave process memory.

Agentic test mode (`Settings(agentic_test_mode=True)` or `AGENTIC_TEST_MODE=1`) swaps in deterministic stubs so no external services are hit: `StubCVParser` produces predictable text, `DeterministicEmbedder` avoids network embeddings, and the agentic database/index paths are `data/test/tmp/agentic_db/cvsearch.db` and `data/test/tmp/agentic_faiss/cv_search.faiss`. Helper utilities in tests/integration/helpers.py provide `cleanup_agentic_state` to delete those artifacts and `ingest_mock_agentic` for other integration flows.

Test data for the async path lives under data/test/pptx_samples/backend_sample.txt, which the Watcher copies into a temporary inbox tree at data/test/gdrive_inbox/Engineering/backend_engineer/. Redis connectivity is configured via `REDIS_URL` in redis_client.py; if unset it defaults to `redis://localhost:6379/0`, but we will target a dedicated DB for tests to avoid collisions.

## Plan of Work

Establish a reusable Redis test fixture in `tests/integration/conftest.py` that speaks to a real Redis instance using `RedisClient`. The fixture should read `REDIS_URL` if present, otherwise default to `redis://localhost:6379/15` (DB 15 for isolation), call `ping` to prove connectivity, flush the DB before yielding, and on teardown delete the known ingestion queues (`ingest:queue:extract`, `ingest:queue:enrich`, `ingest:queue:dlq`), flush, and close the client to leave Redis clean.

Refactor `tests/integration/test_async_agentic.py` to drop the MagicMock shim and MockRedisClient. Inject the real Redis fixture, ensure `cleanup_agentic_state` runs up front, and keep `Settings(agentic_test_mode=True)` so downstream components stay deterministic. Run `Watcher._scan_and_publish()` against the prepared inbox to push tasks into Redis, then pop tasks via `RedisClient.pop_from_queue(..., timeout=1)` to avoid hangs. Feed those tasks into `ExtractorWorker._process_task` and `EnricherWorker._process_task` as before, asserting that the DLQ list is empty at the end and that SQLite/FAISS artifacts exist under the agentic paths.

Augment redis_client.py with a helper `clear_queues(self, names: list[str])` so tests can delete specific lists without reaching into the underlying `client` attribute, plus an optional `redis_url` initializer and `close()` method for clean teardown paths.

Document the expected Redis setup for contributors: a local Redis 7.x instance reachable at localhost:6379 or via a container, with optional password embedded in `REDIS_URL` (for example `redis://:Temp@Pass_word1@localhost:6379/15`). Include a short note in the test docstring or fixture explaining that the test will fail early if Redis is unreachable and how to start the container.

## Concrete Steps

From the repository root, ensure Redis is running. One option using Docker (requires Docker Desktop):

    docker run --rm -d --name cvsearch-redis -p 6379:6379 -e REDIS_PASSWORD=Temp@Pass_word1 redis:7.2.4 --requirepass Temp@Pass_word1

Export a Redis URL that targets an isolated DB for tests (include the password if required):

    $env:REDIS_URL="redis://:Temp@Pass_word1@localhost:6379/15"

Run the async ingestion integration test once the code changes are in place (agentic mode is set inside the test via Settings):

    $env:PYTHONPATH="$(Get-Location);$(Get-Location)\\src"
    $env:REDIS_URL="redis://:Temp@Pass_word1@localhost:6379/15"
    .\\.venv\\Scripts\\pytest tests/integration/test_async_agentic.py -q

If debugging connectivity, verify Redis responds before running pytest (direct python fallback when `uv run` is blocked by cache permissions):

    $env:REDIS_URL="redis://:Temp@Pass_word1@localhost:6379/15"
    .\\.venv\\Scripts\\python -c "import os, redis; client = redis.from_url(os.environ['REDIS_URL'], decode_responses=True); print(client.ping())"

## Validation and Acceptance

A successful run requires a reachable Redis instance, no residual queue items, and persisted ingestion artifacts. Acceptance criteria:

- Running the updated test command with REDIS_URL set produces `1 passed` and exits without hanging. The test should fail fast with a clear message if Redis is unavailable; in the current environment `.\\.venv\\Scripts\\pytest tests/integration/test_async_agentic.py -q` reported `1 passed` with `REDIS_URL=redis://:Temp@Pass_word1@localhost:6379/15`.
- After the test, the agentic database (`data/test/tmp/agentic_db/cvsearch.db`) contains at least one candidate row and the FAISS index (`data/test/tmp/agentic_faiss/cv_search.faiss`) exists; the DLQ Redis list length is 0.
- Queue operations must go through Redis (no in-memory mocks), confirmed by the fixture's connectivity check and use of RedisClient for push/pop.

## Idempotence and Recovery

Using a dedicated Redis DB keeps runs isolated. The fixture’s flush ensures idempotence; re-running the test should not see stale messages. If a run aborts mid-way, manually clear Redis with `redis-cli -u $REDIS_URL flushdb` (or the helper method) and run `cleanup_agentic_state(Settings(agentic_test_mode=True))` to remove agentic DB/index folders before retrying. Stop the dockerized Redis with `docker stop cvsearch-redis` when finished.

## Artifacts and Notes

Example of a healthy pytest run (q-flag) once Redis is wired in:

    $env:REDIS_URL="redis://:Temp@Pass_word1@localhost:6379/15"; uv run pytest tests/integration/test_async_agentic.py -q
    .
    1 passed in 4.8s

## Interfaces and Dependencies

Redis dependency is the standard `redis` Python client already declared in pyproject.toml. The `RedisClient` interface must support:

- `push_to_queue(queue_name: str, message: dict[str, Any])` sending JSON via `rpush`.
- `pop_from_queue(queue_name: str, timeout: int = 0) -> Optional[dict[str, Any]]` retrieving via `blpop`.
- `clear_queues(names: list[str]) -> None` deleting list keys safely, plus access to `client.ping()` for availability checks and a `close()` method for cleanup.

The ingestion workers consume the queue name constants in src/cv_search/ingestion/async_pipeline.py; tests should either use those constants directly or pass a Redis DB that isolates the queues. Settings in agentic mode ensure offline stubs are used for parsing and embedding; no OpenAI or network calls should occur during the test beyond Redis.

Plan update 2025-12-02: fleshed out the ExecPlan to describe the Redis-backed integration test design, environment assumptions, and validation approach per .agent/PLANS.md.
Plan update 2025-12-02: documented the implemented Redis fixture, RedisClient helpers, and progress toward validation.
Plan update 2025-12-02: recorded validation results, Redis authentication requirement, and the fallback pytest invocation when `uv run` is blocked by sandboxed cache access.
