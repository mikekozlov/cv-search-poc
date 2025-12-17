# Persist criteria.json artifacts for search and presale runs

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. Follow `.agent/PLANS.md` from the repository root when maintaining this plan.

## Purpose / Big Picture

Project search (`project-search` and the Streamlit "Project Search" page) and presale planning (`presale-plan`) build a canonical "criteria" object that drives seat derivation, candidate retrieval, and staffing output. Today, search runs persist seat-level ranking artifacts under `runs/<timestamp>/seat_*/`, but they do not persist the criteria used to produce those artifacts. Presale planning returns Criteria JSON to stdout but does not persist it under `runs/` at all.

After this change, every run writes the criteria object to a `criteria.json` file under the run directory:

1. Single-seat search writes `<run_dir>/criteria.json` alongside existing `results.json`, `metrics.json`, etc.
2. Project (multi-seat) search writes `<run_dir>/criteria.json` for the project-level criteria, and each seat directory writes `<run_dir>/seat_*/criteria.json` for the per-seat criteria used for that seat’s search.
3. Presale planning (`presale-plan`) writes `<run_dir>/criteria.json` for the enriched Criteria that includes the presale team arrays.

You can see it working by running `project-search` or `presale-plan` and then inspecting the newest folder under `runs/` (or whatever is configured via `RUNS_DIR`) to confirm `criteria.json` is present.

## Progress

- [x] (2025-12-14 18:30Z) Reviewed where search and presale flows create `run_dir` and write artifacts.
- [x] (2025-12-14 18:36Z) Update seat artifact writer to persist `criteria.json`.
- [x] (2025-12-14 18:36Z) Ensure single-seat payloads always include `criteria` so the artifact writer can persist it even on early exits.
- [x] (2025-12-14 18:37Z) Persist project-level `criteria.json` in the base project search run directory.
- [x] (2025-12-14 18:38Z) Persist presale-plan `criteria.json` under `runs/` without changing stdout output format.
- [x] (2025-12-14 18:39Z) Add unit test coverage for `criteria.json` artifact writing.
- [x] (2025-12-14 18:44Z) Run Ruff and unit tests (excluding `tests/integration` and `tests/eval`).

## Surprises & Discoveries

- Observation: Seat-level search artifacts are written by `SearchRunArtifactWriter`, but that writer does not persist the `criteria` field even though it is present in the normal payload path.
  Evidence: `src/cv_search/search/artifacts.py`.

- Observation: `_run_single_seat` returns early for strict-gating empty results without including `criteria` in the payload, so even adding `criteria.json` to the writer would miss that case.
  Evidence: `src/cv_search/search/processor.py`.

## Decision Log

- Decision: Use a single filename `criteria.json` consistently for the criteria used at that directory scope (project-level at run root; seat-level inside each `seat_*` folder).
  Rationale: Keeps inspection simple: every artifact folder has a single, predictable criteria file next to its results.
  Date/Author: 2025-12-14 / Codex.

- Decision: Keep `presale-plan` stdout output as Criteria JSON and persist `criteria.json` as a side effect under `runs/`.
  Rationale: Avoids breaking existing CLI usage that pipes stdout to a file while still providing the requested persisted artifact.
  Date/Author: 2025-12-14 / Codex.

## Outcomes & Retrospective

Search and presale runs now persist their canonical criteria JSON alongside other run artifacts. This makes runs self-describing: you can inspect any run directory and see the exact criteria used without relying on stdout or UI state.

## Context and Orientation

Relevant code paths:

- Seat-level artifact writing lives in `src/cv_search/search/artifacts.py` (`SearchRunArtifactWriter.write`). It currently writes `gating.sql.txt`, optional ranking/vector artifacts, and `metrics.json`/`results.json` to a per-seat folder.
- Search orchestration lives in `src/cv_search/search/processor.py` (`SearchProcessor.search_for_seat` and `SearchProcessor.search_for_project`). Project search creates a base run directory and then runs each seat search under `seat_*/` subfolders.
- The Click CLI commands live in `src/cv_search/cli/commands/search.py` and `src/cv_search/cli/commands/presale_search.py`. Project search accepts `--run-dir`, and presale planning now also accepts `--run-dir`.

Terminology used in this plan:

- "run directory" (`run_dir`): a folder under `runs/` (or `$env:RUNS_DIR`) used to persist artifacts for a single CLI/UI invocation.
- "criteria": the canonical structured JSON object that describes the project/team requirements, produced either by parsing a brief or loading a JSON file.

## Plan of Work

1. In `src/cv_search/search/artifacts.py`, extend `SearchRunArtifactWriter.write` to write `criteria.json` when the payload includes a `criteria` field.

2. In `src/cv_search/search/processor.py`, ensure `_run_single_seat` includes a `criteria` field in its strict-gate-empty early return payload so the writer can always persist `criteria.json`.

3. In `src/cv_search/search/processor.py`, after the base project run directory is created for a successful multi-seat search, write the project-level criteria dict to `<run_dir>/criteria.json` using the same JSON formatting conventions as other artifacts.

4. In `src/cv_search/cli/commands/presale_search.py` (and `src/cv_search/cli/commands/search.py` for consistency), update `presale-plan` to:
   - Create a run directory (default `runs/<timestamp>/` respecting `RUNS_DIR` via settings).
   - Write the enriched Criteria JSON to `<run_dir>/criteria.json`.
   - Continue to print Criteria JSON to stdout unchanged.

5. Add a focused unit test that exercises `SearchRunArtifactWriter.write` and asserts `criteria.json` is written with the expected content.

## Concrete Steps

From repo root `PS C:\Users\mykha\Projects\cv-search-poc>`:

1. Implement the code changes described above.

2. Run Ruff (format then lint):

    $env:AGENTIC_TEST_MODE = "1"
    uv run --extra dev ruff format src tests
    uv run --extra dev ruff check src tests

3. Run unit tests (explicitly excluding integration and eval tests):

    uv run pytest tests -q --ignore tests\\integration --ignore tests\\eval

## Validation and Acceptance

Behavior acceptance (manual):

- Run a project search and verify criteria artifacts exist:

    uv run python -m cv_search.cli project-search --criteria data\\test\\criteria.json --topk 1 --no-justify

  Expect a JSON payload containing `run_dir`. Under that directory, expect:

    - <run_dir>\\criteria.json
    - <run_dir>\\seat_01_*\\criteria.json
    - <run_dir>\\seat_01_*\\results.json

- Run presale plan and verify criteria artifact exists:

    uv run python -m cv_search.cli presale-plan --text "Need a mobile+web MVP with payments and analytics"

  Expect stdout to be Criteria JSON (as before). Under the newest directory in `runs/`, expect `<run_dir>\\criteria.json`.

Automated acceptance:

- Ruff is clean (`ruff check` succeeds).
- Unit tests pass (`pytest` with `--ignore tests\\integration --ignore tests\\eval` succeeds).
- The new unit test fails before the change and passes after.

## Idempotence and Recovery

Re-running the same commands is safe. Artifact writing overwrites `criteria.json` in the selected run directory. If a mistake is made in artifact naming or serialization, revert the affected file(s) and re-run Ruff and unit tests.

## Artifacts and Notes

Keep JSON formatting consistent with existing artifacts: UTF-8, `indent=2`, `ensure_ascii=False`.

## Interfaces and Dependencies

No new external dependencies are required.

Existing interfaces extended:

- `SearchRunArtifactWriter.write(run_dir, payload)` will additionally write `criteria.json` when `payload["criteria"]` is present.
