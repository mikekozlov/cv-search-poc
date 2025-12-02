# Clean agentic testing: explicit dependencies and pgvector-first

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This ExecPlan must be maintained in accordance with .agent/PLANS.md (repository root: .agent/PLANS.md).

## Purpose / Big Picture

Eliminate the implicit AGENTIC_TEST_MODE toggle and the silent fallbacks it enables so that runtime behavior is explicit, fail-fast, and consistently Postgres/pgvector-backed. After this change, integration tests will pass because they explicitly wire deterministic stubs (embedder, parser, OpenAI backend) and a pgvector/pg_trgm-enabled Postgres instance; production code will stop masking misconfiguration by falling back to SQLite or stubbed LLMs and will surface missing dependencies immediately.

## Progress

- [x] (2025-12-02 14:57Z) Read .agent/PLANS.md and current code; replaced the placeholder with a full ExecPlan for removing AGENTIC_TEST_MODE-driven fallbacks.
- [ ] Catalog every AGENTIC_TEST_MODE usage and define the post-removal default for each component (DB, embedder, parser, OpenAI client, data paths, runs dir).
- [ ] Implement the refactor, update tests/docs, and verify the Postgres/pgvector-only path with deterministic test doubles.

## Surprises & Discoveries

- Observation: CVDatabase downgrades to SQLite when psycopg connection fails only if agentic_test_mode is true, which hides pgvector/pg_trgm issues instead of surfacing them.
  Evidence: src/cv_search/db/database.py __init__ catches connection errors and switches backend to SQLite when settings.agentic_test_mode is true.
- Observation: OpenAIClient silently swaps to StubOpenAIBackend whenever agentic_test_mode is true or when the API key is missing, so production can run against stubbed responses without warning.
  Evidence: src/cv_search/clients/openai_client.py __init__ branches to StubOpenAIBackend when settings.agentic_test_mode or not settings.openai_api_key_str.
- Observation: Async ingestion and pipeline classes pick deterministic embedders, stub parsers, and test data directories automatically based on agentic_test_mode instead of explicit dependency injection, making integration tests rely on hidden global state.
  Evidence: src/cv_search/ingestion/async_pipeline.py and src/cv_search/ingestion/pipeline.py choose DeterministicEmbedder/StubCVParser and test_data_dir when settings.agentic_test_mode is true.

## Decision Log

- Decision: Remove AGENTIC_TEST_MODE from Settings and constructors; tests must supply explicit doubles while runtime defaults stay production-grade.
  Rationale: Hidden environment toggles make behavior unpredictable and obscure failures; explicit wiring clarifies intent and improves reproducibility.
  Date/Author: 2025-12-02 / assistant
- Decision: Drop runtime fallbacks (SQLite database, stub LLM backends, deterministic embedders) and raise clear errors when dependencies are missing; keep pgvector/pg_trgm Postgres as the only supported backend.
  Rationale: Silent fallbacks mask infrastructure issues and diverge from real deployments; failing fast pushes contributors to provision Postgres and credentials up front while tests stay deterministic through injected doubles.
  Date/Author: 2025-12-02 / assistant

## Outcomes & Retrospective

Implementation has not started; this section will summarize results, remaining gaps, and lessons learned after the refactor and test runs.

## Context and Orientation

The project is a Python 3.11 app (src/ layout, uv/pytest) with ingestion pipelines, async Redis workers, search orchestration, and CLI commands defined in main.py. The Settings class (src/cv_search/config/settings.py) currently exposes an agentic_test_mode flag that flips paths (active_db_url, active_runs_dir, gdrive inbox) and drives automatic stub selection across the codebase. CVDatabase (src/cv_search/db/database.py) prefers Postgres with pgvector but falls back to SQLite when agentic_test_mode is enabled; reset_agentic_state truncates data only when that flag is set. OpenAIClient (src/cv_search/clients/openai_client.py) uses StubOpenAIBackend whenever agentic_test_mode is true or the API key is absent. IngestionPipeline and EnricherWorker switch to DeterministicEmbedder and StubCVParser based on the same flag, and they write artifacts under data/test when the flag is true. Integration tests (tests/integration/*.py) set AGENTIC_TEST_MODE=1 via helpers.py, rely on deterministic embedders and stub parsers chosen automatically, and expect a pgvector-enabled Postgres reachable at settings.agentic_db_url spun up via docker-compose.pg.yml.

There is a separate ExecPlan for the Postgres/pgvector migration in .agent/plans/redesign-to-use-pgvector-pg-fts-with-local-docker-pg-setup-instead-of-failss-sqlite.md; this plan builds on that state by enforcing pgvector/pg_trgm as the sole backend and removing agentic fallbacks rather than maintaining a SQLite escape hatch.

## Plan of Work

Map every consumer of agentic_test_mode and the behaviors it toggles (DB selection, data directories, runs_dir, stub LLM/backend choices, embedder/parser defaults, Redis inbox paths). Decide and document the new default for each spot: always use production-grade defaults (Postgres DSN from settings.db_url, LocalEmbedder, CVParser, LiveOpenAIBackend) unless the caller explicitly supplies a substitute.

Redesign configuration so tests can still run deterministically without a global flag. Replace agentic_test_mode with explicit constructor parameters or a lightweight TestConfig (for example: deterministic embedder, stub parser, stub LLM backend, test data dir, test runs dir, test Postgres DSN). Update Settings to drop agentic-specific properties (agentic_db_url, agentic_runs_dir, test_data_dir overrides) or mark them deprecated, and ensure active_db_url/active_runs_dir simply return configured values without branching on an environment variable.

Refactor CVDatabase to remove SQLite fallback paths and require pgvector/pg_trgm; add clear error messages if the connection fails or the vector extension is missing. Keep schema initialization idempotent but fail fast when Postgres is unreachable. Propagate failures instead of catching-and-downgrading. Ensure rank_weighted_set, vector_search, and fts_search always operate against Postgres types (Vector) and return consistent rows to callers.

Update ingestion and async workers to require explicit dependencies. EnricherWorker and CVIngestionPipeline should accept embedder, parser, and OpenAIClient instances and default to production implementations; tests must pass DeterministicEmbedder and StubCVParser explicitly. Remove agentic-based path rewrites; rely on Settings-provided directories or explicit parameters. Ensure pipeline.reset_state can truncate Postgres tables without checking a removed flag.

Tighten OpenAIClient so it only uses StubOpenAIBackend when explicitly injected; otherwise it should raise a clear error when credentials are missing. Adjust JustificationService and search processor wiring so tests can pass a stub backend while production requires real credentials. Ensure error messages suggest running docker compose for Postgres and setting OPENAI_API_KEY.

Rewrite integration tests and helpers to operate without AGENTIC_TEST_MODE. Update fixtures to spin up/verify Postgres via docker-compose.pg.yml, create Settings with explicit test DSNs and paths, and inject deterministic embedders and stub parsers/LLM backends into pipelines, workers, and search processor. Replace environment mutation (agentic_env) with constructor arguments. Add regression tests that confirm the code raises when Postgres is unreachable or when OpenAI credentials are absent without an injected stub.

Clean up documentation (.env.example, README.md, AGENTS.md references) to remove AGENTIC_TEST_MODE and describe the explicit test wiring and Postgres requirements. Note that pgvector/pg_trgm must be present and that tests expect the docker compose service running.

## Concrete Steps

    PS C:\Users\mykha\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d
    Start the pgvector-enabled Postgres service locally; wait for the healthcheck to turn healthy.

    PS C:\Users\mykha\Projects\cv-search-poc> Remove-Item Env:AGENTIC_TEST_MODE -ErrorAction Ignore
    Ensure no legacy environment flag influences behavior.

    PS C:\Users\mykha\Projects\cv-search-poc> uv run python main.py init-db --db-url postgresql://cvsearch:cvsearch@localhost:5433/cvsearch
    Verify schema creation and extension availability; expect vector/pg_trgm listed and no SQLite fallback.

    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests/integration -q
    Run the suite after refactors; tests should inject deterministic doubles explicitly and pass without AGENTIC_TEST_MODE.

    PS C:\Users\mykha\Projects\cv-search-poc> uv run python main.py ingest-mock --db-url postgresql://cvsearch:cvsearch@localhost:5433/cvsearch
    Confirm ingestion works with production defaults and raises if Postgres is unavailable.

## Validation and Acceptance

The plan is complete when the codebase contains no references to AGENTIC_TEST_MODE and no implicit fallbacks to SQLite, stub LLMs, or deterministic embedders. Running the integration suite with the commands above must pass without setting any agentic environment flag. Initializing CVDatabase without a reachable Postgres or missing pgvector/pg_trgm should raise a clear error rather than downgrading. OpenAIClient must raise when no API key is configured unless a stub backend is explicitly provided. Manual runs of ingest-mock and search-seat must succeed against Postgres/pgvector with embeddings stored in candidate_doc.embedding and FTS queries operating on tsv_document.

## Idempotence and Recovery

Schema initialization remains idempotent: re-running init-db should be a no-op when Postgres is healthy. If Postgres state needs resetting, use `docker compose -f docker-compose.pg.yml down -v` followed by `up -d` to clear data, then rerun init-db. Remove-Item Env:AGENTIC_TEST_MODE prevents stale environment influence. Because fallbacks are removed, failures indicate real misconfiguration; recovery involves fixing DSNs, ensuring pgvector/pg_trgm are installed, or providing explicit stubs in tests, not toggling hidden flags.

## Artifacts and Notes

Capture a short init-db transcript showing pgvector/pg_trgm availability and absence of SQLite fallback messaging. Record a pytest run summary demonstrating that tests pass without AGENTIC_TEST_MODE. Keep a snippet of the error raised when OpenAI credentials are missing and no stub backend is provided to prove fail-fast behavior. Save a sample search-seat output showing embeddings retrieved from Postgres (vector distances present) to confirm the pgvector path is exercised.

## Interfaces and Dependencies

Settings (src/cv_search/config/settings.py) should expose explicit db_url, runs_dir, gdrive paths, and optional test overrides without agentic_test_mode. Provide a way to pass deterministic paths/DSNs directly (constructor arguments or a small config object) instead of environment flags.

CVDatabase (src/cv_search/db/database.py) should accept only a Postgres DSN and raise on connection/extension errors; no SQLite fallback. Methods such as initialize_schema, vector_search, fts_search, rank_weighted_set, and reset_state should assume Postgres types (Vector) and run against pgvector/pg_trgm.

OpenAIClient (src/cv_search/clients/openai_client.py) should default to LiveOpenAIBackend and raise if OPENAI_API_KEY is absent; allow an explicit backend parameter for tests (StubOpenAIBackend) without consulting global flags.

Ingestion and async workers (src/cv_search/ingestion/pipeline.py, src/cv_search/ingestion/async_pipeline.py) should require embedder/parser/client injections for deterministic tests; defaults use LocalEmbedder and CVParser. Paths for inbox/json outputs should come from Settings fields, not agentic conditionals.

Tests (tests/integration/*.py) should construct Settings with explicit test DSNs/paths and inject DeterministicEmbedder, StubCVParser, and StubOpenAIBackend through constructors or fixtures; remove agentic_env helpers and validate fail-fast behavior when Postgres or credentials are missing.

Note: Plan updated on 2025-12-02 to replace placeholders with a full ExecPlan and to align with the directive to remove AGENTIC_TEST_MODE and fallback paths in favor of explicit, pgvector-backed testing.
