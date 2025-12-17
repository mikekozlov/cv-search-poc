# Fix hybrid ranking signals (IDF + semantic score)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository includes `.agent/PLANS.md`, which defines the required structure and maintenance rules for ExecPlans. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Search results are currently “hybrid” (lexical + semantic), but two internal scoring signals are mis-specified: the lexical “IDF sums” do not vary by candidate, and the semantic score ignores the actual pgvector similarity values. After this change, hybrid/lexical/semantic ranking uses meaningful, per-candidate signals so that results better reflect: (1) which “must-have” skills are actually present, and (2) how similar the candidate document is to the query embedding.

You can see it working by running the unit tests: new ranking-focused tests fail before the change and pass after, and existing unit tests remain green.

## Progress

- [x] (2025-12-12 17:05Z) Reviewed current hybrid ranking implementation and identified that `must_idf_sum`/`nice_idf_sum` are constant-per-query and semantic fusion uses rank position rather than pgvector similarity.
- [x] (2025-12-12 17:11Z) Updated `CVDatabase.rank_weighted_set` to return per-candidate IDF hit sums (and totals for normalization).
- [x] (2025-12-12 17:11Z) Updated `HybridRanker` to use pgvector similarity scores (not rank-based) and to sort lexical mode by the lexical scoring formula.
- [x] (2025-12-12 17:11Z) Added unit tests covering the two fixes.
- [x] (2025-12-12 17:11Z) Ran Ruff (format + lint) and ran unit tests (excluding `tests/integration` and `tests/eval`).

## Surprises & Discoveries

- Observation: Lexical “IDF sums” do not affect ordering because they are currently constant across candidates for a given query.
  Evidence: `CVDatabase.rank_weighted_set` computes a single `must_sum`/`nice_sum` and writes that same value into every returned row.

- Observation: Semantic scoring in the fusion layer ignores the actual pgvector similarity score and instead uses a simple “rank fraction” derived from `rank`.
  Evidence: `HybridRanker.rank` derives `sem_score[cid]` from `h["rank"]`, not from `h["score"]`/`h["distance"]`.

## Decision Log

- Decision: Compute per-candidate IDF hit sums in SQL by joining `candidate_tag` against a small “query weights” table produced via `UNNEST(%s::text[], %s::double precision[])`.
  Rationale: Avoids dynamic SQL and ensures the IDF-weighted sums vary by candidate without extra round-trips.
  Date/Author: 2025-12-12 / Codex

- Decision: Use the pgvector similarity score already returned by `CVDatabase.vector_search` (`score = 1 - (embedding <=> query)`), clamped to `[0, 1]`, instead of rank-based scoring.
  Rationale: Makes `w_sem` actually mean “trust semantic similarity”, not “trust semantic ordering”.
  Date/Author: 2025-12-12 / Codex

- Decision: Normalize the lexical IDF hit sums by the query-level total (`must_idf_sum / must_idf_total`) when computing the lexical score used for ordering.
  Rationale: Keeps the lexical scoring components on a stable 0–1 scale so the coefficients remain meaningful as the number of tags changes.
  Date/Author: 2025-12-12 / Codex

## Outcomes & Retrospective

Hybrid ranking now uses meaningful signals:

- Lexical: per-candidate IDF hit sums are computed in SQL and the fusion layer normalizes them for scoring.
- Semantic: similarity uses pgvector’s returned score/distance instead of rank-derived fractions.
- Validation: `uv run --extra dev ruff check src tests` is clean and `uv run pytest -q tests --ignore=tests\\integration --ignore=tests\\eval` passes (15 tests).

## Context and Orientation

The single-seat search pipeline is orchestrated by `src/cv_search/search/processor.py`. The high-level flow is:

1) Gating: `GatingFilter.filter_candidates(...)` narrows the candidate IDs based on canonical role + allowed seniority ladder.

2) Lexical retrieval: `LexicalRetriever.search(...)` calls `CVDatabase.rank_weighted_set(...)` (structured tag matching) and optionally `CVDatabase.fts_search(...)` (Postgres full-text search over `candidate_doc.tsv_document`).

3) Semantic retrieval: `PgVectorSemanticRetriever.search(...)` embeds a query string and calls `CVDatabase.vector_search(...)` (pgvector cosine similarity).

4) Late fusion: `HybridRanker.rank(...)` combines lexical and semantic signals into a final ordering.

Definitions used in this plan:

- “IDF” (inverse document frequency): a weight that increases for rarer tags; here computed from how many candidates have a given tag in `candidate_tag`.
- “Late fusion”: combining the output scores of two independent retrieval systems (lexical and semantic) into one final score.

Key files:

- `src/cv_search/db/database.py`: Postgres queries for tag ranking, FTS, and pgvector search.
- `src/cv_search/retrieval/lexical.py`: orchestration of tag-weighted ranking + FTS.
- `src/cv_search/retrieval/pgvector.py`: orchestration of query embedding + pgvector search.
- `src/cv_search/ranking/hybrid.py`: late-fusion scoring and final ranked payload assembly.

## Plan of Work

First, change the lexical ranking SQL in `CVDatabase.rank_weighted_set` so it returns per-candidate weighted sums:

- For each candidate, compute `must_idf_sum` as the sum of IDF weights for the “must-have” tags that are present for that candidate.
- For each candidate, compute `nice_idf_sum` similarly for “nice-to-have” tags.
- Also return `must_idf_total`/`nice_idf_total` (constant totals for the query) so the fusion layer can normalize these hit sums to a stable 0–1 range if needed.

Second, update `HybridRanker.rank`:

- Semantic: populate `sem_score[cid]` from the pgvector similarity score (`h["score"]` or `1 - h["distance"]`) rather than using `rank` position.
- Lexical mode: order the “lexical” results by the lexical scoring formula (not by the raw SQL row order), so the formula actually controls what the user sees in lexical-only searches.
- Keep the payload structure stable: `score_components.lexical.must_idf_sum` and `score_components.semantic.score` should remain present.

Third, add unit tests:

- A test that demonstrates semantic fusion prefers a higher similarity score even if the `rank` field disagrees.
- A test that demonstrates lexical mode is sorted by the lexical scoring formula (so a candidate with stronger lexical signals outranks a weaker one, regardless of incoming list order).

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

- The new unit tests for hybrid ranking pass.
- Existing unit tests pass (running `pytest` with `--ignore=tests\\integration --ignore=tests\\eval`).
- Ruff has no remaining findings.

## Idempotence and Recovery

These changes are safe to re-run and re-test:

- Re-running Ruff and unit tests is always safe.
- The SQL changes are read-only queries; if a query error occurs during development, `CVDatabase.rollback()` can be used to clear the failed transaction and retry.

## Artifacts and Notes

Test transcript (unit tests only):

    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest -q tests --ignore=tests\\integration --ignore=tests\\eval
    ...............                                                          [100%]
    15 passed in 8.38s

## Interfaces and Dependencies

At the end of this plan, the following interfaces must exist and be used:

- `CVDatabase.rank_weighted_set(...)` returns lexical rows that include per-candidate `must_idf_sum` and `nice_idf_sum`, plus query-level totals `must_idf_total` and `nice_idf_total` (same value across returned rows).
- `HybridRanker.rank(...)` uses semantic similarity scores from semantic hits (`score`/`distance`) rather than rank-only scoring.

---

Plan revision note (2025-12-12 17:11Z): Updated progress, decision log, outcomes, and validation artifacts to reflect the implemented change set and passing unit-test validation.
