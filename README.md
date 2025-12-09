# cv-search

Postgres-backed candidate search with pgvector and Postgres FTS, exposed via a Streamlit UI and Click-based CLI. Semantic and lexical signals live in one database; tests run against the same Postgres/pgvector stack with explicit stubs for embeddings/LLM behavior.

---

## Prerequisites

- Python 3.11 (repo ships a `.venv` but you can recreate with `python -m venv .venv`).
- Dependency manager: `uv` (preferred) or `pip` via `python -m ensurepip`.
- Docker Desktop (for the Postgres/pgvector container).
- Optional: Redis 7+ for async ingestion tests/workers.

---

## Environment

Copy `.env.example` to `.env` and set:

```powershell
# Postgres defaults match docker-compose.pg.yml
DB_URL="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch"

# OpenAI or Azure OpenAI settings
OPENAI_MODEL="gpt-4.1-mini"
OPENAI_EMBED_MODEL="text-embedding-3-large"
```

---

## Install dependencies (PowerShell)

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m ensurepip --upgrade
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m pip install --upgrade pip setuptools
$env:UV_PROJECT_ENVIRONMENT = ".venv"
PS C:\Users\<you>\Projects\cv-search-poc> uv sync --inexact --python .\.venv\Scripts\python.exe
```
Important:

> **Do not run plain `uv sync` on this venv anymore**
> or pip will be uninstalled

---

## Database (pgvector)

```powershell
# Start Postgres 16 + pgvector locally
PS C:\Users\<you>\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d

# Initialize schema and extensions
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py init-db

# Sanity check tables/extensions
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py check-db
```

Postgres with pgvector/pg_trgm is required. If the container is not running, commands will fail fast instead of falling back to SQLite.

---

## Ingestion

```powershell
# Rebuild DB with bundled mock CVs
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py ingest-mock

# Google Drive ingestion (requires rclone and configured remote)
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py sync-gdrive
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py ingest-gdrive
```

---

## Search (CLI)

```powershell
# Single-seat search
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py search-seat --criteria data\test\criteria.json --topk 3 --mode hybrid --no-justify

# Project (multi-seat) search
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py project-search --criteria data\test\criteria.json --topk 3 --no-justify
```

`run_dir` outputs live under `runs/` (or whatever you set via `RUNS_DIR`).

---

## Streamlit UI

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m streamlit run app.py
```

The Admin page shows Postgres table counts and pgvector/FTS extension status; ingestion buttons reuse the same pipeline as the CLI.

---

## Testing

Use the dedicated `.env.test` so integration runs stay isolated from your dev data:

```powershell
# Start pgvector if not already running
PS C:\Users\<you>\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d

# Run integration suite with test env vars
PS C:\Users\<you>\Projects\cv-search-poc> uv run python -m dotenv -f .env.test run -- pytest tests\integration -q
```

Integration tests truncate the Postgres database between runs and rely on the pgvector extensions created by `init-db`. The `.env.test` defaults to `cvsearch_test` so test data stays isolated from `DB_URL` in your main `.env`.
