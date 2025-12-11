# LLM presale plan outputs criteria with team arrays

This ExecPlan is a living document and must be maintained per `.agent/PLANS.md`.

## Purpose / Big Picture

Enable the presale planning flow to call the LLM for team composition and return a Criteria JSON that embeds the recommended minimum and extended presale teams. After this change, running the presale-plan CLI on a brief will yield normalized criteria (domain, tech stack, etc.) plus `minimum_team` and `extended_team` arrays derived from the LLM, without performing any candidate search.

## Progress

- [x] (2025-12-11 15:20Z) Reviewed PLANS.md, AGENTS.md, and current presale-plan/Planner implementation to understand deterministic role composition and CLI usage.
- [x] (2025-12-11 15:55Z) Added presale Pydantic schema, OpenAI client method with lexicon-guarded prompt, and stub fixture for deterministic runs.
- [x] (2025-12-11 16:10Z) Extended Criteria/planner to attach minimum/extended teams from the LLM (with fallback) and wired presale-plan CLI commands to emit Criteria JSON; added stub-backed unit test.
- [x] (2025-12-11 16:25Z) Ran Ruff format/check and integration suite (5 passed; noted existing PytestReturnNotNoneWarning in test_settings).

## Surprises & Discoveries

- Pytest flagged `tests/integration/test_async_ingestion.py::test_settings` for returning a Settings object instead of None. Evidence: PytestReturnNotNoneWarning during integration run; tests still passed.

## Decision Log

- Decision: Filter LLM-returned presale roles against the canonical role lexicon and fall back to a deterministic heuristic when empty.  
  Rationale: Keeps presale team arrays aligned with search lexicons while ensuring output even if the LLM/stub omits roles.  
  Date/Author: 2025-12-11 / assistant.

## Outcomes & Retrospective

Presale-plan flow now calls the LLM with role-lexicon guardrails to populate `minimum_team` and `extended_team` on Criteria and emits that JSON via CLI. Stub fixture plus unit test cover the new path; Ruff and integration suites passed (with the known return-not-none warning). Further work: future steps can hook these team arrays into search orchestration when needed.

## Context and Orientation

Presale planning today lives in `src\cv_search\planner\service.py::derive_presale_team`, which deterministically builds minimum/extended role lists from tech tokens and raw text without calling the LLM. The `presale-plan` CLI commands in `src\cv_search\cli\commands\presale_search.py` and `src\cv_search\cli\commands\search.py` parse a brief via `parse_request` (LLM-driven structured criteria) and then invoke `Planner.derive_presale_team`, echoing a custom plan dict. Criteria objects are defined in `src\cv_search\core\criteria.py` and currently have no presale-specific team fields. The OpenAI client (`src\cv_search\clients\openai_client.py`) already provides structured criteria/CV/justification calls with stub support and lexicon-driven prompts; no presale-specific schema exists yet. The role lexicon at `data\lexicons\role_lexicon.json` contains canonical keys (e.g., `ai_solution_architect`, `data_privacy_expert`, `integration_specialist`) that match the requested presale team examples.

## Plan of Work

Design a presale team schema and LLM prompt that restricts outputs to canonical role keys from the role lexicon and separates `minimum_team` vs `extended_team`. Implement a new OpenAI client method (live + stub) to return that schema; add a deterministic fixture under `data\test\llm_stubs` for offline runs. Extend the `Criteria` dataclass to include `minimum_team` and `extended_team` lists and ensure `to_json` carries them. Replace the deterministic `derive_presale_team` path with a presale planning method that calls the new LLM endpoint, normalizes role outputs (lowercase/canonical, dedup), and writes them onto the Criteria derived from `parse_request`. Update both presale-plan CLI commands to return the enriched Criteria JSON (no search). Add unit coverage for the planner method using the stub backend, and validate CLI/schema expectations if feasible. Finish by running Ruff and the integration suite per AGENTS.md.

## Concrete Steps

Work from repo root `C:\Users\mykha\Projects\cv-search-poc`.

1) Define presale schema/prompt: add a Pydantic model for presale team output and a client method in `src\cv_search\clients\openai_client.py` that calls chat completions with role lexicon candidates and strict canonical-key rules; add a stub fixture (e.g., `presale_plan.json`) and stub method.
2) Update domain model and planner: extend `src\cv_search\core\criteria.py` with `minimum_team` and `extended_team` fields; implement a planner method that invokes the new client call and attaches normalized team lists to the Criteria returned by `parse_request`.
3) Wire CLI: adjust `presale-plan` commands to use the new planner method and emit the Criteria JSON only.
4) Tests: add a unit test (e.g., under `tests\test_presale_plan.py`) that uses the stub client to assert the planner sets both team arrays on Criteria; update/refresh any fixtures as needed.
5) Required validation per AGENTS.md:
    PS C:\Users\mykha\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE="1"
    PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff format src tests
    PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff check src tests
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR="data/test/tmp/runs"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR="data/test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR="data/test/gdrive_inbox"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY="test-key"
    PS C:\Users\mykha\Projects\cv-search-poc> python scripts\run_agentic_suite.py

## Validation and Acceptance

Acceptance: presale-plan CLI returns a JSON Criteria that includes normalized domain/tech fields plus non-empty `minimum_team` and `extended_team` arrays populated from the LLM (stubbed in tests). The planner method consumes the stub fixture deterministically in tests. Ruff formatting/checks pass, and the integration suite via `python scripts\run_agentic_suite.py` completes successfully.

## Idempotence and Recovery

The presale planner method should be pure aside from the LLM call; rerunning with the stub backend yields the same team arrays. If live LLM variance is an issue, the stub backend and fixture provide deterministic results for tests. No destructive steps; CLI commands are read-only.

## Artifacts and Notes

Capture an example presale-plan CLI output (with stub) showing the new team arrays after implementation for future reference.

## Interfaces and Dependencies

New API surface: OpenAI client method for presale team composition, returning `{minimum_team: [canonical_role], extended_team: [canonical_role], ...}` using the role lexicon. Planner method should accept a Criteria + raw brief + client/settings and return a Criteria with team arrays set. CLI `presale-plan` should output `Criteria.to_json()` containing `minimum_team` and `extended_team`. Dependencies: role lexicon under `settings.lexicon_dir`, Settings/openai model selection, and the stub backend/fixtures for offline tests.
