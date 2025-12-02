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
PS C:\Users\<you>\Projects\cv-search-poc> python -m ensurepip
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m pip install --upgrade pip
# Prefer uv if available; otherwise install editable package with pip
PS C:\Users\<you>\Projects\cv-search-poc> uv sync
# If uv cannot reach PyPI, run:
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m pip install -e .
```

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

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"
PS C:\Users\<you>\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"
PS C:\Users\<you>\Projects\cv-search-poc> $env:DATA_DIR = "data/test"
PS C:\Users\<you>\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"
PS C:\Users\<you>\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m pytest tests\integration -q
```

Integration tests truncate the Postgres database between runs and rely on the pgvector extensions created by `init-db`. Provide a dedicated test database (e.g., `cvsearch_test`) so test data stays isolated.
