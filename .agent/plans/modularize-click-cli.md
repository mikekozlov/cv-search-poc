# Modularize Click CLI into feature modules

This ExecPlan is a living document maintained in accordance with .agent/PLANS.md. All edits must keep it self-contained so a novice can complete the work without prior context.

## Purpose / Big Picture

Restructure the Click CLI currently packed into main.py into a clear, modular package. After this change a newcomer can find commands by domain (DB, ingestion, search, diagnostics) under src/cv_search/cli, and main.py remains a thin entry point. Behavior and flags stay the same, but the code reads cleanly and is easier to extend.

## Progress

- [x] (2025-12-02 16:10Z) Reviewed .agent/PLANS.md, main.py CLI commands, and repo layout; drafted this plan.
- [x] (2025-12-02 16:13Z) Created CLI package structure with shared context/helpers and per-domain command modules registered on the root group.
- [x] (2025-12-02 16:13Z) Reduced main.py to a thin shim and added cv_search.cli.__main__ for python -m cv_search.cli entry.
- [x] (2025-12-02 16:23Z) Ran integration suite after refactor; added deterministic embedder opt-in to keep tests offline-safe.

## Surprises & Discoveries

- Observation: Loading .env from within src/cv_search/cli needs parents[3] to reach the repo root; parents[2] resolves to the src directory and would miss the top-level .env.
  Evidence: Path(__file__).resolve().parents[3] for src/cv_search/cli/context.py resolves to C:\Users\mykha\Projects\cv-search-poc.
- Observation: Integration tests initially failed because SentenceTransformer tried to hit huggingface through blocked proxies (HTTP_PROXY=http://127.0.0.1:9), causing ProxyError. Added env-controlled deterministic embedder to keep CLI searches offline.
  Evidence: pytest failures in test_cli_ingest_and_search_backend/test_project_search_writes_artifacts showing ProxyError to huggingface; rerun passes with USE_DETERMINISTIC_EMBEDDER=1.

## Decision Log

- Decision: Split commands by domain into multiple modules under src/cv_search/cli/commands with a register(cli) pattern and a shared CLIContext for settings/client/db access. Rationale: keeps Click wiring thin and discoverable without changing UX. Date/Author: 2025-12-02 / assistant.
- Decision: Add src/cv_search/cli/__main__.py so python -m cv_search.cli works alongside python main.py, keeping .env loading centralized in the CLI context. Rationale: gives a packaged entrypoint without altering UX. Date/Author: 2025-12-02 / assistant.
- Decision: Allow CLI search commands to opt into a deterministic embedder via USE_DETERMINISTIC_EMBEDDER/HF_HUB_OFFLINE and set tests to use it, avoiding remote downloads in sandboxed runs. Rationale: integration tests ran with proxies blocking huggingface; stubbed embeddings keep tests deterministic and offline-friendly. Date/Author: 2025-12-02 / assistant.

## Outcomes & Retrospective

CLI code now lives under src/cv_search/cli with domain-based command modules, a shared context, and both python main.py and python -m cv_search.cli entrypoints. Integration tests pass in this environment when USE_DETERMINISTIC_EMBEDDER/HF_HUB_OFFLINE=1 is set to avoid huggingface downloads behind blocked proxies. Residual warnings remain from existing tests (pytest return-not-none, in-memory Redis fallback).

## Context and Orientation

The repository roots the CLI in main.py, which defines a single click.group() and many commands for env-info, init/check DB, mock and GDrive ingestion, brief parsing, search (seat/project), presale planning, and async ingestion workers. main.py currently injects src onto sys.path and initializes Settings, OpenAIClient, and CVDatabase in the group callback. The src/cv_search/cli package exists but is empty; there are no other CLI entry points. README references python main.py <command> for database and search workflows. Tests live under tests/integration and rely on Postgres (docker-compose.pg.yml) with env vars set as in AGENTS.md.

## Plan of Work

Create a real CLI package under src/cv_search/cli that owns the Click root group and per-domain command modules. Define a CLIContext object capturing Settings, OpenAIClient, and a CVDatabase instance so commands share setup consistently. Move each command from main.py into domain-specific modules (diagnostics/env, db/admin, search/planning, ingestion/sync/async) that expose register(cli) functions, importing shared helpers to avoid repeated DB closing or masking logic. Keep command names/options/behavior identical, including JSON outputs and error handling. Adjust main.py to be a minimal entry point that loads the packaged CLI (and still prepends src to sys.path for direct execution). Update any docs or __init__ wiring needed so python -m cv_search.cli and python main.py both work. Maintain helper functions like _print_gdrive_report in an appropriate module. Ensure imports use package-relative paths and avoid circular dependencies by deferring heavyweight imports inside commands when necessary.

## Concrete Steps

Work in PowerShell from the repo root (C:\Users\mykha\Projects\cv-search-poc). Create new files under src/cv_search/cli (context/shared plus commands subpackage), move command functions from main.py into those modules, and wire register() calls in src/cv_search/cli/__init__.py. Keep main.py as a thin shim importing cli.main(). Run formatting manually if needed (no formatter enforced). After code moves, validate a small CLI smoke run such as:
    PS C:\Users\mykha\Projects\cv-search-poc> python main.py env-info
Run required tests with test env vars set (per AGENTS.md):
    PS C:\Users\mykha\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR = "data/test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration -q

## Validation and Acceptance

Acceptance hinges on unchanged CLI behavior with improved structure. python main.py env-info still masks values as before; search-seat, project-search, and presale-plan return identical JSON structures; ingest-mock and ingest-gdrive commands work with existing settings; async ingestion commands still start the same workers. Integration tests pass after the refactor. The codebase should clearly separate command registration by domain under src/cv_search/cli/commands, and main.py should simply delegate to that package.

## Idempotence and Recovery

Edits are additive/relocating. Running the steps multiple times should be safe because command logic remains the same and databases are only touched via existing commands. If a command move introduces an import error, re-run python main.py <command> after fixing imports; no persistent state changes occur until ingestion/search commands run intentionally. Keep DB credentials and env vars unchanged between retries.

## Artifacts and Notes

Record key excerpts or error transcripts here if encountered during implementation. None yet.

## Interfaces and Dependencies

Define CLIContext in src/cv_search/cli/context.py capturing Settings, OpenAIClient, and CVDatabase (or a factory/closure) to share across commands. In src/cv_search/cli/__init__.py, expose cli (click.Group) and main() that invokes cli(). Each command module under src/cv_search/cli/commands (diagnostics.py, db_admin.py, search.py, ingestion.py, async_ingestion.py or similar) must export register(cli) to attach commands with the same names/options as currently in main.py. main.py should import main/cli from cv_search.cli and remain runnable via python main.py <command>, keeping sys.path adjustment so src is importable without installation.
