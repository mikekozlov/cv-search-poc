# Refine parse_request criteria prompting and normalization

This ExecPlan is a living document and must be maintained per `.agent/PLANS.md`.

## Purpose / Big Picture

Improve how free-text briefs become canonical search criteria so single-seat and project searches align with the ingestion pipeline and Postgres-backed lexical/semantic retrieval. After this change, a user can run `parse-request` on a brief and receive a normalized `Criteria` JSON whose roles, seniority ladder, domains, and must-have tech tags match the same lexicons and tagging rules used when CVs are ingested, leading to tighter gating and ranking in `search-seat`.

## Progress

- [x] (2025-12-09 14:36Z) Reviewed PLANS.md plus current parse_request, LLM prompting, ingestion pipeline, and search processor to map inputs to gating/ranking.
- [x] (2025-12-09 14:50Z) Draft improved prompt and candidate-selection strategy aligned with ingestion lexicons and DB gating fields.
- [x] (2025-12-09 15:20Z) Implement refactor (helper extraction, prompt rewrite, normalization) and update stubs/fixtures.
- [x] (2025-12-09 16:30Z) Add/adjust tests and CLI examples; run validation commands (unit tests passed; integration failed on missing fixtures and live-audio constraints).
- [ ] Summarize outcomes and lessons learned.

## Surprises & Discoveries

- Integration suite currently fails on missing fixture `data/test/expected_search.json` and live Whisper call rejecting dummy audio (400 invalid format). Evidence: `tests/integration/test_cli_integration.py` and `test_project_search_artifacts.py` FileNotFoundError; `test_cli_transcription.py` 400 invalid file format when hitting live endpoint with synthetic bytes.

## Decision Log

- Decision: Scope the refactor to keep public parse_request signature stable while tightening prompt, lexicon narrowing, and post-LLM normalization to match ingestion tagging.  
  Rationale: Maintains CLI compatibility but reduces drift between brief parsing and how CVs are tagged in Postgres/vector search.  
  Date/Author: 2025-12-09 / assistant.

## Outcomes & Retrospective

Pending final summary. Current state: prompt and parser normalization implemented; unit tests added and passing. Integration validation still blocked by missing expected_search.json fixture and live transcription endpoint rejecting dummy audio; needs resolution before declaring full acceptance.

## Context and Orientation

parse_request lives in `src/cv_search/core/parser.py` and calls `OpenAIClient.get_structured_criteria`, returning a `Criteria` (domain, tech_stack, expert_roles, project_type, team_size). The `search-seat` CLI (`src/cv_search/cli/commands/search.py`) expects `criteria["team_size"]["members"][0]` to contain canonical `role`, `seniority`, `domains`, `tech_tags` (must-have), and `nice_to_have` lists; these feed `GatingFilter` (`src/cv_search/retrieval/gating.py`) and downstream ranking. Ingestion (`src/cv_search/ingestion/pipeline.py` and `OpenAIClient.get_structured_cv`) canonicalizes roles/domains/tech using lexicon-driven candidate lists, hashes lexicon snapshots, and de-duplicates tags before writing Postgres rows and vector-store documents. The current structured_criteria prompt is minimal and does not mirror ingestion rules, which can cause non-canonical roles/techs or missing seniority to leak into search.

## Plan of Work

Establish a baseline by capturing current parse_request output for a few briefs (short, multi-role, domain-heavy) and note gaps versus gating needs (missing seniority, non-canonical role keys, noisy tech_stack). Redesign the criteria prompt to mirror ingestion guardrails: include lexicon fingerprint, pre-selected candidate slices for roles/domains/tech (reuse `_select_candidates` heuristics), and explicit rules for must-have vs nice-to-have tech, domains, and seniority ladder expectations. Extract prompt construction and lexicon candidate selection into a helper (e.g., `_build_criteria_prompt(...)`) so it can be unit-tested and reasoned about. Add post-processing that normalizes/lowers and de-duplicates tags, enforces canonical role/seniority presence for at least one seat, and defaults team_size.members from expert_roles/tech_stack when the LLM omits counts. Update stub backend fixture (`data/test/llm/structured_criteria.json` if used) and any tests relying on legacy fields. Add targeted tests around parse_request to assert canonicalization (role must be in lexicon, seniority normalized per gating ladder, domain/tech de-dup) and that prompt-building embeds the candidate lists and lexicon hash. Ensure planner/multi-seat flows still accept the Criteria object and that CLI `parse-request` produces JSON compatible with `search-seat`.

## Concrete Steps

Work from repo root `C:\Users\mykha\Projects\cv-search-poc`.

1) Baseline capture: run parse_request on 2–3 briefs and save outputs for comparison.  
    PS C:\Users\mykha\Projects\cv-search-poc> uv run python -m cv_search.cli parse-request --text "need 1 .net middle azure developer"

2) Implement refactor: add helper(s) in `src\cv_search\core\parser.py` or a nearby module to build lexicon-filtered prompts and normalize Criteria data; update `OpenAIClient.get_structured_criteria` prompt text to use candidates/hash and ingestion-like guardrails; adjust stub fixture if present.

3) Add tests: extend unit/integration coverage (e.g., a new test under `tests\unit\core\test_parser.py` or similar) that mocks `OpenAIClient` to return varied shapes (missing team_size, mixed-case tags) and asserts normalized Criteria; add a prompt-construction test to check for candidate lists and hash inclusion without hitting the network. Update existing fixtures if shapes change.

4) Run required tests per AGENTS.md:  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR="data/test/tmp/runs"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR="data/test"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR="data/test/gdrive_inbox"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY="test-key"  
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration -q

5) Spot-check CLI compatibility: run `parse-request` then `search-seat` using the produced criteria JSON to ensure search executes without schema errors.  
    PS C:\Users\mykha\Projects\cv-search-poc> uv run python -m cv_search.cli parse-request --text "need 1 .net middle azure developer" > tmp_criteria.json  
    PS C:\Users\mykha\Projects\cv-search-poc> uv run python -m cv_search.cli search-seat --criteria tmp_criteria.json --topk 2 --mode hybrid --no-justify

## Validation and Acceptance

Acceptance: `parse-request` on sample briefs produces Criteria JSON whose `team_size.members[0]` has canonical role (from role lexicon), normalized seniority compatible with gating (`junior|middle|senior|lead|manager`), deduped domains/tech aligned with lexicons, and populated tech_stack rollup. `search-seat` runs with that output without errors and returns results (or an empty-but-valid payload) while logging gating SQL. All integration tests pass via the command above; new unit tests around parse_request/prompt helpers pass.

## Idempotence and Recovery

Prompt-building and normalization functions should be pure and repeatable; rerunning parse_request on the same brief yields consistent normalized output (aside from any stochastic LLM variance, which stubs/tests should control). If tests fail due to fixture drift, refresh stub criteria fixtures to the new schema and rerun. No destructive steps are involved; temporary files (e.g., tmp_criteria.json) can be safely deleted.

## Artifacts and Notes

Capture before/after parse_request outputs for a fixed brief and include short snippets in this section after implementation to demonstrate improved canonicalization (e.g., role lowered to `dotnet_developer`, seniority normalized to `middle`, domains/tech deduped).

## Interfaces and Dependencies

Primary function: `src\cv_search\core\parser.py::parse_request(text: str, model: str, settings: Settings, client: OpenAIClient) -> Criteria` must continue returning a `Criteria` dataclass with `team_size.members` populated and canonical tags. Supporting helpers to add: prompt builder and candidate-selection logic (may leverage `_select_candidates` and `_lexicon_fingerprint` already in `OpenAIClient`). Dependencies: role/tech/domain/expertise lexicons under `settings.lexicon_dir`; Settings drives `openai_model` and stub/live backend. Keep backward compatibility for CLI users while enhancing prompt fidelity and post-processing normalization.
