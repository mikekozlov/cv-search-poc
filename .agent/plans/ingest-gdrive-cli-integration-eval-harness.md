# Integration and Eval Harness for ingest-gdrive CLI

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This plan must be maintained in accordance with .agent/PLANS.md.

## Purpose / Big Picture

Enable a contributor to add a deterministic integration test and a repeatable evaluation harness for the command `python main.py ingest-gdrive --file test.pptx`. After implementation, a novice can run a single CLI-driven ingestion using stubs (no network or model downloads), see the resulting Postgres rows and embedding column populated, and optionally run an eval script against golden labels to quantify LLM output quality for this flow.

## Progress

- [x] (2025-12-03 12:33Z) Drafted initial ExecPlan for ingest-gdrive integration/eval harness.
- [x] (2025-12-03 12:42Z) Implemented deterministic integration test for `ingest-gdrive --file` with stubbed parser/LLM/embedder.
- [x] (2025-12-03 12:42Z) Added offline eval harness with golden expectations and optional JSONL output.
- [x] (2025-12-03 12:46Z) Ran integration test suite with new coverage; documented outcomes.

## Surprises & Discoveries

- Observation: Pydantic Settings favored environment variables over constructor arguments, so test helpers needed to set DB_URL in os.environ before instantiating Settings to ensure connections target the test database.
  Evidence: CVDatabase reported dsn as `.../cvsearch` until helpers updated env priming; after the change dsn became `.../cvsearch_test`.
- Observation: Relative RUNS_DIR from .env.test produced relative artifact paths (e.g., `data/test/tmp/runs/...`), breaking assertions that expect absolute locations.
  Evidence: test_project_search_artifacts failed until helpers overrode RUNS_DIR/DATA_DIR/GDRIVE paths to absolute values after loading .env.test.
- Observation: Loading .env.test via dotenv and normalizing path entries is sufficient; no hardcoded test constants are required once env is sourced from that file.
  Evidence: After refactor, Settings pulled all values from .env.test and integration suite passed with expected paths.

## Decision Log

- Decision: Gate the eval harness behind RUN_INGEST_EVAL to keep default test runs fast, and allow WRITE_EVAL_OUTPUT to opt into JSONL emission under runs/evals.
  Rationale: Avoid slowing CI while still providing an on-demand quality metric pipeline.
  Date/Author: 2025-12-03 / assistant
- Decision: Monkeypatch CVParser.extract_text in both integration and eval tests to avoid python-pptx dependency on placeholder files.
  Rationale: Keeps tests deterministic/offline while still exercising the ingestion pipeline surface.
  Date/Author: 2025-12-03 / assistant
- Decision: Use module-level helper imports (tests.integration.helpers) to avoid pytest collecting helper functions named with `test_*`.
  Rationale: Prevents noisy PytestReturnNotNone warnings while preserving shared utilities.
  Date/Author: 2025-12-03 / assistant
- Decision: Load .env.test via load_dotenv in helpers to prime env for tests (DB_URL, DATA_DIR, RUNS_DIR, GDRIVE_LOCAL_DEST_DIR, stub flags) instead of hardcoding overrides in code.
  Rationale: Single source of truth for test env values and easier to edit without code changes.
  Date/Author: 2025-12-03 / assistant

## Outcomes & Retrospective

- Added deterministic end-to-end ingestion test and opt-in eval harness with golden tags. Helpers now prep inbox fixtures, load emitted JSON, and enforce test DB env priming. Integration suite (`python -m pytest tests\integration -q`) passes with existing warnings only; eval harness remains gated by RUN_INGEST_EVAL. Follow-up: consider renaming helper functions that start with `test_` or marking warnings as expected to reduce noise in unrelated suites.

## Context and Orientation

The CLI entrypoint is `main.py`, which exposes a Click group from `src/cv_search/cli/__init__.py`. The ingestion command `ingest-gdrive` is defined in `src/cv_search/cli/commands/ingestion.py`; it builds a `CLIContext` (`src/cv_search/cli/context.py`) that wires `Settings`, `OpenAIClient`, and `CVDatabase`, then constructs `CVIngestionPipeline` (`src/cv_search/ingestion/pipeline.py`) and calls `run_gdrive_ingestion(target_filename=...)`.

`CVIngestionPipeline` loads role lexicons from `data/lexicons`, enumerates `.pptx` and `.txt` files under `settings.gdrive_local_dest_dir`, parses each via `CVParser.extract_text` (`src/cv_search/ingestion/cv_parser.py`), calls `OpenAIClient.get_structured_cv`, normalizes tags, writes a debug JSON to `<data_dir>/ingested_cvs_json`, and writes candidate rows plus embeddings into Postgres using `CVDatabase`. Embeddings are stored in the `candidate_doc.embedding` vector column (pgvector); there is no FAISS in the current code. The pipeline uses `LocalEmbedder` unless `USE_DETERMINISTIC_EMBEDDER` or `HF_HUB_OFFLINE` is set, in which case `DeterministicEmbedder` is used. `OpenAIClient` falls back to `StubOpenAIBackend` when `USE_OPENAI_STUB` is true or no API key is present, using fixtures in `data/test/llm_stubs`.

Existing integration helpers live in `tests/integration/helpers.py`: `test_env()` sets `DB_URL`, `DATA_DIR`, `RUNS_DIR`, `GDRIVE_LOCAL_DEST_DIR`, `OPENAI_API_KEY`, `USE_DETERMINISTIC_EMBEDDER`, `HF_HUB_OFFLINE`, and `USE_OPENAI_STUB`. `cleanup_test_state()` clears Postgres tables and wipes `runs/` and the GDrive inbox under `data/test`. Postgres schema initialization is available via the CLI command `init-db` (in `db_admin.py`), and instructions in AGENTS.md require running integration tests against Postgres via `docker-compose.pg.yml` with DSN `postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test`.

The test repository layout already includes `tests/integration/test_cli_integration.py` and `test_async_ingestion.py` that use `CliRunner` with `run_cli()` from helpers. We will follow this pattern for the new ingestion test to keep the suite cohesive.

## Plan of Work

Establish two deliverables: (1) a deterministic integration test that exercises `ingest-gdrive --file test.pptx` end-to-end with stubs and Postgres, and (2) a separate eval harness that can compare ingestion output to golden expectations when running with real or stubbed LLMs.

For the integration test, add `tests/integration/test_ingest_gdrive_cli.py`. Use `test_env()` to set environment variables so Postgres points at `cvsearch_test`, data directories resolve to `data/test`, and deterministic embedder plus stubbed OpenAI backend are enforced (no network or model downloads). Prepare a fake PPTX placeholder under `data/test/gdrive_inbox/CVs/backend_engineer/test.pptx`; because the test will monkeypatch `CVParser.extract_text` to return deterministic text containing a backend hint, the PPTX contents can be dummy bytes. Use `cleanup_test_state()` to clear prior runs. Invoke `init-db` then `ingest-gdrive --file test.pptx` via `run_cli()`. After ingestion, open `CVDatabase` with `test_settings()` and assert: one candidate row exists for `source_filename='test.pptx'`; role/domain/tech/seniority tags include backend_engineer, healthtech, dotnet/postgresql/kafka (from the backend stub fixture); `candidate_doc.embedding` is non-null (DeterministicEmbedder returns length 384); `experience` rows reflect stored tech/domain CSV; and the debug JSON file exists under `data/test/ingested_cvs_json`. Keep assertions robust to minor text formatting but strict on tags and counts.

For the eval harness, create `tests/eval/test_ingest_gdrive_eval.py` (or `scripts/eval_ingest_gdrive.py` if we prefer a manual runner). Provide a small golden label file, e.g., `tests/fixtures/golden/ingest_gdrive_backend.yaml`, capturing expected role/domain/tech tags for `test.pptx`. The harness should: (a) prepare the inbox and DB like the integration test (optionally allowing an env flag to disable stubbing for live LLM runs), (b) run `ingest-gdrive --file test.pptx`, (c) load the JSON emitted to `data/test/ingested_cvs_json/<candidate_id>.json` and the DB rows for that candidate, and (d) compute simple precision/recall/F1 for role, domain, and tech tags against the golden file. Mark the pytest as `@pytest.mark.slow` or gate the script behind `if __name__ == "__main__"` so default CI runs remain fast. Emit a short metrics dict or table; store any JSONL outputs under `runs/evals/` to avoid polluting repo roots.

If helpers need to be shared, extend `tests/integration/helpers.py` with utilities to (1) write the placeholder PPTX file and role folder layout, and (2) read the emitted candidate JSON. Keep helpers idempotent and ensure cleanup removes `data/test/gdrive_inbox`, `data/test/tmp/runs`, and `data/test/ingested_cvs_json` between runs.

## Concrete Steps

Prepare Postgres and environment (required before coding or running tests):
    PS C:\Users\mykha\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR = "data/test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:USE_DETERMINISTIC_EMBEDDER = "1"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:USE_OPENAI_STUB = "1"

Implementation steps (to be performed and checked off in Progress as they complete):
1. Add or extend helpers in `tests/integration/helpers.py` to create the gdrive inbox layout and dummy PPTX, and to load the emitted JSON for a candidate ID. Ensure `cleanup_test_state` also removes `data/test/ingested_cvs_json`.
2. Write `tests/integration/test_ingest_gdrive_cli.py` that:
   - Uses `cleanup_test_state` and `ensure_postgres_available`.
   - Monkeypatches `CVParser.extract_text` to return deterministic backend-oriented text.
   - Creates `test.pptx` under `data/test/gdrive_inbox/CVs/backend_engineer/`.
   - Runs `init-db` then `ingest-gdrive --file test.pptx` via `run_cli`.
   - Asserts candidate row, tags, experience CSVs, embedding presence, and debug JSON existence.
3. Create `tests/fixtures/golden/ingest_gdrive_backend.yaml` with expected tags for the stubbed backend CV. Keep values aligned with `data/test/llm_stubs/structured_cv_backend.json`.
4. Add `tests/eval/test_ingest_gdrive_eval.py` (or `scripts/eval_ingest_gdrive.py`) that:
   - Reuses helpers to ingest `test.pptx` (allowing `USE_OPENAI_STUB` override via env).
   - Loads the emitted JSON and DB rows for the candidate_id derived from `test.pptx`.
   - Computes precision/recall/F1 for role/domain/tech tags vs the golden YAML.
   - Marks the test as `slow` or documents that the script is opt-in.
   - Writes optional JSONL metrics to `runs/evals/ingest_gdrive.jsonl` when invoked with a flag.
5. Update this plan’s `Progress`, `Decision Log`, `Surprises & Discoveries`, and `Outcomes & Retrospective` after each step and once tests are run.

## Validation and Acceptance

The change is accepted when:
1. The integration test passes locally with stubs and Postgres running:
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration\test_ingest_gdrive_cli.py -q
   Expected: test executes `init-db` and `ingest-gdrive --file test.pptx` via the CLI, asserting one processed candidate with correct tags and a non-null embedding; test passes without network access or model downloads.
2. Existing suites remain green:
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration -q
3. The eval harness runs on demand and reports metrics:
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\eval\test_ingest_gdrive_eval.py -q -m slow
   or (if implemented as a script):
    PS C:\Users\mykha\Projects\cv-search-poc> uv run python scripts\eval_ingest_gdrive.py --input test.pptx --golden tests/fixtures/golden/ingest_gdrive_backend.yaml --output runs/evals/ingest_gdrive.jsonl
   Acceptance: metrics output shows non-zero precision/recall for backend role/domain/tech tags and writes a JSON/JSONL artifact without errors.

## Idempotence and Recovery

Tests rely on deterministic stubs and a candidate_id derived from the filename, so reruns are safe. Before each run, call `cleanup_test_state()` to truncate Postgres tables and remove `data/test/gdrive_inbox`, `data/test/tmp/runs`, and `data/test/ingested_cvs_json`; the helper should recreate required directories. If a test fails mid-run, rerun `init-db` then re-execute the ingestion command. The eval harness should overwrite its output JSONL on repeated runs; instruct the user where outputs land so they can delete them if needed.

## Artifacts and Notes

Sample stub payload driving expectations (from `data/test/llm_stubs/structured_cv_backend.json`):
    role_tags: backend_engineer
    domain_tags: healthtech
    tech_tags: dotnet, kubernetes, postgresql, kafka, python
    seniority: senior
Expected debug JSON location after ingestion: `data/test/ingested_cvs_json/pptx-<hash>.json` where the hash is MD5 of `test.pptx` basename, truncated to 10 chars and prefixed with `pptx-`.

## Interfaces and Dependencies

Primary interfaces touched:
    src/cv_search/cli/commands/ingestion.py: CLI command `ingest-gdrive` that instantiates `CVIngestionPipeline`.
    src/cv_search/ingestion/pipeline.py: methods `_process_single_cv_file`, `run_gdrive_ingestion`, `upsert_cvs`, `_build_candidate_doc_texts`, `_ingest_single_cv`.
    src/cv_search/ingestion/cv_parser.py: method `extract_text`, to be monkeypatched in tests.
    src/cv_search/clients/openai_client.py: stub backend selected via `USE_OPENAI_STUB`; uses fixtures in `data/test/llm_stubs`.
    src/cv_search/retrieval/embedder_stub.py: `DeterministicEmbedder` engaged via `USE_DETERMINISTIC_EMBEDDER` or `HF_HUB_OFFLINE`.
    tests/integration/helpers.py: shared helpers for env setup, cleanup, and CLI invocation; extend as needed.
Dependencies to note: Postgres with pgvector and pg_trgm (via `docker-compose.pg.yml`), pytest, click.testing, python-pptx (only needed if we do not stub `CVParser.extract_text`), and sentence-transformers (avoided by deterministic embedder).

Plan change log:
    - 2025-12-03 - Initial creation of integration/eval harness ExecPlan for `ingest-gdrive --file test.pptx`.
    - 2025-12-03 - Documented implemented integration test, eval harness gating, and helper updates.
