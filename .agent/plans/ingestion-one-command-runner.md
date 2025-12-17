# Add one command to run watcher + workers

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository has an ExecPlan spec at `.agent/PLANS.md`. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Running async ingestion currently requires three terminals: `ingest-watcher` (enqueue), `ingest-extractor` (dequeue/extract), and `ingest-enricher` (dequeue/enrich/upsert). For local development and debugging, it is useful to run everything in one terminal so that logs show the full lifecycle of a file from enqueue to database commit.

After this change, a single Click command (new) starts all three components and streams their logs to the same console with clear prefixes.

## Progress

- [x] (2025-12-16 00:00Z) Draft ExecPlan for one-command runner.
- [x] (2025-12-16 00:00Z) Implement combined command that spawns three subprocesses and streams output.
- [x] (2025-12-16 00:00Z) Run Ruff (format + lint) and unit tests (excluding `tests/integration` and `tests/eval`).

## Surprises & Discoveries

- Observation: The Click CLI supports running the watcher and workers as standalone commands, which makes them easy to compose via subprocesses.
  Evidence: `src/cv_search/cli/commands/async_ingestion.py`.

## Decision Log

- Decision: Implement the one-command runner by spawning three child Python processes (watcher/extractor/enricher) and streaming their stdout with prefixes, rather than running them as threads in-process.
  Rationale: Avoids shared-state/thread-safety concerns around DB connections, OpenAI client, and watchdog observer internals; preserves existing behavior of each component.
  Date/Author: 2025-12-16 / agent

## Outcomes & Retrospective

Outcome: Added `ingest-async-all` for one-terminal local runs; it spawns watcher/extractor/enricher and prefixes their output.

## Context and Orientation

Async ingestion is exposed as three Click commands:

- `ingest-watcher` enqueues file events to `ingest:queue:extract`.
  src/cv_search/cli/commands/async_ingestion.py:9

- `ingest-extractor` dequeues from `ingest:queue:extract` and enqueues to `ingest:queue:enrich`.
  src/cv_search/cli/commands/async_ingestion.py:22

- `ingest-enricher` dequeues from `ingest:queue:enrich` and writes to Postgres.
  src/cv_search/cli/commands/async_ingestion.py:35

The new combined command should live alongside these in `src/cv_search/cli/commands/async_ingestion.py` and call them via `python -m cv_search.cli <command>` so the existing entrypoints remain the source of truth.

## Plan of Work

1. Add a new Click command (e.g., `ingest-async-all`) that:

   - creates an environment for child processes (inherit current env, but force `DB_URL` to match `ctx.settings.db_url` so `--db-url` overrides are respected)
   - spawns `python -u -m cv_search.cli ingest-watcher`, `... ingest-extractor`, and `... ingest-enricher`
   - reads each child’s combined stdout/stderr line-by-line on separate threads and prints them to the parent console with a prefix such as `[watcher]`, `[extractor]`, `[enricher]`
   - terminates all children cleanly on Ctrl+C (KeyboardInterrupt)

2. Run Ruff and unit tests.

## Concrete Steps

From repository root in PowerShell:

1. Format and lint:

    PS C:\Users\<you>\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = "1"
    PS C:\Users\<you>\Projects\cv-search-poc> uv run --extra dev ruff format src tests
    PS C:\Users\<you>\Projects\cv-search-poc> uv run --extra dev ruff check src tests

2. Run unit tests only (exclude integration and eval folders):

    PS C:\Users\<you>\Projects\cv-search-poc> uv run pytest -q tests --ignore=tests/integration --ignore=tests/eval

## Validation and Acceptance

With Redis and Postgres configured and reachable:

- Running `python -m cv_search.cli ingest-async-all` in one terminal starts all three components and prints prefixed logs.
- Editing a `.txt` file under `GDRIVE_LOCAL_DEST_DIR` shows (order may vary slightly):

    [watcher] Queued file: ...
    [extractor] Extractor dequeued: ...
    [extractor] -> Text extracted. Pushed to Enrich Queue.
    [enricher] Enricher dequeued: ...
    [enricher] -> Enriched and saved: ...

## Idempotence and Recovery

This change adds a new command without changing existing ones. If the combined runner misbehaves, use the original three-terminal flow as a fallback and iterate on the combined command.

## Artifacts and Notes

The combined runner’s main value is log visibility; it is not intended to be used as a production supervisor. It should remain simple and easy to reason about.

## Interfaces and Dependencies

- Standard library only for process management: `subprocess`, `threading`, `sys`, `os`.
- Click for printing: `click.echo`.
