# Criteria-only parsing and generic brief guard

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Follow `.agent/PLANS.md` from the repository root when maintaining this plan.

## Purpose / Big Picture

Normal searches (`project-search`, Streamlit search pages, and `parse-request`) currently call `OpenAIBackend.get_structured_brief`, which asks the model to produce both search criteria and a presale staffing plan. That means even when the user only wants a candidate search, we pay for and surface presale output. Additionally, very broad briefs like “need a developer” can lead the model to guess a generic role (for example `fullstack_engineer`) and trigger a search with little real signal.

After this change:

1. Criteria extraction for normal search uses a criteria‑only prompt (no presale plan) unless the user explicitly runs a presale command.
2. Free‑text project search treats generic/low‑signal briefs as insufficient information even if the LLM guessed a generic role. The system returns a friendly payload with `reason: "low_signal_brief"` and does not run retrieval or create artifacts.

You can see it working by running:

    uv run python main.py project-search --text "need a developer" --topk 3 --no-justify

and observing an early low‑signal response with no `runs/` output, while:

    uv run python main.py project-search --text "need backend developer with python" --topk 3 --no-justify

still produces normal seats/results.

## Progress

- [x] (2025-12-12 11:10Z) Reviewed existing LLM prompts and low‑signal guard behavior.
- [ ] Add criteria‑only prompt in `LiveOpenAIBackend.get_structured_criteria`.
- [ ] Add `include_presale` switch to `parse_request` and update call sites.
- [ ] Add deterministic generic‑brief detection before search.
- [ ] Update tests accordingly.
- [ ] Run Ruff and integration tests.

## Surprises & Discoveries

- Observation: `parse_request` always uses `get_structured_brief` because `OpenAIClient` exposes that method, so presale prompts run even for search.
  Evidence: `src/cv_search/core/parser.py::parse_request`.

- Observation: Low‑signal guard only fires when no seats are derived; it does not catch “generic role, no constraints” cases.
  Evidence: `src/cv_search/search/processor.py::search_for_project`.

## Decision Log

- Decision: Introduce a criteria‑only system prompt based on the same lexicon guardrails but without presale fields, and use `LLMCriteria` schema for this call.
  Rationale: Keeps costs and outputs aligned with user intent while reusing existing schema/normalization.
  Date/Author: 2025-12-12 / Codex.

- Decision: Detect generic briefs deterministically using both raw text and normalized criteria (empty domain/tech/seniority and role implied only by generic terms like “developer/engineer”).
  Rationale: Prevents arbitrary searches even if the model guesses a role.
  Date/Author: 2025-12-12 / Codex.

## Outcomes & Retrospective

Pending implementation.

## Context and Orientation

Relevant code paths:

- LLM backend and prompts live in `src/cv_search/clients/openai_client.py`. `LiveOpenAIBackend.get_structured_brief` currently returns a combined `LLMStructuredBrief` (criteria + presale_team). `get_structured_criteria` is just a thin wrapper around that combined prompt.
- `parse_request` in `src/cv_search/core/parser.py` calls the backend to get structured criteria, normalizes tags against lexicons, and returns a `Criteria` dataclass.
- Free‑text project search (`project-search` CLI and Streamlit) uses `parse_request` then `SearchProcessor.search_for_project` (`src/cv_search/search/processor.py`).
- Presale commands (`presale-plan`, `presale-search`) also call `parse_request` and later `Planner.derive_presale_team`.

We need to add a criteria‑only prompt, control which prompt is used, and add stricter low‑signal gating for generic briefs.

## Plan of Work

1. In `src/cv_search/clients/openai_client.py`:
   - Import `LLMCriteria` from `cv_search.llm.schemas`.
   - Implement `LiveOpenAIBackend.get_structured_criteria` with its own system prompt:
     - Same role/domain/expertise candidate lists and canonical‑only rules as today.
     - No presale_team instructions.
     - Add a rule: if the brief only says generic hiring intent (developer/engineer) without explicit role qualifiers or tech/domain, return empty `expert_roles` and `team_size` rather than guessing.
   - Keep `get_structured_brief` for presale workflows.

2. In `src/cv_search/core/parser.py`:
   - Add parameter `include_presale: bool = False` to `parse_request`.
   - When `include_presale` is `True`, call `client.get_structured_brief` and parse presale_team as before.
   - When `False`, call `client.get_structured_criteria` (criteria‑only prompt); skip presale parsing.

3. Update call sites:
   - `project-search` CLI (`src/cv_search/cli/commands/search.py`) and Streamlit project search (`pages/1_Project_Search.py`) should use default `include_presale=False`.
   - Presale commands (`presale-plan`, `presale-search`) should pass `include_presale=True`.

4. Strengthen low‑signal detection in `SearchProcessor.search_for_project`:
   - If `raw_text` is present, check for generic briefs by:
     - tokenizing `raw_text` and looking for generic terms (“developer”, “engineer”, “dev”) AND
     - ensuring there are no non‑generic role hints or tech/domain signals, and derived criteria has empty `domain`, `tech_stack`, and no explicit seniority.
   - If generic/low‑signal, return the same early payload as the existing low‑signal path (reason `"low_signal_brief"`, no run_dir, no search).

5. Update tests:
   - Adjust unit tests for `parse_request` to pass `include_presale=True` where presale fields are expected.
   - Add a new test ensuring generic briefs with a stubbed generic role still return `low_signal_brief`.

## Concrete Steps

From repo root `PS C:\Users\mykha\Projects\cv-search-poc>`:

1. Edit `src/cv_search/clients/openai_client.py` to add the criteria‑only prompt.
2. Edit `src/cv_search/core/parser.py` to add `include_presale` and branch behavior.
3. Update call sites in `src/cv_search/cli/commands/search.py`, `src/cv_search/cli/commands/presale_search.py`, and `pages/1_Project_Search.py`.
4. Update/add tests under `tests/`.
5. Run Ruff and tests:

    $env:AGENTIC_TEST_MODE = "1"
    uv run --extra dev ruff format src tests
    uv run --extra dev ruff check src tests

    $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
    $env:RUNS_DIR = "data/test/tmp/runs"
    $env:DATA_DIR = "data/test"
    $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"
    $env:OPENAI_API_KEY = "test-key"
    uv run pytest tests\integration -q

## Validation and Acceptance

- Generic brief returns low‑signal:

    uv run python main.py project-search --text "need a developer" --topk 3 --no-justify

  Expect `reason: "low_signal_brief"` and `seats: []`, and no new `runs/seat_*` folders.

- Specific brief still searches:

    uv run python main.py project-search --text "need backend developer with python" --topk 3 --no-justify

  Expect at least one seat searched and artifacts created.

- Presale commands still include presale teams and do not regress existing presale tests.
- Ruff clean and `pytest tests\integration -q` passes.

## Idempotence and Recovery

All changes are additive and safe to re‑run. If the generic‑brief heuristic is too strict/loose, adjust only that check and re‑run Ruff + tests.

## Artifacts and Notes

Keep the low‑signal `note` short and user‑friendly to make it easy to surface in UI/CLI.

## Interfaces and Dependencies

New interface:

- `parse_request(text, model, settings, client, include_presale: bool = False) -> Criteria`

No new external libraries are required.

