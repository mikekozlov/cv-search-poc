# Agentic Integration and Testing Refresh

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Maintain this document in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

The goal is to redesign cv-search so an automated coding agent can make changes and immediately validate them through deterministic integration tests. After implementation, anyone (or any agent) should be able to run a single command to rebuild a clean SQLite + FAISS state from fixtures, exercise ingestion (sync and async), and verify search outputs without network access. The observable outcome is a passing integration suite that proves: mock CVs ingest, search returns expected candidates for provided criteria, and the async watcher->extractor->enricher path updates the index reliably.

## Progress

- [x] (2025-12-01 20:23Z) Reviewed repository, PLANS.md, and identified injection points and test gaps for agentic mode.
- [x] (2025-12-01 20:41Z) Implemented agentic test mode, deterministic OpenAI/embedder stubs, injectable ingestion/search/async pipelines, and reset helpers.
- [x] (2025-12-01 20:41Z) Added agentic fixtures (LLM stubs, expected search, sample inbox files) plus integration tests and helper runner.
- [x] (2025-12-01 20:41Z) Ran agentic suite via `python scripts/run_agentic_suite.py` (pytest unavailable; manual fallback executed end-to-end).
- [x] (2025-12-01 20:43Z) Documented outcomes, artifacts, and plan updates after the agentic suite run.

## Surprises & Discoveries

- OpenAIClient and LocalEmbedder are hard-wired to external services (API key + model download). In restricted or offline environments the current flows cannot run, so deterministic stubs and dependency injection are mandatory for any agentic integration tests. Evidence: `src/cv_search/clients/openai_client.py` raises when no API key; `src/cv_search/retrieval/local_embedder.py` downloads `all-MiniLM-L6-v2`.
- The README still lists missing helpers (`Settings.test_data_dir`, `CVDatabase.get_or_create_faiss_id`) as gaps, but these now exist in code (`src/cv_search/config/settings.py`, `src/cv_search/db/database.py`). The plan must reconcile docs vs. code so tests assert the real behavior, not outdated guidance.
- Local environment lacked `pytest` and `redis` packages; the agentic suite now falls back to an in-process runner with a mocked `redis` module for async tests. Evidence: `scripts/run_agentic_suite.py` raised `ModuleNotFoundError: pytest` and `tests/integration/test_async_agentic.py` mocks `redis`.

## Decision Log

- Decision: Introduce an explicit "agentic test mode" (env var flag) that swaps OpenAIClient and LocalEmbedder for deterministic stubs and forces test-specific paths for DB/index artifacts. Rationale: keeps integration runs reproducible without secrets or downloads and protects production code paths. Date/Author: 2025-12-01 / agent.
- Decision: Reuse `data/test/mock_cvs.json` and `data/test/criteria.json` as the canonical integration fixtures, extending them only if coverage gaps remain. Rationale: existing fixtures mirror expected search targets and reduce setup time for agents. Date/Author: 2025-12-01 / agent.
- Decision: Add a stub CV parser for agentic mode and prefer Click's `CliRunner` plus a manual runner fallback when pytest is missing; mock `redis` in async tests to avoid external services. Rationale: keeps tests runnable inside restricted sandboxes without subprocess or network issues. Date/Author: 2025-12-01 / agent.

## Outcomes & Retrospective

Agentic test mode now exercises ingestion, search, and async pipelines without network access or external services. The helper runner (`python scripts/run_agentic_suite.py`) successfully executed all integration tests via the manual fallback (pytest missing in this environment) and produced artifacts under `data/test/tmp/agentic_runs`. The flow confirms that mock ingestion builds a FAISS index at the agentic path, search-seat returns expected candidate IDs for backend criteria, project-search writes per-seat artifacts, and the async watcher→extractor→enricher path ingests a text sample into SQLite/FAISS with an empty DLQ. Remaining risk: pytest must be installed to use the standard runner; otherwise, the manual fallback remains the supported path in constrained environments.

## Context and Orientation

cv-search is a Python 3.11 project managed with uv (editable src layout). The CLI entrypoint is `main.py` (Click commands for DB init, ingestion from mock JSON or Google Drive, search-seat/project-search, async ingestion workers). The Streamlit UI lives in `app.py` and `pages/`, but this plan centers on CLI and ingestion/search backends. Core modules: `src/cv_search/ingestion/pipeline.py` ingests JSON or PPTX-derived CVs into SQLite and FAISS; `src/cv_search/ingestion/async_pipeline.py` defines watcher/extractor/enricher workers communicating via Redis queues (now mockable for tests and able to read `.txt` in agentic mode); `src/cv_search/search/processor.py` orchestrates gating plus lexical/semantic/hybrid ranking; `src/cv_search/config/settings.py` defines paths (DB under `data/db/cvsearch.db`, FAISS index at `data/cv_search.faiss`, test fixtures under `data/test/`). Agentic paths live under `data/test/tmp/` for DB/index/runs, a stub CV parser lives at `src/cv_search/ingestion/parser_stub.py`, and deterministic embeddings come from `src/cv_search/retrieval/embedder_stub.py`. Integration tests now live under `tests/integration/`, with helper runners in `scripts/run_agentic_suite.py` and `tests/integration/helpers.py`.

## Plan of Work

First, add an agentic test mode that gates all external calls. Extend Settings with a boolean flag (for example, `agentic_test_mode`) and derived paths pointing to `data/test/tmp/agentic_*` so runs cannot clobber user data. Refactor OpenAIClient to accept an injectable backend and to return fixture-backed responses when the flag is set or no API key exists; keep the public methods unchanged so callers do not change. Wrap LocalEmbedder behind an interface (or a simple protocol) and provide a stub embedder that generates deterministic vectors from text hashes; teach CVIngestionPipeline (and async pipeline) to accept an embedder/client injection instead of constructing concrete classes internally. Next, harden ingestion flows for reuse in tests: factor out DB/index reset helpers, ensure `CVIngestionPipeline.run_mock_ingestion` honors the agentic paths, allow async workers to run with stubbed CVParser/OpenAIClient without touching Redis or the real filesystem beyond `data/test`, and enable `.txt` samples to flow through watcher/extractor/enricher. Then, build integration fixtures: keep `data/test/mock_cvs.json` as the source of truth, add minimal PPTX/text samples under `data/test/pptx_samples` to drive the async path, and document the expected top candidates for `data/test/criteria.json` so assertions are unambiguous. After dependency injection and fixtures are ready, create integration tests under `tests/integration/`: a CLI flow that runs `init-db`, `ingest-mock`, and `search-seat` (justify off) asserting candidate IDs and artifact files; a project-search flow that inspects per-seat artifacts under the agentic runs dir; and an async ingestion flow that simulates watcher->extractor->enricher using stubs and confirms the DB row plus FAISS entry exist. Finally, add a single entry point (script or documented command) that agents can run after any change to execute all integration suites in a clean temp workspace, and update docs to describe the flag, fixtures, and how to interpret failures.

## Concrete Steps

Work from the repository root (`C:\Users\mykha\Projects\cv-search-poc`).

1) Add agentic test mode plumbing.
    - Extend `src/cv_search/config/settings.py` with `agentic_test_mode: bool = False` plus derived `agentic_db_path`, `agentic_faiss_path`, and `agentic_runs_dir` under `data/test/tmp/` when enabled.
    - Refactor `src/cv_search/clients/openai_client.py` to accept an optional backend or stub implementation; when agentic mode is on or the API key is missing, load deterministic fixtures (small JSON files under `data/test/llm_stubs/`) for criteria parsing, CV parsing, and justification.
    - Introduce an embedder interface and stub in `src/cv_search/retrieval/embedder_stub.py` that returns fixed-dimension normalized vectors derived from a stable hash of the input text; wire `LocalEmbedder` usage sites (`cv_search/ingestion/pipeline.py`, `cv_search/search/processor.py` semantic retriever init) to accept an injected embedder from settings or a factory.

2) Make ingestion and async pipelines injectable and test-friendly.
    - Update `cv_search/ingestion/pipeline.py` constructors to accept `embedder` and `client` parameters (defaulting to current classes) and to honor agentic paths for DB/index when the settings flag is set.
    - Adjust `cv_search/ingestion/async_pipeline.py` workers to accept injected parser/client/embedder/db or factories; in agentic mode, default to stubs and keep queue interactions in-memory (optionally reuse the MockRedisClient from `tests/verify_async_pipeline.py`).
    - Add reset helpers in `cv_search/db/database.py` or a small utility module to drop or recreate the SQLite DB and delete the FAISS index; ensure they are safe to run repeatedly and scoped to agentic paths.

3) Prepare fixtures for deterministic expectations.
    - Keep `data/test/mock_cvs.json` as the ingestion source and add any missing fields required by new code; derive expected top results for `data/test/criteria.json` and store them in `data/test/expected_search.json` (for example, ordered candidate_ids for backend/frontend seats).
    - Add lightweight text or PPTX samples under `data/test/pptx_samples/` that encode one backend and one frontend profile; ensure the stub CVParser reads these without external tools.
    - Create stub LLM responses under `data/test/llm_stubs/` for criteria parsing, CV parsing, and justification so OpenAIClient can read them deterministically.

4) Author integration tests.
    - Add `tests/integration/test_cli_agentic.py` that sets `AGENTIC_TEST_MODE=1`, resets DB/index, runs `uv run python main.py init-db`, `uv run python main.py ingest-mock`, and `uv run python main.py search-seat --criteria data/test/criteria.json --topk 3 --mode hybrid --no-justify` (or justify disabled flag) and asserts the returned candidate_ids match `expected_search.json`; verify the FAISS index file exists and contains the expected vector count.
    - Add `tests/integration/test_project_search_artifacts.py` that runs `project-search` with fixtures, checks `runs/<timestamp>/` exists, and verifies per-seat artifact files written by `SearchRunArtifactWriter`.
    - Add `tests/integration/test_async_agentic.py` that seeds the inbox with fixture PPTX/text, runs watcher/extractor/enricher once with stubs and MockRedis, and asserts the new candidate exists in SQLite and FAISS with no DLQ entries.

5) Provide a single command for agents and document it.
    - Add a helper script (for example, `scripts/run_agentic_suite.py`) or document a one-liner that exports `AGENTIC_TEST_MODE=1` and runs `uv run pytest tests/integration -q`, with a manual fallback if pytest is unavailable.
    - Update README or a short `docs/agentic.md` note to describe the flag, required fixtures, and how to interpret failures; link the ExecPlan to that doc.

## Validation and Acceptance

Acceptance hinges on runnable, deterministic checks. With `AGENTIC_TEST_MODE=1` set and from repo root:

    uv run python main.py init-db
    uv run python main.py ingest-mock
    uv run python main.py search-seat --criteria data/test/criteria.json --topk 3 --mode hybrid --no-justify
    uv run pytest tests/integration -q

If pytest is unavailable, run `python scripts/run_agentic_suite.py`; it will fall back to an in-process runner and still exercise the same flows.

Expected behaviors: the search-seat command returns a JSON payload whose `payload.results` list begins with the candidate_ids recorded in `data/test/expected_search.json`; the FAISS index exists at the agentic path and contains embeddings for every ingested CV; integration tests pass without network access and without requiring real Redis/OpenAI/SentenceTransformer services; async test leaves the DLQ empty and the new candidate present in both SQLite and FAISS. Any deviation should be actionable (for example, missing fixture, path conflict, or stub not engaged).

## Idempotence and Recovery

Agentic mode must use isolated paths under `data/test/tmp/`, so repeated runs can delete and recreate the SQLite DB and FAISS index without impacting user data. Provide a cleanup helper that removes the agentic DB/index/runs directories before each test run. CLI commands are safe to rerun because `init-db` recreates schema and `ingest-mock` rebuilds both DB and index; tests should always call cleanup first to avoid residue. If a run fails midway, rerun the cleanup plus command sequence above; avoid mutating non-test `data/` files in agentic mode.

## Artifacts and Notes

Keep short evidence snippets in this section as work progresses, such as sample outputs from the search-seat command or pytest summaries. For example after the first successful run:

    {"run_dir": "...agentic_runs/20251201-224100", "topK": ["cvnet01-k1l2","cvnet03-o5p6"], ...}
    $ AGENTIC_TEST_MODE=1 python scripts/run_agentic_suite.py
    pytest not installed; running integration tests directly.
    Queued file: backend_sample.txt
    -> Text extracted. Pushed to Enrich Queue.
    -> Enriched and saved: pptx-9a5019b881

## Interfaces and Dependencies

Define stable interfaces to make swapping implementations trivial:

    src/cv_search/clients/openai_client.py:
        class OpenAIBackendProtocol:
            def get_structured_criteria(text: str, model: str, settings: Settings) -> dict: ...
            def get_structured_cv(raw_text: str, role_folder_hint: str, model: str, settings: Settings) -> dict: ...
            def get_candidate_justification(seat_details: str, cv_context: str) -> dict: ...
        class OpenAIClient:
            def __init__(self, settings: Settings, backend: OpenAIBackendProtocol | None = None): ...

    src/cv_search/retrieval/embedder_stub.py:
        class DeterministicEmbedder:
            dims: int
            def get_embeddings(self, texts: list[str]) -> list[list[float]]:
                # derive normalized vectors from stable hashes

    src/cv_search/ingestion/pipeline.py:
        class CVIngestionPipeline:
            def __init__(self, db: CVDatabase, settings: Settings, embedder: EmbedderProtocol | None = None, client: OpenAIClient | None = None, parser: CVParser | None = None): ...
            def reset_agentic_state(self) -> None  # drop DB/index when agentic_test_mode is True

    src/cv_search/ingestion/parser_stub.py:
        class StubCVParser:
            def extract_text(self, file_path: Path) -> str  # read plain text fixtures for agentic runs

    scripts/run_agentic_suite.py:
        - Runs pytest when available; falls back to invoking the integration test functions directly with AGENTIC_TEST_MODE=1.

    tests/integration fixtures:
        data/test/expected_search.json with ordered candidate_ids for each seat.
        data/test/llm_stubs/*.json providing deterministic outputs used by the stub backend.

A note at the bottom should record changes to this plan; keep it updated as the plan evolves.

---
Updated this plan to replace the draft skeleton with a fully specified, PLANS-compliant ExecPlan for the agentic integration redesign (2025-12-01).
Updated with completed agentic mode implementation, fixtures/tests, and validation notes after running the agentic suite (2025-12-01 20:43Z).
