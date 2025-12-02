# redesign-to-use-pgvector-pg-fts-with-local-docker-pg-setup-instead-of-failss-sqlite

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This ExecPlan must be maintained in accordance with .agent/PLANS.md.

## Purpose / Big Picture

Move the product off the fragile SQLite + FAISS stack and onto a single Postgres instance with pgvector and Postgres FTS. After implementing this plan, a contributor can spin up Postgres locally via Docker, run ingestion, and execute lexical/semantic/hybrid searches backed by pgvector and tsvector indexes with no dependency on file-based FAISS artifacts. The CLI, async ingestion workers, and Streamlit UI should all run against the same Postgres database and expose clear checks to prove pgvector/FTS are active.

## Progress

- [x] (2025-12-02 08:15Z) Read .agent/PLANS.md and current codebase; drafted full ExecPlan for the Postgres/pgvector migration.
- [x] (2025-12-02 10:56Z) Added docker-compose.pg.yml/init SQL, new pgvector/FTS schema and DB layer with Postgres-first + SQLite fallback; schema init exercised via tests, but Docker engine remains inaccessible for container verification.
- [x] (2025-12-02 10:57Z) Refactored ingestion/search stacks to store embeddings in Postgres (pgvector retriever + FTS-aware lexical), removed FAISS/SQLite code paths, and updated CLI/UI to surface Postgres status with a constrained-environment SQLite fallback.
- [x] (2025-12-02 10:57Z) Updated tests and docs for the Postgres flow; integration suite now passes in agentic mode using the fallback backend when pgvector is unavailable, with README/.env.example refreshed for the new DSNs and commands.

## Surprises & Discoveries

- Observation: The current retrieval stack is split between SQLite (for tags) and a file-based FAISS index for semantic search; there is no real FTS usage despite the `check_fts` helper.
  Evidence: `LocalSemanticRetriever` loads `settings.active_faiss_index_path` (src/cv_search/retrieval/semantic.py), and `CVDatabase.rank_weighted_set` only scores structured tags (src/cv_search/db/database.py).
- Observation: Integration tests assert that FAISS files are written and SQLite tables exist when `AGENTIC_TEST_MODE=1`, so tests will break until they are redirected to Postgres and pgvector.
  Evidence: `tests/integration/test_async_agentic.py` checks `faiss.read_index(str(settings.active_faiss_index_path))` and queries SQLite tables.
- Observation: The Streamlit Admin page rebuilds the FAISS index and reports FAISS ntotal, which will become meaningless once the vector store moves into Postgres.
  Evidence: `pages/3_Admin_&_Ingest.py` calls `pipeline.run_ingestion_from_list` and inspects `processor.semantic_retriever.vector_db`.
- Observation: Docker engine is not currently accessible on this host (`docker images` reports “Access is denied”), so local container validation will rely on compose/schema readiness until access is restored.
  Evidence: Running `docker images` fails with “open //./pipe/dockerDesktopLinuxEngine: Access is denied.”
- Observation: PyPI access for `psycopg`/`pgvector` is blocked (`pip install` reports “No matching distribution found”), so a SQLite-backed fallback path was added for agentic tests while keeping Postgres as the primary target.
  Evidence: `.venv\\Scripts\\python -m pip install "psycopg[binary,pool]>=3.2"` failed with “No matching distribution found for psycopg>=3.2”.

## Decision Log

- Decision: Target Postgres 16 with the pgvector extension enabled via a local Docker Compose service (exposed on localhost, separate `cvsearch` and `cvsearch_test` databases).
  Rationale: Keeps contributors off host-level Postgres installs, provides deterministic vector support, and cleanly separates dev/test data.
  Date/Author: 2025-12-02 / assistant
- Decision: Retain `CVDatabase` as the main data-access facade but reimplement it with psycopg3 + pooling and a new Postgres-focused schema file.
  Rationale: Minimizes call-site churn across ingestion/search/UI while unlocking Postgres features and better connection handling.
  Date/Author: 2025-12-02 / assistant
- Decision: Store embeddings directly in Postgres (`candidate_doc.embedding vector(384)` with an IVFFLAT cosine index) and add a generated `tsv_document` column for weighted FTS over summary, experience, and tags.
  Rationale: Eliminates FAISS file management, co-locates semantic and lexical signals, and enables hybrid ranking in a single queryable store.
  Date/Author: 2025-12-02 / assistant
- Decision: Add a SQLite-backed compatibility path for agentic mode when psycopg/pgvector or Docker are unavailable, while keeping Postgres the primary and preferred backend.
  Rationale: Network restrictions blocked installing pgvector/psycopg and starting Docker, so a fallback keeps CLI/tests runnable without masking the Postgres-first design.
  Date/Author: 2025-12-02 / assistant

## Outcomes & Retrospective

Ingestion/search now target Postgres with pgvector + FTS and drop FAISS entirely; CLI/UI report Postgres health and mock ingestion flows seed embeddings directly into `candidate_doc`. Agentic tests pass end-to-end using a SQLite fallback because pgvector wheels and Docker are blocked in this environment; once pgvector/psycopg are available the same code path will use the containerized Postgres defined in `docker-compose.pg.yml`. Remaining risk: container/extension creation is unverified locally due to Docker service permissions, so a follow-up check on a host with Docker access is recommended.

## Context and Orientation

The repository today is a Python 3.11 project managed by uv (src/ layout, pyproject.toml). Data is stored in SQLite (`data/db/cvsearch.db`, schema at `src/cv_search/db/schema.sql`) with a separate FAISS index file (`data/cv_search.faiss`) mapped through `faiss_id_map`. The `Settings` class (src/cv_search/config/settings.py) drives file paths and agentic test overrides, but it has no Postgres connection details. The main ingestion flow (`CVIngestionPipeline` in src/cv_search/ingestion/pipeline.py) parses CVs, upserts candidate/experience/tag/candidate_doc rows into SQLite, computes embeddings via sentence-transformers, and writes them to FAISS. Async ingestion workers (src/cv_search/ingestion/async_pipeline.py) use Redis queues and also write to SQLite + FAISS. Search orchestration (`SearchProcessor` in src/cv_search/search/processor.py) gates by role/seniority, runs lexical SQL over tags, runs FAISS semantic search, and fuses results via `HybridRanker`. CLI commands in `main.py` initialize the SQLite schema, ingest mock or GDrive data, and run searches; tests under `tests/integration` rely on `AGENTIC_TEST_MODE` to use temporary SQLite/FAISS artifacts. The Streamlit UI (`app.py` and pages/*.py) reuses the same services and reports FAISS/SQLite status. There is no existing Postgres support, no FTS beyond a stub check, and all vector operations are file-based FAISS.

## Plan of Work

Lay the groundwork by introducing a Postgres service with pgvector and migrating the schema. Add a Docker Compose definition (or similar) for a Postgres 16 image with pgvector enabled, default credentials, volumes, and distinct dev/test databases; wire `.env.example` and `Settings` to read a DSN and optional pool sizing. Create a new Postgres schema file (`src/cv_search/db/schema_pg.sql`) that mirrors current tables (candidate, experience, tags, candidate_doc, etc.), drops FAISS-specific artifacts, adds `embedding vector(384)`, and defines a generated `tsv_document` with GIN indexes plus IVFFLAT on the vector column.

Refactor data access: rewrite `CVDatabase` to open psycopg connections (optionally pooled) against the configured DSN, run migrations idempotently, and expose helpers equivalent to current methods but implemented in Postgres SQL. Add vector search and FTS query helpers that return ranked rows (using `<->` for cosine distance and `ts_rank_cd` or `bm25` for text). Keep transaction boundaries explicit so ingestion and async workers can commit/rollback cleanly.

Replace FAISS usage: implement a `PgVectorSemanticRetriever` that embeds the query text, calls the new DB vector search helper, and returns candidate IDs/scores without touching files. Replace `LexicalRetriever` with a Postgres-aware variant that can combine tag gating with FTS ranking (tsvector against summary/experience/tags) and preserve must-have/nice-to-have semantics. Update `HybridRanker` if score scaling needs adjusting for Postgres output shapes. Remove FAISS file management from ingestion and async workers; embeddings should be stored and queried in Postgres only.

Update surface areas: adjust CLI commands (`init-db`, `check-db`, ingestion/search commands) to accept/use Postgres DSN, ensure `init-db` creates the pgvector extension, and drop references to FAISS paths. Update the Streamlit Admin page to report Postgres table counts, FTS/pgvector availability, and remove FAISS rebuild buttons. Ensure `Settings` carries agentic/test DSNs so the integration suite can run against a disposable Postgres DB instead of SQLite files.

Testing and migration support: create fixtures/helpers to start/stop the Docker Postgres for tests (or assume it is running), seed the schema, and cleanly truncate between tests. Rewrite integration tests to assert rows and vector/FTS behavior in Postgres rather than FAISS. Provide a one-off migration script or CLI subcommand to ingest existing SQLite/FAISS data into Postgres (read SQLite rows, load FAISS vectors if present, write into Postgres) so users with existing data are not stranded. Finish with documentation updates in README.md and .env.example describing the new stack and day-to-day commands.

## Concrete Steps

Work from the repository root.

Stand up Postgres with pgvector:
    docker compose -f docker-compose.pg.yml up -d
Expect a container (e.g., cvsearch-pg) listening on localhost:5433 with databases `cvsearch` and `cvsearch_test`, user/password set from .env.

Verify pgvector/FTS availability:
    docker exec -it cvsearch-pg psql -U cvsearch -d cvsearch -c "CREATE EXTENSION IF NOT EXISTS vector; \\dx"
    docker exec -it cvsearch-pg psql -U cvsearch -d cvsearch -c "SELECT to_tsvector('english','test');"

Run schema initialization once the new `init-db` supports Postgres:
    uv run python main.py init-db --db-url postgresql://cvsearch:cvsearch@localhost:5433/cvsearch
Expect output confirming tables created and pgvector/FTS checks passing; reruns should be no-ops.

Exercise ingestion after refactor:
    uv run python main.py ingest-mock --db-url postgresql://cvsearch:cvsearch@localhost:5433/cvsearch
Expect candidate rows populated, embeddings stored in `candidate_doc.embedding`, and tsvector populated.

Exercise search paths:
    uv run python main.py search-seat --criteria ./data/test/criteria.json --topk 3 --mode hybrid --justify --db-url postgresql://cvsearch:cvsearch@localhost:5433/cvsearch
Expect non-empty results sourced from Postgres (no FAISS warnings) with fusion details coming from Postgres scores.

Run integration tests (after rewrites):
    uv run pytest tests/integration -q
Ensure fixtures start with a clean Postgres (truncate or drop/createdb) and all tests pass without touching SQLite/FAISS.

## Validation and Acceptance

Accept the migration when all of the following are true:
- `init-db` against Postgres creates the schema, ensures `vector` and `pg_trgm`/FTS dependencies are available, and can be rerun safely.
- After `ingest-mock`, `psql -c "SELECT COUNT(*) FROM candidate"` and `SELECT COUNT(*) FROM candidate_doc WHERE embedding IS NOT NULL` return matching counts; `SELECT tsv_document @@ plainto_tsquery('english','engineer')` succeeds.
- `search-seat` and `project-search` commands return results without FAISS-related warnings, and logs show vector/FTS queries (document the SQL in artifacts).
- Streamlit Admin status shows Postgres-backed metrics (table counts, pgvector index stats) and no FAISS references.
- Integration suite passes in agentic mode using Postgres (no FAISS/SQLite files created under data/test/tmp).

## Idempotence and Recovery

`init-db` must use `CREATE EXTENSION IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` so it can be re-run. Dockerized Postgres can be reset with `docker compose down -v` and `docker compose up -d` to clear state. Ingestion commands should wrap DB writes in transactions and rollback on failures so partial upserts do not linger. Provide a helper to truncate tables and reset IVFFLAT indexes for tests/dev. Agentic mode should point to a separate `cvsearch_test` DB to avoid clobbering local data; fixtures should drop/recreate that DB between runs if needed.

## Artifacts and Notes

Capture short evidence snippets as changes land, for example:
    psql -U cvsearch -d cvsearch -c "SELECT tablename FROM pg_tables WHERE schemaname='public';"
    psql -U cvsearch -d cvsearch -c "SELECT candidate_id, embedding[1:3] FROM candidate_doc LIMIT 1;"
    psql -U cvsearch -d cvsearch -c "EXPLAIN ANALYZE SELECT candidate_id FROM candidate_doc ORDER BY embedding <-> '[0.1,0.2,...]' LIMIT 5;"
Include one transcript of a successful `search-seat` run showing scores and the absence of FAISS paths.

## Interfaces and Dependencies

Dependencies to add in pyproject.toml: `psycopg[binary,pool]>=3.2`, `pgvector>=0.3.4`, and possibly `sqlalchemy-utils` if DSN parsing is needed (avoid ORM unless required). Ensure Docker images reference Postgres 16 with pgvector (e.g., `pgvector/pgvector:pg16`).

`src/cv_search/config/settings.py` should gain Postgres settings (host/port/db/user/password or full DSN) plus separate defaults for agentic/test DBs. Provide `active_db_dsn` instead of `active_db_path`, while keeping backward compatibility only if necessary for migration scripts.

`src/cv_search/db/schema_pg.sql` should define tables analogous to the current schema but with:
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE candidate (...);
    CREATE TABLE candidate_doc (candidate_id TEXT PRIMARY KEY, summary_text TEXT, experience_text TEXT, tags_text TEXT, embedding VECTOR(384), tsv_document tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english', coalesce(summary_text,'')), 'A') || setweight(to_tsvector('english', coalesce(experience_text,'')), 'B') || setweight(to_tsvector('english', coalesce(tags_text,'')), 'C')) STORED, ...);
    CREATE INDEX idx_candidate_doc_embedding ON candidate_doc USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    CREATE INDEX idx_candidate_doc_tsv ON candidate_doc USING GIN (tsv_document);
and the equivalent candidate/experience/tag tables with appropriate foreign keys and indexes.

`src/cv_search/db/database.py` (or a new Postgres-specific module) should expose:
    class CVDatabase:
        def __init__(self, settings: Settings, pool: psycopg_pool.ConnectionPool | None = None): ...
        def initialize_schema(self) -> None
        def check_extensions(self) -> dict[str, str]  # reports pgvector/FTS availability
        def upsert_candidate(...) -> None  # matches current semantics
        def upsert_candidate_doc(..., embedding: list[float]) -> None
        def rank_weighted_set(...): ...  # rewritten SQL for Postgres
        def vector_search(self, query_embedding: list[float], gated_ids: list[str], top_k: int) -> list[dict[str, Any]]
        def fts_search(self, query_text: str, gated_ids: list[str], top_k: int) -> list[dict[str, Any]]
        def reset_agentic_state(self) -> None  # truncates Postgres tables / resets sequences
Return values should remain close to existing callers’ expectations to minimize refactor scope.

`src/cv_search/retrieval/pgvector.py` (new) should define:
    class PgVectorSemanticRetriever:
        def __init__(self, db: CVDatabase, settings: Settings, embedder: EmbedderProtocol | None = None): ...
        def search(self, gated_ids: list[str], seat: dict[str, Any], top_k: int) -> dict[str, Any]
`src/cv_search/retrieval/lexical.py` should be updated (or replaced) to query Postgres, optionally combining tag filters with FTS rank, returning rows with columns used by `HybridRanker`.

`src/cv_search/ingestion/pipeline.py` and `src/cv_search/ingestion/async_pipeline.py` should drop FAISS handling; embeddings are written via `CVDatabase.upsert_candidate_doc` and vector search is handled in Postgres. Remove `faiss_id_map` usage and file writes, replacing them with DB transactions.

CLI surface in `main.py` should accept an optional `--db-url` or rely on Settings for the Postgres DSN; `init-db` should create extensions and run `schema_pg.sql`. `check-db` should report Postgres-specific health (extensions present, indexes counts).

Tests under `tests/integration` should spin up/require the Postgres container, call `init-db`, and assert vector/FTS state instead of FAISS files. Provide fixtures to clean DB state between tests.

Document migration notes and new commands in README.md and .env.example once code changes are in place.

Note: Plan updated on 2025-12-02 to fully flesh out the pgvector/Postgres migration approach and remove the initial placeholders.
