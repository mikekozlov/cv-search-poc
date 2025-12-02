# cv-search

Postgres-backed candidate search with pgvector and Postgres FTS, exposed via a Streamlit UI and Click-based CLI. Semantic and lexical signals live in one database; agentic tests can fall back to an embedded SQLite store when Postgres or the pgvector driver are unavailable.

---

## Prerequisites

- Python 3.11 (repo ships a `.venv` but you can recreate with `python -m venv .venv`).
- Dependency manager: `uv` (preferred) or `pip` via `python -m ensurepip`.
- Docker Desktop (for the Postgres/pgvector container). If Docker is unavailable, the code falls back to SQLite for agentic tests only.
- Optional: Redis 7+ for async ingestion tests/workers.

---

## Environment

Copy `.env.example` to `.env` and set:

```powershell
# Postgres defaults match docker-compose.pg.yml
DB_URL="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch"
AGENTIC_DB_URL="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"

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

If Docker or pgvector wheels are blocked, agentic mode will transparently use the SQLite fallback so tests and CLI flows still run, but Postgres remains the target.

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

`run_dir` outputs live under `runs/` (or `data/test/tmp/agentic_runs` in agentic mode).

---

## Streamlit UI

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m streamlit run app.py
```

The Admin page shows Postgres table counts and pgvector/FTS extension status; ingestion buttons reuse the same pipeline as the CLI.

---

## Testing

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> $env:AGENTIC_TEST_MODE = "1"
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m pytest tests\integration -q
```

Agentic tests truncate the database between runs. If Postgres or pgvector wheels are unavailable, the tests exercise the SQLite fallback to keep coverage running, but Postgres remains the supported path for real deployments.
