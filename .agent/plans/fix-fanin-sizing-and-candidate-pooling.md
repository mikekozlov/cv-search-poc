# Fix fan-in sizing and candidate pooling (performance + recall)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository includes `.agent/PLANS.md`, which defines the required structure and maintenance rules for ExecPlans. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Single-seat search currently has two related issues that hurt both performance and recall.

First, the lexical retrieval step can become accidentally unbounded because its SQL `LIMIT` is derived from the size of the gated candidate set. As the dataset grows, this makes lexical retrieval scale with the number of gated candidates rather than with the number of results the user asked for.

Second, the hybrid fusion pool ignores the vector-store fan-in setting (`--vs-topk`) because it only pools the first `top_k` semantic hits. That means increasing semantic fan-in does not change hybrid results (only semantic-only results).

After this change, the search pipeline uses explicit, bounded fan-in controls:

- `sem_fanin`: how many semantic (pgvector) candidates to consider (controlled by existing `--vs-topk` / `Settings.search_vs_topk`).
- `lex_fanin`: how many lexical candidates to consider (computed deterministically from `top_k`, `sem_fanin`, and two new settings: `Settings.search_fanin_multiplier` and `Settings.search_lex_fanin_max`).

You can see it working by running unit tests: hybrid ranking behavior changes when `--vs-topk` (semantic fan-in) changes, and fan-in metrics are persisted to run artifacts.

## Progress

- [x] (2025-12-14 19:31Z) Reviewed current seat search fan-in sizing and found unbounded `lex_limit` and hybrid pooling that ignores semantic fan-in.
- [x] (2025-12-14 19:35Z) Implemented bounded `lex_fanin` sizing and added `Settings.search_fanin_multiplier` / `Settings.search_lex_fanin_max` defaults.
- [x] (2025-12-14 19:35Z) Updated hybrid pooling to use `sem_fanin` (vs fan-in) and surfaced `pool_size` in metrics.
- [x] (2025-12-14 19:36Z) Added/updated unit tests covering `sem_fanin`-sensitive hybrid pooling and bounded lexical fan-in sizing.
- [x] (2025-12-14 19:36Z) Ran Ruff (format + lint) and unit tests (excluding `tests/integration` and `tests/eval`).

## Surprises & Discoveries

- Observation: Lexical SQL `LIMIT` can become O(gate size) because `lex_limit = max(top_k, vs_topk, len(gated_ids))`.
  Evidence: `SearchProcessor._run_single_seat` sets `lex_limit` based on `len(gated_ids)`.

- Observation: Hybrid fusion ignores `--vs-topk` because it only pools `semantic_hits[:top_k]` rather than the full semantic fan-in.
  Evidence: `HybridRanker.rank` builds `pool_ids` using `semantic_hits[:top_k]`.

## Decision Log

- Decision: Treat the existing `--vs-topk` / `Settings.search_vs_topk` as the semantic fan-in (`sem_fanin`) and thread it into hybrid pooling.
  Rationale: Preserves the CLI surface area while making hybrid results sensitive to semantic fan-in as intended.
  Date/Author: 2025-12-14 / Codex

- Decision: Compute lexical fan-in (`lex_fanin`) as `min(search_lex_fanin_max, max(top_k, sem_fanin) * search_fanin_multiplier)`, additionally bounded by the gated candidate count.
  Rationale: Keeps lexical retrieval bounded and proportional to ranking needs, rather than proportional to dataset size.
  Date/Author: 2025-12-14 / Codex

## Outcomes & Retrospective

Single-seat search fan-in is now explicit and bounded:

- Semantic fan-in (`sem_fanin`) is the same value as `--vs-topk` / `Settings.search_vs_topk`, and hybrid pooling now considers semantic hits up to this size.
- Lexical fan-in (`lex_fanin`) is no longer derived from `len(gated_ids)`. It is computed deterministically from `top_k`, `sem_fanin`, and the new Settings knobs:

  - `search_fanin_multiplier` (default `10`)
  - `search_lex_fanin_max` (default `250`)

- Run payload metrics include `gate_count`, `lex_fanin`, `sem_fanin`, and `pool_size`, and these are persisted to `metrics.json` when `run_dir` artifacts are written.

Validation: `uv run --extra dev ruff check src tests` is clean and `uv run pytest -q tests --ignore=tests\\integration --ignore=tests\\eval` passes (20 tests).

## Context and Orientation

The single-seat search pipeline is orchestrated by `src/cv_search/search/processor.py` in `SearchProcessor._run_single_seat(...)`. The high-level flow is:

1) Gating: `GatingFilter.filter_candidates(...)` returns the candidate IDs eligible for the seat (role + seniority gating).

2) Lexical retrieval: `LexicalRetriever.search(...)` runs structured tag ranking (and optional Postgres full-text search) over the gated candidate IDs and returns the top lexical matches.

3) Semantic retrieval: `PgVectorSemanticRetriever.search(...)` embeds a query string and runs pgvector similarity search over the gated candidate IDs.

4) Late fusion: `HybridRanker.rank(...)` produces the final ordered results for modes `lexical`, `semantic`, or `hybrid`.

The terms used in this plan mean:

- “Fan-in”: the number of candidates retrieved from a channel before final ranking. Larger fan-in can improve recall, but increases query cost.
- “Pool” (hybrid): the set of unique candidate IDs that the fusion stage considers when combining lexical and semantic signals.

Key files:

- `src/cv_search/search/processor.py`: computes fan-in, runs gating, calls retrievers, writes run artifacts.
- `src/cv_search/ranking/hybrid.py`: builds the hybrid pool and performs late fusion.
- `src/cv_search/config/settings.py`: defines search-related knobs (to be extended with fan-in sizing controls).
- `src/cv_search/search/artifacts.py`: persists `metrics.json` and other artifacts when a `run_dir` is provided.

## Plan of Work

First, introduce two new Settings fields in `src/cv_search/config/settings.py`:

- `search_fanin_multiplier` (default `10`): scales how many lexical rows to consider relative to `max(top_k, sem_fanin)`.
- `search_lex_fanin_max` (default `250`): hard cap for lexical fan-in to prevent unbounded query sizes.

Second, update `SearchProcessor._run_single_seat` in `src/cv_search/search/processor.py`:

- Interpret `vs_topk` as `sem_fanin`.
- Compute `lex_fanin` using the formula above, clamped to the gated candidate count.
- Call `LexicalRetriever.search(..., top_k=lex_fanin)` and `PgVectorSemanticRetriever.search(..., top_k=sem_fanin)`.
- Add `lex_fanin` and `sem_fanin` to the returned `metrics`, along with `pool_size` (see below).

Third, update `HybridRanker.rank` in `src/cv_search/ranking/hybrid.py`:

- Add a parameter `sem_fanin` (defaulting to `top_k` for backward compatibility within this repo).
- In `hybrid` mode, build the fusion pool as `lex_top + semantic_hits[:sem_fanin]` rather than `semantic_hits[:top_k]`.
- Return (or otherwise surface) the resulting pool size so `SearchProcessor` can persist it as `metrics.pool_size`.

Fourth, update/extend unit tests:

- Update existing `tests/test_hybrid_ranker_scoring.py` calls to match any signature changes.
- Add a new unit test that proves `sem_fanin` changes hybrid results when semantic hits beyond `top_k` contain a stronger match.
- Add a unit test for bounded lexical fan-in sizing so a large gate count cannot cause a huge lexical SQL limit.

## Concrete Steps

All commands must be run from the repository root in PowerShell.

1) Implement the code changes described above.

2) Run Ruff formatting and linting:

    PS C:\Users\mykha\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = "1"
    PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff format src tests
    PS C:\Users\mykha\Projects\cv-search-poc> uv run --extra dev ruff check src tests

3) Run unit tests only (ignore integration and eval):

    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest -q tests --ignore=tests\\integration --ignore=tests\\eval

## Validation and Acceptance

Acceptance criteria:

- Hybrid search results change when semantic fan-in changes (demonstrated via a unit test that varies `sem_fanin`).
- With a very large gated set, lexical fan-in stays bounded (demonstrated via a unit test that shows `lex_fanin` is capped and does not scale with gate size).
- Run payload metrics include: `gate_count`, `lex_fanin`, `sem_fanin`, and `pool_size`, and these are persisted to `metrics.json` by `SearchRunArtifactWriter`.
- Ruff is clean and unit tests pass when run with `--ignore=tests\\integration --ignore=tests\\eval`.

## Idempotence and Recovery

These changes are safe to re-run and re-test. If a change causes failures, revert the modified files and re-run the commands in `Concrete Steps` to confirm the baseline is restored.

## Artifacts and Notes

After a successful run that writes artifacts (for example, via the CLI `search-seat` command with a `--run-dir`), `metrics.json` should include keys showing the fan-in sizing and pool size:

    {
      "gate_count": 1234,
      "lex_fanin": 250,
      "sem_fanin": 25,
      "pool_size": 275
    }

## Interfaces and Dependencies

No new external dependencies are required. The change is confined to settings, orchestration, and ranking logic:

- `Settings` adds `search_fanin_multiplier: int` and `search_lex_fanin_max: int`.
- `SearchProcessor._run_single_seat(...)` computes and records fan-in metrics.
- `HybridRanker.rank(...)` accepts `sem_fanin` and uses it when constructing the hybrid pool.

---

Plan revision note (2025-12-14 19:37Z): Updated progress and outcomes to reflect the implemented fan-in sizing changes, new tests, and passing Ruff/unit-test validation.
