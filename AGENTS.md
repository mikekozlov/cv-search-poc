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
Run only unit tests, don't run integration tests that reside under /tests/integration folder and /tests/eval folder 

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


## Rider-navigable file references (terminal linkify)

When citing code locations, always emit Rider-linkifiable file references **inline**, immediately after the step they support (not as a separate list at the end).

### Placement (mandatory)
- Any time you mention a **specific function/method/class/CLI command entrypoint** (e.g., `ingest_gdrive_cmd`, `run_gdrive_ingestion`, `_process_single_cv_file`, `upsert_cvs`, etc.), you MUST place the corresponding file reference(s) **directly under that line**.
- Do **not** collect references into a “References” or “File references” section at the bottom.
- If a step maps to multiple relevant locations, output **multiple reference lines** immediately under that step (one per line).

### Reference line format (must be Rider-linkifiable)
A “reference line” must be:

[optional leading spaces]relative/path/from/repo/root.ext:LINE

Rules:
- The reference line may have **leading spaces only** (to visually “nest” under the step).
- After any leading spaces, the line must contain **only** the `path:line` token.
    - No bullets (`-`, `*`, `•`)
    - No prefixes/labels (`File:`, `Ref:`, `at`, `→`, `↳`)
    - No surrounding punctuation (`(` `)` `[` `]` `"` `'` `` ` ``)
    - No trailing punctuation after the line number (no `,` `.` `)` etc.)
- Prefer forward slashes `/`.
- Avoid line-wrapping inside the path. If needed, split the explanation but keep the reference line intact.

### Example (good)
- ingest-gdrive --file <name> calls ingest_gdrive_cmd(...).
  src/cv_search/cli/commands/ingestion.py:137

- ingest_gdrive_cmd instantiates CVIngestionPipeline and calls run_gdrive_ingestion(...).
  src/cv_search/ingestion/pipeline.py:424

- run_gdrive_ingestion:
  src/cv_search/ingestion/pipeline.py:394
  src/cv_search/ingestion/pipeline.py:326
    - _partition_gdrive_files(...) skips unchanged/out-of-inbox files.
      src/cv_search/ingestion/pipeline.py:269
    - Submits _process_single_cv_file(...) for that file.
      src/cv_search/ingestion/pipeline.py:172

- _process_single_cv_file(...) extracts text then requests structured CV.
  src/cv_search/ingestion/pipeline.py:172
  src/cv_search/ingestion/cv_parser.py:15
  src/cv_search/clients/openai_client.py:464
  src/cv_search/clients/openai_client.py:312

- upsert_cvs(...) embeds and upserts candidate doc then commits.
  src/cv_search/retrieval/local_embedder.py:30
  src/cv_search/db/database.py:148
  src/cv_search/db/database.py:335
  src/cv_search/db/database.py:91

### Examples (bad — do not do this)
- ingest-gdrive ... (src/cv_search/cli/commands/ingestion.py:137)
- ingest-gdrive ... src/cv_search/cli/commands/ingestion.py:137,
- - src/cv_search/cli/commands/ingestion.py:137
- File: src/cv_search/cli/commands/ingestion.py:137
- `src/cv_search/cli/commands/ingestion.py:137`

---

## Three-Agent Development Framework

This repository uses a three-agent autonomous development framework for implementing features end-to-end. The agents are invoked via Claude Code slash commands.

### Agents

| Agent | Command | Purpose |
|-------|---------|---------|
| **Developer Agent** | `/implement-feature {plan}` | 5-step implementation from plan (UNDERSTAND -> ANALYZE -> IMPLEMENT -> VERIFY -> CONCLUDE) |
| **Verifier Agent** | `/verify-endpoint {METHOD} {PATH}` | Standalone E2E API verification for any endpoint |
| **Pre-PR Agent** | `/pre-pr [--skip-review] [--no-push]` | Code review, regression analysis, squash, push, GitHub PR |
| **Resume Agent** | `/resume-feature {feature-id}` | Resume interrupted implementation from persisted state |

### Typical Workflow

1. **Plan** — User describes the feature; Claude enters Plan Mode and writes a plan to `.claude/plans/`
2. **Implement** — User runs `/implement-feature .claude/plans/my-feature.md`
   - Developer Agent parses plan, discovers patterns, implements task-by-task
   - Runs lint + unit tests after each task
   - Delegates E2E verification to the Verifier Agent (via `e2e-api-test` skill)
3. **Resume** (if interrupted) — User runs `/resume-feature my-feature-id`
   - Loads persisted state, skips completed tasks, carries forward failure history
4. **Ship** — User runs `/pre-pr`
   - Reviews code, analyzes regression risk, merges main, squashes, pushes, creates GitHub PR

### ExecPlans vs Feature Plans

| Aspect | ExecPlan (`.agent/plans/`) | Feature Plan (`.claude/plans/`) |
|--------|---------------------------|--------------------------------|
| **Purpose** | Living design document for complex features | Terse, machine-parsable task list |
| **Consumer** | Any agent or human | `/implement-feature` Developer Agent |
| **Format** | Free-form with required sections per `.agent/PLANS.md` | Structured `## Implementation Tasks` with `TASK-ID: desc \| files: ... \| done_when: ...` |
| **When to use** | Large design work, architectural decisions | Features implemented via `/implement-feature` |
| **Coexistence** | Both can exist for the same feature | Feature Plan references ExecPlan if one exists |

### Verification Profiles

The Developer Agent classifies each feature into a verification profile that determines which checks to run:

```
Does the feature add/modify a FastAPI router endpoint?
  NO  -> unit-only
  YES -> Does the endpoint route through SearchProcessor/Planner (which call OpenAI)?
    NO  -> e2e-light
    YES -> Does the endpoint write to search_run or modify candidate data?
      NO  -> e2e-full
      YES -> e2e-mutation
```

| Profile | What runs | Stub mode | Example endpoints |
|---------|-----------|-----------|-------------------|
| **unit-only** | Lint + unit tests | N/A | Database methods, utility functions |
| **e2e-light** | Server + call + verify response | None | `GET /health`, `GET /api/v1/runs/` |
| **e2e-full** | Server + call + verify response | `USE_OPENAI_STUB=1` | `POST /api/v1/planner/parse-brief` |
| **e2e-mutation** | Server + call + verify response + verify DB | `USE_OPENAI_STUB=1` | `POST /api/v1/search/seat`, `POST /api/v1/search/project` |

### State Persistence

Feature state is persisted at `$env:TEMP\cvsearch-feature-state\{feature-id}.json` to survive context compaction and session restarts. Key features:

- **Task-level tracking**: Each task has status (pending/in-progress/completed), attempt count, and last failure signature
- **Failure history**: All failure signatures are recorded to enable duplicate failure detection
- **Duplicate failure detection**: If the same error signature appears twice consecutively, the agent stops immediately instead of burning retries on the same misidentified root cause
- **Clean exit**: State file is deleted on successful completion; preserved on failure for `/resume-feature`

### Integration with Existing Automation

The three-agent framework layers on top of existing automation:

- **`stop-verify.ps1`** — Unchanged. Remains the final safety net (stop hook)
- **`verify-app` subagent** — Unchanged. Complements the Verifier Agent for broader verification
- **`verify-fast.ps1` / `verify.ps1`** — Called by the agents as lint/test steps
- **ExecPlan system** — Unchanged. Feature Plans coexist with ExecPlans
