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

### Default test flow (PowerShell, from repo root)

From the repository root (for example `PS C:\Users\<username>\Projects\cv-search-poc>`):

1. Start Postgres with pgvector locally if it is not already running:

   ```powershell
   PS C:\Users\<username>\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d
   ```

2. Point settings to the isolated test database and paths:

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
