# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CV Search is a PostgreSQL-backed candidate search system using lexical retrieval (Postgres FTS + IDF-weighted tag matching) with LLM verdict ranking. It exposes a FastAPI REST API, a Streamlit UI, and a Click-based CLI for CV ingestion, multi-seat project searches, and presale team planning.

## Common Commands

All commands run from PowerShell at repo root. Use `uv run` or `.\.venv\Scripts\python`.

```powershell
# Start local dev Postgres container
docker compose -f docker/docker-compose.pg.yml up -d

# Initialize database schema
uv run python main.py init-db
uv run python main.py check-db

# Ingest mock CVs (resets DB and runs_dir)
uv run python main.py ingest-mock

# Google Drive ingestion (requires rclone setup)
uv run python main.py sync-gdrive
uv run python main.py ingest-gdrive

# Re-ingest from parsed JSON (skips PPTX parsing)
uv run python main.py ingest-json

# Parse natural language request into criteria JSON
uv run python -m cv_search.cli parse-request --text "need 1 .net middle azure developer"

# Single-seat search
uv run python -m cv_search.cli search-seat --criteria data\test\criteria.json --topk 3 --no-justify

# Project (multi-seat) search
uv run python -m cv_search.cli project-search --criteria data\test\criteria.json --topk 3 --no-justify

# Presale planning and search
uv run python main.py presale-plan --text "Mobile app + web dashboard with payments"
uv run python main.py presale-search --text "Mobile app + web dashboard with payments" --topk 3

# Streamlit UI
uv run streamlit run app.py
```

### Async Ingestion (requires Redis)

```powershell
# All-in-one: watcher + extractor + enricher
uv run python -m cv_search.cli ingest-async-all --enricher-workers 4

# Or run individually
uv run python -m cv_search.cli ingest-watcher
uv run python -m cv_search.cli ingest-extractor
uv run python -m cv_search.cli ingest-enricher --workers 4
```

### Testing

```powershell
# Run integration tests with isolated test database
uv run python -m dotenv -f .env.test run -- pytest tests\integration -q

# Run a single test file
uv run python -m dotenv -f .env.test run -- pytest tests\integration\test_cli_integration.py -v

# Run unit tests only
uv run pytest tests\unit -q
```

### Linting

```powershell
uv run ruff check src tests
uv run ruff format src tests
```

### Verification (Feedback Loop)

The project uses a verification feedback loop that ensures code quality before Claude completes tasks.

**Quick verification (lint + unit tests):**
```powershell
./scripts/verify-fast.ps1
```

**Full verification (lint + all tests):**
```powershell
./scripts/verify.ps1
```

**Stop Hook:** Claude Code is configured with a Stop hook that automatically runs `verify-fast.ps1` when Claude tries to complete a task. If verification fails, Claude must fix the issues before proceeding.

**Verify Subagent:** Use the `verify-app` subagent for a detailed verification report:
```
@verify-app run full verification
```

### Agent Commands

```powershell
# Developer Agent: 5-step implementation from plan
/implement-feature .claude/plans/my-feature.md

# Verifier Agent: E2E API verification for a specific endpoint
/verify-endpoint POST /api/v1/search/seat

# Pre-PR Agent: review, merge, squash, push, create GitHub PR
/pre-pr
/pre-pr --skip-review
/pre-pr --no-push

# Resume interrupted implementation
/resume-feature my-feature-id
```

See `AGENTS.md` for full documentation of the three-agent framework, verification profiles, and state persistence.

## Architecture

### Source Layout

```
src/cv_search/
├── api/                # FastAPI REST API (for chatbot integration)
│   ├── main.py         # App factory, lifespan, CORS, logging setup
│   ├── deps.py         # Dependency injection (DB, services, auth)
│   ├── exceptions.py   # Custom exception handlers (with logging)
│   ├── logging_config.py  # Centralized logging setup (LOG_LEVEL, format)
│   ├── middleware.py    # Request logging middleware (request ID, duration)
│   ├── search/         # Search endpoints (/api/v1/search/*)
│   ├── planner/        # Planner endpoints (/api/v1/planner/*)
│   ├── runs/           # Run history endpoints (/api/v1/runs/*)
│   └── health/         # Health check endpoints (/health, /ready)
├── cli/                # Click-based CLI (commands/ subdir)
├── core/               # Data models: Criteria, TeamMember, SeniorityEnum, role classification
├── db/                 # CVDatabase class + schema_pg.sql
├── search/             # SearchProcessor (orchestrates single/multi-seat searches)
├── ranking/            # LLMVerdictRanker (lexical scoring + LLM verdict)
├── retrieval/          # GatingFilter, LexicalRetriever
├── ingestion/          # CVIngestionPipeline, async workers, file watching
├── clients/            # OpenAIClient (standard + Azure)
├── config/             # Settings (pydantic-settings, loads from .env)
├── planner/            # Planner service (derives project seats from briefs)
├── presale/            # Presale search criteria generation
├── llm/                # Justification service, schemas, logging
├── lexicon/            # Tech/role/domain lexicon loaders
├── utils/              # Archive and utility helpers
└── app/                # Streamlit helpers (bootstrap, theme, results)
```

### Key Flows

**Search Pipeline:**
1. `GatingFilter` narrows candidates by role/seniority/must-have tags
2. `LexicalRetriever` scores gated candidates via IDF-weighted tag matching + FTS
3. `LLMVerdictRanker` sends top lexical candidates to LLM for final verdict ranking
4. Returns scored results with optional LLM-generated justifications per candidate

**Ingestion Pipeline:**
1. PPTX files parsed by `CVParser` (python-pptx)
2. `OpenAIClient.get_structured_cv()` extracts structured JSON from raw text
3. Tech tags normalized via lexicon reverse-index
4. `CVIngestionPipeline.upsert_cvs()` stores candidate, tags, experiences, FTS document
5. Async variant uses Redis queues (watcher -> extractor -> enricher)

**Project/Presale Search:**
1. `Planner.derive_project_seats()` converts a brief or criteria into seat definitions
2. `SearchProcessor.search_for_project()` iterates seats, calling `search_for_seat()` per seat
3. Artifacts (criteria.json, per-seat results) written to `runs/<timestamp>/`

### Data Model

Core Postgres tables (schema in `src/cv_search/db/schema_pg.sql`):
- `candidate` - identity, seniority, source metadata
- `candidate_doc` - summary_text, experience_text, tags_text, tsv_document (auto-generated tsvector for FTS)
- `candidate_tag` - (candidate_id, tag_type, tag_key, weight)
- `experience` - per-candidate work history
- `experience_tag` - tech/domain tags per experience
- `candidate_qualification` - certifications, languages, etc.
- `search_run` - audit log of search executions

### Environment Variables

Key settings (see `.env.example`):
- `DB_URL` - Postgres DSN (default: `postgresql://cvsearch:cvsearch@localhost:5433/cvsearch`)
- `OPENAI_API_KEY` / `USE_AZURE_OPENAI` / `AZURE_ENDPOINT` - LLM configuration
- `OPENAI_MODEL` - model name or Azure deployment name (default: `gpt-4.1-mini`)
- `REDIS_URL` - required for async ingestion
- `USE_OPENAI_STUB=1` - offline/stub mode (uses fake LLM responses)

### Stub Mode

For offline development or tests without OpenAI:
```powershell
$env:USE_OPENAI_STUB = "1"
uv run python main.py ingest-mock
```

## FastAPI REST API

The project includes a FastAPI-based REST API for chatbot integration. The API exposes the same search and planning functionality as the CLI and Streamlit UI.

### Running the API Server

```powershell
# Development (with auto-reload)
uv run uvicorn cv_search.api.main:app --reload --port 8000

# Or using the entry point script
uv run python api_server.py

# Production (multi-worker)
uv run uvicorn cv_search.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks DB) |
| GET | `/docs` | Swagger UI documentation |
| GET | `/redoc` | ReDoc documentation |
| POST | `/api/v1/search/seat` | Single-seat candidate search |
| POST | `/api/v1/search/project` | Multi-seat project search |
| POST | `/api/v1/search/presale` | Presale team search |
| POST | `/api/v1/planner/parse-brief` | Parse NL brief → Criteria |
| POST | `/api/v1/planner/derive-seats` | Derive project seats |
| POST | `/api/v1/planner/presale-plan` | Generate presale team plan |
| GET | `/api/v1/runs/` | List recent search runs |
| GET | `/api/v1/runs/{run_id}` | Get run details |
| POST | `/api/v1/runs/{run_id}/feedback` | Submit feedback |

### Example API Calls

```powershell
# Single-seat search
curl -X POST http://localhost:8000/api/v1/search/seat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "criteria": {
      "team_size": {
        "members": [{
          "role": "backend developer",
          "seniority": "senior",
          "tech_tags": ["python", "fastapi"]
        }]
      }
    },
    "top_k": 3
  }'

# Project search from brief
curl -X POST http://localhost:8000/api/v1/search/project \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"text": "Need 2 Python developers and 1 React frontend", "top_k": 3}'

# Parse brief to criteria
curl -X POST http://localhost:8000/api/v1/planner/parse-brief \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"text": "Mobile app with payments integration", "include_presale": true}'
```

All search endpoints (`/seat`, `/project`, `/presale`) accept an optional `include_cv_markdown` parameter (default: `false`). Set to `true` to include full CV markdown in results (adds ~3-5KB per candidate). The presale endpoint also accepts `include_extended` (default: `false`) to include extended team roles.

### API Authentication

Optional API key authentication can be enabled by setting `API_KEY` in `.env`:

```
API_KEY=your-secret-key
```

When set, all requests must include the `X-API-Key` header. In Swagger UI (`/docs`), use the **Authorize** button — the key is not shown as a per-endpoint parameter.

### Logging & Observability

The API uses structured Python logging configured via `LOG_LEVEL` env var (default: `INFO`).

- **Request middleware** logs every request with a unique request ID, method, path, status, and duration in ms
- **Exception handlers** log warnings for business errors and full tracebacks for unhandled exceptions
- **Search endpoints** log search start parameters, failed-status warnings with error details, and unhandled exceptions
- **Docker**: logs use `json-file` driver with rotation (`max-size: 50m`, `max-file: 5`). View with `docker compose logs api --tail 200`
- **Volumes**: `./runs` is mounted so search artifacts persist across container restarts

### API Environment Variables

- `API_HOST` - Host to bind (default: `0.0.0.0`)
- `API_PORT` - Port to bind (default: `8000`)
- `API_KEY` - Optional API key for authentication
- `API_CORS_ORIGINS` - Comma-separated CORS origins (default: `*`)
- `LOG_LEVEL` - Python logging level: DEBUG, INFO, WARNING, ERROR (default: `INFO`)

## Deployment (Production)

The project deploys as Docker containers (FastAPI API + Postgres) via `docker-compose.yml` at repo root.

### Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Python 3.11-slim, uv for deps, uvicorn 4 workers |
| `docker-compose.yml` | Production compose: `postgres:16` + `cvsearch-api` |
| `.env.production.example` | Template for production env vars |
| `scripts/deploy.ps1` | One-step deploy from Windows: zip → scp → deploy-vm.sh |
| `scripts/deploy-vm.sh` | Ubuntu VM setup: Docker install, build, schema init, health check |
| `scripts/vm-psql.ps1` | Run SQL queries against VM Postgres via SSH |

### One-Step Deploy (from Windows)

```powershell
# Deploy to default VM (builds, uploads, restarts)
.\scripts\deploy.ps1

# Deploy to specific VM
.\scripts\deploy.ps1 -VmIp 10.0.0.1

# Quick restart (skip Docker build)
.\scripts\deploy.ps1 -SkipBuild
```

`deploy.ps1` creates a zip, SCPs it to the VM, unzips, and runs `deploy-vm.sh`. Requires `.env.production` in repo root and SSH key at `~/Downloads/cvsearch-vm_key.pem`.

### Manual Deploy (local Docker)

```bash
# 1. Create .env from template
cp .env.production.example .env.production

# 2. Edit .env.production with real values (DB_PASSWORD, API_KEY, OpenAI creds)

# 3. Build and start
docker compose --env-file .env.production up -d --build

# 4. Initialize DB schema
docker compose exec api python -c "
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
settings = Settings()
db = CVDatabase(settings)
db.initialize_schema()
db.close()
"

# 5. Verify
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

### VM Remote Query

```powershell
# Run SQL directly on the VM's Postgres
.\scripts\vm-psql.ps1 "SELECT count(*) FROM candidate"
.\scripts\vm-psql.ps1 "SELECT candidate_id, name, seniority FROM candidate LIMIT 5"
```

### Production Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_USER` | No | `cvsearch` | Postgres user |
| `DB_PASSWORD` | **Yes** | `cvsearch` | Postgres password (change!) |
| `DB_NAME` | No | `cvsearch` | Postgres database name |
| `DB_PORT` | No | `5433` | Host-mapped Postgres port |
| `USE_AZURE_OPENAI` | No | `false` | Use Azure OpenAI endpoint |
| `OPENAI_API_KEY` | **Yes** | — | OpenAI or Azure OpenAI key |
| `AZURE_ENDPOINT` | If Azure | — | Azure OpenAI resource URL |
| `AZURE_API_VERSION` | If Azure | — | Azure API version |
| `OPENAI_MODEL` | No | `gpt-4.1-mini` | Model or Azure deployment name |
| `API_PORT` | No | `8000` | Host-mapped API port |
| `API_KEY` | Recommended | — | API auth key (`X-API-Key` header) |
| `API_CORS_ORIGINS` | No | `*` | Comma-separated CORS origins |
| `LOG_LEVEL` | No | `INFO` | Python logging level |

### Operational Commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f postgres

# Restart API only
docker compose restart api

# Rebuild after code changes
docker compose up -d --build api

# Stop everything
docker compose down

# Stop and remove volumes (destroys data)
docker compose down -v
```

### Database Backup & Restore

```bash
# Backup (local Docker)
docker compose exec postgres pg_dump -U cvsearch -d cvsearch > backup.sql

# Backup (VM via SSH)
ssh -i key.pem azureuser@vm_ip \
  "sudo docker compose -f /opt/cvsearch/docker-compose.yml exec -T postgres pg_dump -U cvsearch -d cvsearch" \
  > backup.sql

# Restore (pipe into running container)
docker compose exec -T postgres psql -U cvsearch -d cvsearch < backup.sql

# Schema-only reset (re-initialize without data)
docker compose exec api python -c "
from cv_search.config.settings import Settings
from cv_search.db.database import CVDatabase
db = CVDatabase(Settings())
db.initialize_schema()
db.close()
"
```

A full `backup.sql` exists at repo root (pg_dump from postgres 16). The `scripts/migrate_drop_vector.sql` script is a legacy migration that drops the pgvector extension if present.

## Streamlit Pages

- `app.py` - Home page, loads stateless services once
- `pages/1_Project_Search.py` - Multi-seat project search + presale planning
- `pages/2_Single_Seat_Search.py` - Single role search
- `pages/3_Admin_&_Ingest.py` - DB status, ingestion triggers
- `pages/4_Runs.py` - Browse search run history

## Database Querying (MCP)

Claude has access to the CV Search database via the `db-cv-search` MCP server. Use `mcp__db-cv-search__query` to run read-only SQL queries directly against the local PostgreSQL database.

**Example queries:**

```sql
-- Get search run details with feedback
SELECT run_id, run_kind, status, raw_text, feedback_sentiment, feedback_comment
FROM search_run WHERE run_id = 'your-run-id';

-- Count candidates by role
SELECT t.tag_key AS role, COUNT(*) AS cnt
FROM candidate_tag t WHERE t.tag_type = 'role'
GROUP BY t.tag_key ORDER BY cnt DESC;

-- Find candidates with specific tech tags
SELECT c.candidate_id, c.name, c.seniority
FROM candidate c
JOIN candidate_tag t ON c.candidate_id = t.candidate_id
WHERE t.tag_type = 'tech' AND t.tag_key IN ('python', 'langchain', 'rag');

-- List recent search runs
SELECT run_id, run_kind, user_email, created_at, status, result_count
FROM search_run ORDER BY created_at DESC LIMIT 10;
```

**Key tables:** `candidate`, `candidate_tag`, `candidate_doc`, `experience`, `experience_tag`, `candidate_qualification`, `search_run`

See `src/cv_search/db/schema_pg.sql` for full schema.
