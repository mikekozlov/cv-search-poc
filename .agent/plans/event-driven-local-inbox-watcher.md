# Event-driven local inbox watching for async ingestion

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository defines how to author and maintain ExecPlans in `.agent/PLANS.md`, which must be followed and kept in sync with implementation progress.

## Purpose / Big Picture

Today the async ingestion `Watcher` polls the Google Drive local inbox directory by walking the whole tree every few seconds. After this change, the watcher reacts to filesystem change notifications (create/modify/move) using a cross-platform library (`watchdog`) on Windows, and still performs a reconciliation scan so it does not miss files when the watcher is down. This reduces latency and CPU cost, and is resilient to rclone’s “write then rename / multiple modify events” patterns by debouncing and waiting for file stability before enqueueing work.

The user-visible behavior is: running `cv-search ingest-watcher` starts a process that immediately enqueues tasks for any new or modified `*.pptx` / `*.txt` files under `data/gdrive_inbox`, without needing polling intervals, and without re-enqueueing the same unchanged file repeatedly.

## Progress

- [x] (2025-12-16 11:55Z) Create ExecPlan for event-driven watcher implementation.
- [x] (2025-12-16 11:56Z) Add `watchdog` dependency and update lockfile.
- [x] (2025-12-16 12:05Z) Implement `FileWatchService` (watch + reconcile + debounce + stability check).
- [x] (2025-12-16 12:06Z) Add Redis cross-process dedupe primitive (`SET NX` + TTL) to `RedisClient` and the in-memory stub.
- [x] (2025-12-16 12:07Z) Switch async `Watcher` to `FileWatchService` (keep CLI command name stable).
- [x] (2025-12-16 12:10Z) Fix candidate identity and “skip unchanged” logic to use `source_gdrive_path` (relative path) instead of basename-only collisions.
- [x] (2025-12-16 12:14Z) Add/adjust unit tests for candidate-id derivation and dedupe behavior (no integration/eval tests).
- [x] (2025-12-16 12:15Z) Run Ruff format + lint and unit tests; fix failures.
- [x] (2025-12-16 12:16Z) Document outcomes and any follow-ups in this plan.

## Surprises & Discoveries

- Observation: `RedisClient.pop_from_queue(..., timeout=0)` blocks forever (redis BLPOP semantics), so unit tests must not use `timeout=0` when asserting an empty queue.
  Evidence: Unit test run hung until replacing the empty-queue assertion with a non-blocking `llen` check.

## Decision Log

- Decision: Use `source_gdrive_path` (relative path under the inbox) as the canonical per-file identity for ingestion and candidate ID derivation.
  Rationale: Basename-only keys collide when different folders contain the same filename (e.g., `CV.pptx`), causing incorrect dedupe and overwrites at scale.
  Date/Author: 2025-12-16 / GPT-5.2

- Decision: Keep Redis lists (BLPOP) as the queue transport for now; add a lightweight Redis `SET NX` + TTL dedupe to avoid event storms.
  Rationale: Migrating to Redis Streams would be a larger behavioral change; this plan targets event-driven detection + idempotency guardrails while preserving existing worker semantics.
  Date/Author: 2025-12-16 / GPT-5.2

- Decision: Keep `Watcher._scan_and_publish()` as a test-friendly reconciliation helper by delegating to `FileWatchService.reconcile_once()`.
  Rationale: Existing integration tests and debugging workflows use a “scan once and enqueue” entry point without starting a long-running watchdog observer thread.
  Date/Author: 2025-12-16 / GPT-5.2

## Outcomes & Retrospective

The async ingestion watcher is now event-driven via `watchdog`, with reconciliation scans, per-file debouncing, and a stability check to avoid ingesting partially-written files. Enqueue storms are controlled with a Redis `SET NX` dedupe key with TTL. Candidate identity and “skip unchanged” logic now key off `source_gdrive_path` (relative path) instead of basename-only `source_filename`, preventing collisions across folders. Ruff is clean and unit tests pass.

Follow-up work (not in scope here) would be upgrading Redis lists to Redis Streams for at-least-once processing semantics and adding per-candidate worker locks.

## Context and Orientation

The async ingestion pipeline lives under `src/cv_search/ingestion/async_pipeline.py` and is wired into the CLI via `src/cv_search/cli/commands/async_ingestion.py`. The current `Watcher` periodically scans `Settings.gdrive_local_dest_dir` for `*.pptx` and `*.txt`, compares filesystem mtime with a DB lookup keyed by `candidate.source_filename`, and enqueues `FileDetectedEvent` payloads to Redis `ingest:queue:extract`.

The batch ingestion pipeline is `src/cv_search/ingestion/pipeline.py::CVIngestionPipeline.run_gdrive_ingestion`, which also scans the local inbox and filters unchanged files. Both the batch and async paths currently derive `candidate_id` from `md5(file_path.name)`, which collides across folders.

The Postgres schema (see `src/cv_search/db/schema_pg.sql`) already includes both `source_filename` and `source_gdrive_path` on the `candidate` table. `source_gdrive_path` is intended to be the unique per-file path identity, and in the batch pipeline it is already populated as the relative path within the inbox.

Terms used in this plan:

“Filesystem events” means OS notifications when a file is created/modified/moved in a directory tree. On Windows this is backed by `ReadDirectoryChangesW`.

“Reconciliation scan” means a periodic walk of the directory tree that enqueues work for any file that appears new/modified compared to the database. This prevents missed ingestion when the watcher process is stopped or the OS drops events.

“Debounce” means coalescing a burst of events for the same file path into a single processing attempt after a short quiet period.

“Stability check” means waiting until the file’s size and modification time stop changing for a small window before enqueueing ingestion, to avoid reading partially written files.

“Dedupe key” means a Redis key set with `SET NX` and an expiry so duplicate events across processes or event storms are dropped.

## Plan of Work

1. Add the `watchdog` dependency to `pyproject.toml` and update `uv.lock` so the project installs consistently.

2. Introduce a new module `src/cv_search/ingestion/file_watch_service.py` that:

   - Performs an initial reconciliation scan of `Settings.gdrive_local_dest_dir` for `*.pptx` / `*.txt`.
   - Starts a watchdog observer to receive file create/modify/move events recursively.
   - Debounces events per path and performs a stability check (signature unchanged for a window).
   - Enqueues a `FileDetectedEvent` dict to Redis `ingest:queue:extract` only if a Redis dedupe key can be acquired (`SET NX` + TTL).

3. Extend `src/cv_search/ingestion/redis_client.py`:

   - Add `RedisClient.set_if_absent(key, value, ttl_seconds) -> bool` implemented via redis-py `set(..., nx=True, ex=ttl_seconds)`.
   - Add an equivalent implementation to the in-memory redis stub used by tests (including TTL expiry behavior sufficient for tests).

4. Replace polling logic in `src/cv_search/ingestion/async_pipeline.py::Watcher.run` with the new `FileWatchService` (run forever until Ctrl+C). Keep CLI entry points unchanged.

5. Fix file identity and “skip unchanged” logic:

   - Add `CVDatabase.get_last_updated_for_gdrive_paths(...)` and `CVDatabase.get_candidate_last_updated_by_source_gdrive_path(...)` in `src/cv_search/db/database.py`.
   - Update the batch ingestion file selection (`src/cv_search/ingestion/pipeline.py::_partition_gdrive_files`) and async reconciliation logic to use `source_gdrive_path` (relative path) instead of `source_filename`.
   - In `src/cv_search/ingestion/source_identity.py`, introduce a single helper to derive `candidate_id` from `source_gdrive_path` (e.g., `pptx-<md5(rel_path)[:10]>`) and use it in both batch and async ingestion paths.

6. Add unit tests under `tests/` (not `tests/integration` or `tests/eval`) to validate:

   - `candidate_id` differs for two files with the same basename in different folders.
   - Redis `set_if_absent` works with the in-memory backend and prevents duplicate enqueue.

7. Run formatting, linting, and unit tests (PowerShell), fix any failures, and update this ExecPlan with outcomes.

## Concrete Steps

All commands are PowerShell from the repository root `C:\Users\mykha\Projects\cv-search-poc`.

1. Install/update dependencies after editing `pyproject.toml`:

   - `PS C:\Users\mykha\Projects\cv-search-poc> uv lock`
   - `PS C:\Users\mykha\Projects\cv-search-poc> uv sync --extra dev`

2. Format and lint (must be clean before tests):

   - `PS C:\Users\mykha\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = \"1\"`
   - `PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff format src tests`
   - `PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff check src tests`

3. Run unit tests (explicitly excluding integration/eval folders):

   - `PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY = \"test-key\"`
   - `PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests -q --ignore=tests\\integration --ignore=tests\\eval`

Expected transcript snippet:

   - `...`
   - `N passed`

## Validation and Acceptance

Acceptance is demonstrated by both behavior and tests:

1. Behavior: with Redis and Postgres already running, start the watcher and observe that creating or modifying a file under `data\\gdrive_inbox` causes exactly one “Queued file” log line after a short debounce/stability delay, and repeated writes to the same file do not enqueue duplicates within the dedupe TTL.

2. Unit tests: running the unit test command in `Concrete Steps` completes with all tests passing, and the new tests added for candidate ID and Redis dedupe fail before this change and pass after.

## Idempotence and Recovery

All code changes are additive and safe to retry. If the watchdog observer fails to start (e.g., missing dependency), the failure is immediate at process start and does not corrupt state. The watcher can be restarted; reconciliation scan ensures missed files are detected on startup. Redis dedupe keys expire automatically, so a restart does not permanently block ingestion.

If required, rollback is: revert the new module and switch `Watcher` back to polling; the rest of the ingestion pipeline remains unchanged.

## Artifacts and Notes

Key validation transcripts:

    PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff check src tests
    All checks passed!

    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests -q --ignore=tests\integration --ignore=tests\eval
    24 passed in 6.71s

## Interfaces and Dependencies

Dependencies:

- Add `watchdog` to `pyproject.toml` for filesystem notifications on Windows/Linux/macOS.

Key interfaces to exist after completion:

- In `src/cv_search/ingestion/redis_client.py`, define:

    def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool: ...

- In `src/cv_search/db/database.py`, define:

    def get_candidate_last_updated_by_source_gdrive_path(self, source_gdrive_path: str) -> Optional[str]: ...
    def get_last_updated_for_gdrive_paths(self, paths: Iterable[str]) -> Dict[str, Optional[str]]: ...

- In `src/cv_search/ingestion/file_watch_service.py`, define a `FileWatchService` class with `start()`, `stop()`, and `run_forever()` suitable for use by `Watcher`.
- In `src/cv_search/ingestion/source_identity.py`, define:

    def candidate_id_from_source_gdrive_path(source_gdrive_path: str) -> str: ...

Plan revision note (2025-12-16): Updated milestones to reflect completed implementation, captured the BLPOP `timeout=0` test hang discovery, and recorded the compatibility decision to keep `Watcher._scan_and_publish()`.
