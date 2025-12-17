# Translate non-English briefs before criteria extraction

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Project search currently performs poorly on Ukrainian (and other non‑English) briefs because canonical role, domain, and expertise lexicons are English and the prompt/candidate ordering relies on English tokens. After this change, a user can paste a Ukrainian brief like “Потрібен сильний Senior .NET …” and the system will first translate the brief to English, then extract canonical criteria from the English version, and use that English text for downstream semantic search. Search results should better reflect the intended role, seniority, tech stack, and domain.

## Progress

- [x] (2025-12-12 12:20Z) Reviewed current parsing and search flow to locate prompts and raw_text usage.
- [x] (2025-12-12 12:35Z) Added translation-first instructions to criteria/brief LLM prompts and requested `english_brief` field.
- [x] (2025-12-12 12:40Z) Threaded English translation into project and presale search raw_text paths.
- [x] (2025-12-12 12:55Z) Added unit test and ran Ruff + unit tests.

## Surprises & Discoveries

- Observation: Lexicon prioritization and low-signal detection tokenize only `[a-z0-9_+#\\.]`, so Cyrillic words are ignored.
  Evidence: `src/cv_search/clients/openai_client.py` helper `_tokenize`, `src/cv_search/search/processor.py` `_is_generic_low_signal`.

## Decision Log

- Decision: Implement translation inside the criteria LLM prompt (single call) and request an extra `english_brief` field in the JSON output.
  Rationale: Lexicons are small, so candidate ordering is not critical; avoiding a second LLM call keeps latency/cost down while still giving us the English text for downstream use.
  Date/Author: 2025-12-12 / agent

- Decision: Store the translated text on the returned `Criteria` instance as a dynamic attribute instead of adding a new dataclass field.
  Rationale: Keeps canonical `criteria.json` schema unchanged while still letting search callers access the translation.
  Date/Author: 2025-12-12 / agent

## Outcomes & Retrospective

Non‑English briefs are now translated to English inside the criteria/brief LLM prompt, and the translated text is surfaced as `english_brief` and threaded through project/presale search raw_text. Unit tests and Ruff pass. This should improve lexicon matching and semantic retrieval for Ukrainian briefs without changing the canonical criteria schema.

## Context and Orientation

Criteria extraction happens through `parse_request` in `src/cv_search/core/parser.py`, which calls `OpenAIClient.get_structured_criteria` or `get_structured_brief` and then normalizes the payload into a `Criteria` dataclass. The OpenAI client builds a `system_prompt` that includes ordered role/domain/expertise lexicons from `data/lexicons/*.json` and sends it to the chat model. Project search callers pass the original brief as `raw_text` into `SearchProcessor.search_for_project`, which uses it for low‑signal checks and deterministic seat inference. Relevant files:

- `src/cv_search/clients/openai_client.py` — builds `system_prompt`/`prompt` for criteria and brief extraction.
- `src/cv_search/core/parser.py` — orchestrates criteria extraction and normalization.
- `src/cv_search/cli/commands/search.py` and `pages/1_Project_Search.py` — call `parse_request` and pass `raw_text` to project search.
- `src/cv_search/search/processor.py` and `src/cv_search/planner/service.py` — consume `raw_text`.

## Plan of Work

1. Update `OpenAIClient.get_structured_criteria` and `get_structured_brief` system prompts to explicitly:
   - Translate the client brief to English first if it is not already English.
   - Use the English translation for all lexicon matching and reasoning.
   - Include an extra top-level field `english_brief` with the translated text.
   The JSON schema for criteria/presale remains the same; extra fields are allowed by pydantic.

2. In `parse_request`, after receiving the criteria payload, read `english_brief` if present and attach it to the returned `Criteria` object (for example `crit._english_brief = english_text`).

3. In project search entrypoints (`project_search_cmd` in `src/cv_search/cli/commands/search.py` and the Streamlit flow in `pages/1_Project_Search.py`), prefer the attached English text for `raw_text` when calling `SearchProcessor.search_for_project` and `Planner.derive_presale_team`. Keep original text as fallback.

4. Add/adjust unit tests to cover that `parse_request` propagates `english_brief` onto the Criteria object and that callers use it when present.

## Concrete Steps

From repo root `PS C:\Users\mykha\Projects\cv-search-poc>`:

1. Edit prompts and parsing/search code per Plan of Work.

2. Run Ruff on changed Python files:

   PS C:\Users\mykha\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = "1"
   PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff format src tests pages
   PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff check src tests pages

3. Run unit tests (excluding integration/eval folders):

   PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests -q --ignore tests\integration --ignore tests\eval

## Validation and Acceptance

Behavioral acceptance:

- Running parse-request with a Ukrainian brief produces criteria that include canonical English lexicon keys for role, tech stack, and domain and internally stores an English translation.
- Running project-search with the same Ukrainian brief produces better seat derivation and semantic queries because English text is used for downstream search and heuristics.

Test acceptance:

- `uv run pytest tests -q --ignore tests\integration --ignore tests\eval` passes with the new unit test(s) failing before the change and passing after.

## Idempotence and Recovery

All edits are additive and safe to re-run. If translation behavior causes regressions, revert to prior prompts and remove the `_english_brief` threading; unit tests will signal the rollback is clean.

## Artifacts and Notes

(Add any notable prompt diffs or test outputs here after implementation.)

## Interfaces and Dependencies

No new external dependencies. Uses existing OpenAI chat model and pydantic schemas which already allow extra JSON fields.

Plan revision note (2025-12-12): Marked final validation complete and recorded outcomes after Ruff and unit tests passed.
