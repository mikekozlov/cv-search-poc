# AGENTS.md

## Purpose

This document sets expectations for how automated agents (and humans following the same conventions) should work in this repository. It complements `.agent/PLANS.md`, which defines how to author and maintain ExecPlans.

Whenever you are making non-trivial changes (new features, significant refactors, or multi-file edits), you must:

- Drive the work from an ExecPlan as described in `.agent/PLANS.md`.
- Assume a **Windows host** and **PowerShell** as the only supported shell.
- **Run tests after any code change**, fix failures, and only then provide a final answer.

---

## Environment and Shell Assumptions

- Host OS: **Windows** (e.g., Windows 10/11).
- Shell: **PowerShell** (PowerShell 7+ preferred).
- Repository root: typically something like `C:\Users\<username>\Projects\cv-search-poc`.

All commands shown in ExecPlans or in your final answers must be valid **PowerShell** commands:

- Use Windows paths and separators, for example:

    - `C:\Users\<username>\Projects\cv-search-poc`
    - `python scripts\run_agentic_suite.py`

- Use PowerShell environment variable syntax:

    - Correct:
        - `$env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"`
        - `$env:REDIS_URL = "redis://:Temp@Pass_word1@localhost:6379/15"`
    - Do **not** use Bash syntax such as:
        - `export DB_URL=...`
        - `REDIS_URL=... pytest ...`
        - `./venv/bin/python`

- When you show commands, include the working directory where relevant, e.g.:

    - `PS C:\Users\<username>\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"`
    - `PS C:\Users\<username>\Projects\cv-search-poc> python scripts\run_agentic_suite.py`

If you copy or adapt instructions from upstream or other docs that use Bash/zsh syntax, you must rewrite them into PowerShell form in your ExecPlan or final answer.

---

## ExecPlans

When writing **complex features** or **significant refactors**, you must use an ExecPlan from design through implementation:

- ExecPlans are stored under `.agent/plans/*.md`.
- The rules for structure, formatting, and maintenance are defined in `.agent/PLANS.md`.
- Treat `.agent/PLANS.md` as authoritative and follow it "to the letter".

At a minimum, before changing code:

1. Read `.agent/PLANS.md` and understand its requirements.
2. Create or update an appropriate ExecPlan under `.agent/plans/`.
3. Ensure the ExecPlan is self-contained and beginner-friendly, as required by `.agent/PLANS.md`.

---

## Mandatory Testing for Any Code Change

If you change **any code or tests**, you must run tests and ensure they pass before giving a final answer.
Run only unit tests, don't run integration tests that reside under /tests/integration folder

### Default test flow (PowerShell, from repo root)

From the repository root (for example `PS C:\Users\<username>\Projects\cv-search-poc>`). Assume Postgres and Redis are already running and reachable; do not start Docker containers from these instructions.

1. Point settings to the isolated test database and paths:

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
   PS C:\Users\<username>\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"
   PS C:\Users\<username>\Projects\cv-search-poc> $env:DATA_DIR = "data/test"
   PS C:\Users\<username>\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"
   PS C:\Users\<username>\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"
   ```

3. Run the integration suite:

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> uv run pytest tests\integration -q
   ```

---

## Mandatory Linting & Formatting for Any Python Change

If you change **any Python code**, run Ruff before tests and before giving a final answer. Ruff configuration lives in `pyproject.toml`; linting must be clean before proceeding.

### Default lint/format flow (PowerShell, from repo root)

From the repository root (for example `PS C:\Users\<username>\Projects\cv-search-poc>`):

1. Enable agentic test mode (same guard used for tests):

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = "1"
   ```

2. Format the Python sources (optional but recommended):

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> uv run --extra dev ruff format src tests
   ```

3. Run the linter and fix all reported issues:

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> uv run --extra dev ruff check src tests
   ```

   - Do not finish a task with outstanding Ruff errors.
   - If a rule must be suppressed, use a focused `# noqa` or `pyproject.toml` ignore entry and justify it in the ExecPlan’s **Decision Log**.

4. After Ruff is clean, run the integration suite as described above:

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> python scripts\run_agentic_suite.py
   ```

ExecPlans involving Python changes must list the Ruff format/lint steps ahead of tests in both **Concrete Steps** and **Validation and Acceptance** so that future agents follow the same order.

### Live ingest eval (optional, slow)

The ingest-gdrive eval harness is opt-in and may call the live OpenAI API. Assume Postgres and Redis are already running and reachable via your `.env.test` values; do not start Docker containers here. To run it:

```powershell
PS C:\Users\<username>\Projects\cv-search-poc> $env:RUN_INGEST_EVAL = "1"
PS C:\Users\<username>\Projects\cv-search-poc> $env:EVAL_USE_LIVE = "1"   # clears stubs inside the test
PS C:\Users\<username>\Projects\cv-search-poc> uv run pytest tests\eval\test_ingest_gdrive_eval.py::test_ingest_gdrive_eval_backend -q
```

Explicitly: Docker is not required for these instructions. Point `DB_URL` at an already-running Postgres on `localhost:5433/cvsearch_test` (or your configured host) and ensure Redis in `.env.test` is reachable.

The eval test is skipped unless `RUN_INGEST_EVAL` is set; always set that (and `EVAL_USE_LIVE` if you want live OpenAI) before invoking pytest so the test actually runs.
