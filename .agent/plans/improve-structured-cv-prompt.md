# Harden structured CV prompt and method in OpenAI client

This ExecPlan is a living document and must be maintained in accordance with .agent/PLANS.md. Update it as progress is made so a newcomer can implement and validate the work using only this file and the repository.

## Purpose / Big Picture

Improve the `get_structured_cv` prompt and method in `src/cv_search/clients/openai_client.py` so LLM-driven CV parsing is deterministic, maps consistently to lexicons, and behaves safely in production-grade environments. Keep the prompt concise by avoiding full lexicon dumps (especially tech), instead grounding the model with a pre-filtered candidate set. After implementation, running CV ingestion should yield structured JSON with predictable keys, strict handling of the role folder hint, and clearer error-surfacing when the model deviates.

## Progress

- [x] (2025-12-03 18:25Z) Drafted initial ExecPlan; no code changes yet.
- [x] (2025-12-03 18:50Z) Reviewed current lexicon structures and prompt; refined approach to use candidate filtering and hashes, avoiding full lexicon dumps.
- [x] (2025-12-03 19:05Z) Implemented candidate filtering, lexicon fingerprinting, and concise prompt revisions in `openai_client.py`; added unit tests for helpers.
- [ ] (2025-12-03 19:20Z) Validation in progress: unit helper tests pass; integration suite pending due to Docker access denial on this host.
- [ ] Finalize retrospective and ensure docs/plan are updated.

## Surprises & Discoveries

- Decision: Avoid dumping full lexicons (especially tech) into the prompt; instead pre-filter lexicon candidates based on the CV text and role hint, and capture unmapped techs to a review stash rather than mutating the lexicon on the fly.
  Rationale: Reduces prompt noise and token cost while keeping mapping deterministic and auditable without silent lexicon drift.
  Date/Author: 2025-12-03 / assistant
- Decision: Do not rely on “prompt caching” by placing full lexicons at the top; caching behavior is opaque and unstable across providers. Instead, include a lightweight lexicon fingerprint (e.g., version hash + small candidate slices) early in the prompt if caching is desired, keeping the candidate lists small.
  Rationale: Maintains low token usage and predictable outputs without betting on undocumented cache heuristics; still allows reuse if provider caching becomes effective.
  Date/Author: 2025-12-03 / assistant

## Decision Log

- Observation: Docker daemon not accessible on this host; `docker-compose -f docker-compose.pg.yml up -d` fails with "Access is denied" against DockerDesktopLinuxEngine.
  Evidence: `unable to get image 'pgvector/pgvector:pg16': ... open //./pipe/dockerDesktopLinuxEngine: Access is denied.`
- Observation: `uv run pytest` failed to read cache directory due to permission issues; `.venv` python invocation works.
  Evidence: `error: failed to open file C:\Users\mykha\AppData\Local\uv\cache\sdists-v9\.git: Access is denied.`

## Outcomes & Retrospective

Pending implementation.

## Context and Orientation

LLM interactions live in `src/cv_search/clients/openai_client.py`. `LiveOpenAIBackend.get_structured_cv` builds a system prompt using lexicons loaded from `cv_search.lexicon.loader` and delegates to `_get_structured_response`, which calls OpenAI/Azure chat completions with `LLMCV` as the Pydantic schema. `OpenAIClient.get_structured_cv` simply forwards to the backend, and `StubOpenAIBackend.get_structured_cv` loads fixtures for deterministic runs. CV ingestion pipelines in `src/cv_search/ingestion/async_pipeline.py` and `src/cv_search/ingestion/pipeline.py` call the client, so prompt or logic changes affect downstream parsing. The goal is to improve only the `get_structured_cv` method (and its immediate prompt-building logic), keeping interfaces stable for callers while reducing prompt size via pre-filtered lexicon slices.

## Plan of Work

Study current lexicon loaders and the `LLMCV` schema to clarify required fields and allowed values. Design a stronger system prompt that separates responsibilities: explicit validation of the folder hint, strict mapping rules for each tag set, and explicit handling for unmapped tokens. Outline deterministic behaviors such as returning null for invalid hints, refusing to invent keys not in lexicons, and preserving evidence notes when mapping is ambiguous. Replace full lexicon dumps with pre-filtered candidates derived from the CV text and the role hint (e.g., n-gram/fuzzy match to limit to the nearest canonical keys), while retaining a concise instruction that only canonical keys are allowed. Capture unmapped techs into an audit list (or optional review file) instead of mutating the lexicon at runtime to prevent silent drift. Keep logging/metadata intact and consider adding a max_tokens cap or temperature control for safety. Document any expectations about the lexicon format inside the prompt so the model understands capitalization, plurals, and synonyms.

## Concrete Steps

From `PS C:\Users\mykha\Projects\cv-search-poc>`:

1) Inspect `src\cv_search\clients\openai_client.py` and `cv_search\lexicon\loader.py` to capture lexicon structure and current prompt content.
2) Implement a pre-filter step in `LiveOpenAIBackend.get_structured_cv` that derives small candidate lists for roles/domains/tech/expertise from the CV text and role hint (e.g., lowercase token match, simple n-gram containment, or light fuzzy scoring) and use only these candidates in the prompt; include instructions that only canonical keys are valid.
3) Redraft the system prompt to emphasize: validate folder hint to canonical role or null; map only to provided candidate canonical keys; keep unmapped techs separate; do not invent keys; prefer best-match canonical keys when multiple candidates are close.
4) Keep behavior aligned with `StubOpenAIBackend`; if candidate filtering changes expectations, adjust or add fixtures/tests under `tests` to cover candidate list generation and prompt changes without mutating lexicon files.
5) Optionally capture unmapped techs to a review list or log for later lexicon curation (no auto-write); document this in code comments and tests.
6) Run the integration suite with the required env vars set:

    PS C:\Users\mykha\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR = "data/test"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration -q

## Validation and Acceptance

Implementation is accepted when the revised `get_structured_cv` prompt produces deterministic, lexicon-aligned JSON and the ingestion paths continue to function. Running the integration suite must pass without regressions. For manual validation, call `OpenAIClient.get_structured_cv` with a sample CV text and a role folder hint; confirm `source_folder_role_hint` resolves only when the hint matches a canonical role and that all tags map to provided lexicons with unmapped terms isolated.

## Idempotence and Recovery

Edits are limited to prompt and method logic within `src/cv_search/clients/openai_client.py` and related tests/fixtures. Changes can be reapplied safely; if a prompt revision behaves poorly, revert only the affected prompt/method block while keeping interfaces intact. Stub backend fixtures must remain coherent with any schema expectation changes.

## Artifacts and Notes

Capture any updated prompt text and example structured outputs observed during testing in this section as work proceeds, keeping snippets concise and indented for readability.

## Interfaces and Dependencies

The method signature for `LiveOpenAIBackend.get_structured_cv` must remain `def get_structured_cv(self, raw_text: str, role_folder_hint: str, model: str, settings: Settings) -> Dict[str, Any]`, and it must continue to call `_get_structured_response` with `LLMCV` as the schema. Do not change external callers. Any new helper used for prompt assembly should live in the same module and avoid altering `OpenAIClient` or stub interfaces. Maintain dependence on `cv_search.lexicon.loader` for lexicon data, but do not mutate lexicon files at runtime; collect unmapped terms for review instead.

Note (2025-12-03): Updated plan to avoid full lexicon dumps, add candidate filtering for prompt grounding, and clarify stance against auto-mutation of lexicon files while capturing unmapped techs for review.
