# Add more logs for async ingestion queues

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository has an ExecPlan spec at `.agent/PLANS.md`. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

When running the local ingestion watcher and workers, operators need visibility into the “queue lifecycle” of a file: detection/enqueue by the watcher, dequeue by workers, and successful completion or failure. Today the watcher prints “Queued file: …”, but failures in the background watcher thread are silently swallowed, and workers do not explicitly log when they dequeue a task.

After this change, running `python -m cv_search.cli ingest-watcher`, `python -m cv_search.cli ingest-extractor`, and `python -m cv_search.cli ingest-enricher` shows clear console logs for:

- enqueue events (already present, retained)
- dequeue events for both workers
- worker “handled” events (already partially present, clarified)
- watcher callback exceptions (no longer silent) with light throttling to avoid log spam when a dependency (like Redis) is misconfigured

## Progress

- [x] (2025-12-16 00:00Z) Draft ExecPlan for improved watcher/worker logging.
- [x] (2025-12-16 00:00Z) Implement worker dequeue logs and watcher error reporting.
- [x] (2025-12-16 00:00Z) Run Ruff (format + lint) and unit tests (excluding `tests/integration` and `tests/eval`).
- [ ] Confirm watcher shows errors when Redis auth is missing, and shows dequeue/handled logs when Redis works.

## Surprises & Discoveries

- Observation: File watcher exceptions in the scheduler thread are currently swallowed with a bare `except Exception: continue`, which hides Redis connection/auth failures from the terminal.
  Evidence: `src/cv_search/ingestion/file_watch_service.py` `_CoalescingScheduler._run`.

## Decision Log

- Decision: Log watcher callback exceptions to the terminal with a time-based throttle.
  Rationale: Makes configuration failures (e.g., Redis AUTH) visible without flooding logs in a tight loop.
  Date/Author: 2025-12-16 / agent

## Outcomes & Retrospective

Outcome: The watcher no longer silently swallows background callback exceptions, and both workers emit explicit “dequeued” logs so operators can trace files through the queues.

## Context and Orientation

The async ingestion flow is split into three Click commands:

- `ingest-watcher`: watches `Settings.gdrive_local_dest_dir` for file changes and enqueues `FileDetectedEvent` messages to `ingest:queue:extract`.
  src/cv_search/cli/commands/async_ingestion.py:9
  src/cv_search/ingestion/async_pipeline.py:24
  src/cv_search/ingestion/file_watch_service.py:111

- `ingest-extractor`: dequeues from `ingest:queue:extract`, extracts text, and enqueues `TextExtractedEvent` messages to `ingest:queue:enrich`.
  src/cv_search/cli/commands/async_ingestion.py:23
  src/cv_search/ingestion/async_pipeline.py:74

- `ingest-enricher`: dequeues from `ingest:queue:enrich`, calls the LLM + embedder, and writes the candidate doc to Postgres.
  src/cv_search/cli/commands/async_ingestion.py:37
  src/cv_search/ingestion/async_pipeline.py:150

`FileWatchService` uses watchdog (filesystem events) plus a coalescing scheduler thread; the scheduler currently swallows all callback exceptions.
src/cv_search/ingestion/file_watch_service.py:40

## Plan of Work

1. Update the watcher scheduler exception handling so that callback failures are reported via `click.secho(...)` with basic throttling.
   src/cv_search/ingestion/file_watch_service.py:70

2. Add explicit dequeue logs to `ExtractorWorker.run` and `EnricherWorker.run` so operators can see that tasks are being consumed.
   src/cv_search/ingestion/async_pipeline.py:86
   src/cv_search/ingestion/async_pipeline.py:172

3. (Cleanup) Remove the previously-added PowerShell helper script if it exists, since the desired interface is “run the Click command via Python”.

## Concrete Steps

From repository root in PowerShell:

1. Format and lint:

    PS C:\Users\<you>\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = "1"
    PS C:\Users\<you>\Projects\cv-search-poc> uv run --extra dev ruff format src tests
    PS C:\Users\<you>\Projects\cv-search-poc> uv run --extra dev ruff check src tests

2. Run unit tests only (exclude integration and eval folders):

    PS C:\Users\<you>\Projects\cv-search-poc> uv run pytest -q tests --ignore=tests/integration --ignore=tests/eval

## Validation and Acceptance

Acceptance is observed behavior:

1. If Redis is misconfigured (e.g., requires AUTH but `REDIS_URL` has no password), changing a `.txt` file under `data/gdrive_inbox` results in a visible error line in the watcher console (not silent).

2. With a correct `REDIS_URL`, editing a `.txt` file results in:

- watcher logs: `Queued file: ...` (existing behavior)
- extractor logs: a “Dequeued …” line, followed by extraction logs, then “Pushed to Enrich Queue”
- enricher logs: a “Dequeued …” line, followed by “Enriching candidate: …”, and finally “-> Enriched and saved: …” on success

## Idempotence and Recovery

These changes are additive logging only. If logs are too noisy, revert by removing the added `click.echo`/`click.secho` lines; behavior should otherwise remain unchanged.

## Artifacts and Notes

Expected example log snippets (not exact):

    Watcher started. Monitoring ...\data\gdrive_inbox...
    Queued file: CANDIDATES/.../resume.pptx
    Extractor dequeued: CANDIDATES/.../resume.pptx
    Extracting text from: resume.pptx
    -> Text extracted. Pushed to Enrich Queue.
    Enricher dequeued: CANDIDATES/.../resume.pptx
    Enriching candidate: <candidate_id>
    -> Enriched and saved: <candidate_id>

## Interfaces and Dependencies

- Use existing Click output (`click.echo`, `click.secho`) for terminal-visible logs.
- Do not change queue names or message schemas.
