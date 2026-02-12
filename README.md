# cv-search

Postgres-backed candidate search combining lexical retrieval (FTS + IDF tag matching) with LLM verdict ranking. Exposed via a FastAPI REST API, Streamlit UI, and Click-based CLI.

---

## Prerequisites

- Python 3.11 (repo ships a `.venv` but you can recreate with `python -m venv .venv`).
- Dependency manager: `uv` (preferred) or `pip` via `python -m ensurepip`.
- Docker Desktop (for the local Postgres container).
- Optional: Redis 7+ for async ingestion tests/workers.

---

## Environment

Copy `.env.example` to `.env` and set:

```powershell
# Postgres defaults match docker-compose.pg.yml
DB_URL="postgresql://cvsearch:cvsearch@localhost:5433/cvsearch"

# OpenAI or Azure OpenAI settings
OPENAI_MODEL="gpt-4.1-mini"
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

## Database

```powershell
# Start Postgres 16 locally
PS C:\Users\<you>\Projects\cv-search-poc> docker compose -f docker/docker-compose.pg.yml up -d

# Initialize schema
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py init-db

# Sanity check tables
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py check-db
```

Postgres 16 with pg_trgm is required (no pgvector needed).

---

## Ingestion

```powershell
# Rebuild DB with bundled mock CVs
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py ingest-mock

# Google Drive ingestion (requires rclone and configured remote)
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py sync-gdrive
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py ingest-gdrive

# Re-ingest from parsed CV JSON (skips PPTX parsing)
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python main.py ingest-json
```

---

## Async ingestion (watcher + workers)

Async ingestion requires Redis. Set `REDIS_URL` in your `.env` (for example: `redis://:your-password@localhost:6379/0`).

Use the all-in-one command to start the watcher, extractor, and enricher in one terminal:

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m cv_search.cli ingest-async-all
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m cv_search.cli ingest-async-all --enricher-workers 4
```

You can also run them individually:

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m cv_search.cli ingest-watcher
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m cv_search.cli ingest-extractor
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m cv_search.cli ingest-enricher
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m cv_search.cli ingest-enricher --workers 4
```

---

## Search (CLI)

```powershell
# parse request
uv run python -m cv_search.cli parse-request --text "need 1 .net middle azure developer" > tmp_criteria.json


# Single-seat search
uv run python -m cv_search.cli search-seat --criteria data\test\criteria.json --topk 3 --no-justify

# Project (multi-seat) search
uv run python -m cv_search.cli project-search --criteria data\test\criteria.json --topk 3 --no-justify
```

`run_dir` outputs live under `runs/` (or whatever you set via `RUNS_DIR`).

---

## Streamlit UI

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m streamlit run app.py
```

Use the sidebar to open **Project Search & Planning** for project search and presale planning. The **Plan Presale Team** tab can generate a presale plan and run the presale role search directly in the UI.

The Admin page shows Postgres table counts and FTS status; ingestion buttons reuse the same pipeline as the CLI. For a step-by-step presale runbook, see `docs/presale.md`.

---

## Streamlit Auth (Auth0 OIDC)

Streamlit can authenticate via Auth0 (OIDC). The configuration lives in `.streamlit/secrets.toml`, and the Auth0 redirect URI must end with `/oauth2callback`.

### Local setup

Set the Auth0 environment variables, generate the secrets file if missing, then run Streamlit:

```powershell
PS C:\Users\<you>\Projects\cv-search-poc> $env:AUTH0_DOMAIN = "your-tenant.us.auth0.com"
PS C:\Users\<you>\Projects\cv-search-poc> $env:AUTH0_CLIENT_ID = "your-auth0-client-id"
PS C:\Users\<you>\Projects\cv-search-poc> $env:AUTH0_CLIENT_SECRET = "your-auth0-client-secret"
PS C:\Users\<you>\Projects\cv-search-poc> $env:AUTH0_SCOPE = "openid profile email"
PS C:\Users\<you>\Projects\cv-search-poc> $env:AUTH0_ORG = "org_0000000000000000"
PS C:\Users\<you>\Projects\cv-search-poc> $env:AUTH0_AUDIENCE = "https://api.example.com"  # optional
PS C:\Users\<you>\Projects\cv-search-poc> $env:STREAMLIT_COOKIE_SECRET = "replace-with-a-long-random-string"
PS C:\Users\<you>\Projects\cv-search-poc> $env:STREAMLIT_AUTH_REDIRECT_URI = "http://localhost:8501/oauth2callback"
PS C:\Users\<you>\Projects\cv-search-poc> python scripts\generate_secrets_toml.py
PS C:\Users\<you>\Projects\cv-search-poc> .\.venv\Scripts\python -m streamlit run app.py
```

If `.streamlit/secrets.toml` already exists, the script will leave it unchanged. Delete the file to regenerate it.

---

## REST API (FastAPI)

The project includes a FastAPI-based REST API for chatbot and programmatic integration.

### Running the API Server

```powershell
# Development (with auto-reload)
PS C:\Users\<you>\Projects\cv-search-poc> uv run uvicorn cv_search.api.main:app --reload --port 8000

# Production (multi-worker)
PS C:\Users\<you>\Projects\cv-search-poc> uv run uvicorn cv_search.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks DB) |
| GET | `/docs` | Swagger UI documentation |
| POST | `/api/v1/search/seat` | Single-seat candidate search |
| POST | `/api/v1/search/project` | Multi-seat project search |
| POST | `/api/v1/search/presale` | Presale team search |
| POST | `/api/v1/planner/parse-brief` | Parse NL brief → Criteria |
| POST | `/api/v1/planner/derive-seats` | Derive project seats |
| POST | `/api/v1/planner/presale-plan` | Generate presale team plan |
| GET | `/api/v1/runs/` | List recent search runs |
| GET | `/api/v1/runs/{run_id}` | Get run details |
| POST | `/api/v1/runs/{run_id}/feedback` | Submit feedback |

### Example Requests

```powershell
# Single-seat search
curl -X POST http://localhost:8000/api/v1/search/seat `
  -H "Content-Type: application/json" `
  -H "X-API-Key: your-key" `
  -d '{"criteria": {"team_size": {"members": [{"role": "backend developer", "seniority": "senior", "tech_tags": ["python", "fastapi"]}]}}, "top_k": 3}'

# Project search from brief
curl -X POST http://localhost:8000/api/v1/search/project `
  -H "Content-Type: application/json" `
  -H "X-API-Key: your-key" `
  -d '{"text": "Need 2 Python developers and 1 React frontend", "top_k": 3}'
```

All search endpoints accept an optional `include_cv_markdown` parameter (default: `false`). Set to `true` to include full CV markdown in results (adds ~3-5KB per candidate). The presale endpoint also accepts `include_extended` (default: `false`) to include extended team roles in the search.

### Project Search Response

`POST /api/v1/search/project` returns a `ProjectSearchResponse` with the following structure:

**Top-level fields:**

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `string` | Unique UUID for this search run. Can be used to retrieve run details via `/api/v1/runs/{run_id}`. |
| `status` | `string` | Search outcome: `"ok"` (success), `"skipped"` (brief too vague or no seats derived), or `"failed"` (error). |
| `criteria` | `object` | The derived project criteria parsed from the natural language brief (see Criteria below). |
| `seats` | `SeatResult[]` | Results per seat/role. Each seat contains ranked candidates (see SeatResult below). |
| `gaps` | `int[]` | Seat indices where **no candidates were found**. Empty array means all seats were filled. |
| `note` | `string\|null` | User-facing message for edge cases (e.g. `"This brief is too broad..."`). `null` on success. |
| `reason` | `string\|null` | Machine-readable status code: `"low_signal_brief"`, `"no_seats_derived"`. `null` when `status` is `"ok"`. |

**Criteria object** (`criteria`):

| Field | Type | Description |
|-------|------|-------------|
| `domain` | `string[]` | Domain areas extracted from the brief (e.g. `["cloud_platforms"]`). |
| `tech_stack` | `string[]` | Technologies extracted from the brief (e.g. `["dotnet", "azure", "react"]`). |
| `expert_roles` | `string[]` | Distinct roles needed (e.g. `["backend_engineer", "frontend_engineer"]`). |
| `project_type` | `string\|null` | Project type if detected (e.g. `"greenfield"`), otherwise `null`. |
| `team_size.total` | `int` | Number of distinct roles (seats). |
| `team_size.members` | `object[]` | Seat definitions, each with `role`, `seniority`, `domains`, `tech_tags`, `nice_to_have`, `rationale`. |

**SeatResult** (each item in `seats`):

| Field | Type | Description |
|-------|------|-------------|
| `seat_index` | `int` | Zero-based index of this seat. |
| `role` | `string` | Role being searched (e.g. `"backend_engineer"`). |
| `seniority` | `string\|null` | Required seniority from the criteria (e.g. `"senior"`, `"middle"`). |
| `results` | `CandidateResult[]` | Ranked candidates for this seat (up to `top_k`). |
| `metrics` | `object` | Search execution metrics (see Metrics below). |
| `gap` | `bool` | `true` if no candidates were found for this seat. |

**SearchMetrics** (per-seat `metrics`):

| Field | Type | Description |
|-------|------|-------------|
| `gate_count` | `int` | Number of candidates that passed the gating filter (role + seniority match). |
| `lex_fanin` | `int` | Number of candidates scored by the lexical retriever. |
| `pool_size` | `int` | Number of candidates sent to the LLM for final ranking. |
| `mode` | `string` | Search mode used (always `"llm"`). |
| `duration_ms` | `int` | Wall-clock duration of the seat search in milliseconds (includes LLM calls). |

**CandidateResult** (each item in seat `results`):

| Field | Type | Description |
|-------|------|-------------|
| `candidate_id` | `string` | Unique candidate identifier (e.g. `"pptx-c73a6d8877"`). |
| `name` | `string\|null` | Candidate display name. |
| `source_file` | `string\|null` | Google Drive path or filename of the source CV. |
| `cv_markdown` | `string\|null` | Full CV rendered as Markdown (~3-5KB). `null` when `include_cv_markdown` is `false`. |
| `score` | `object` | `{ "value": 0.95, "order": 1 }` — LLM match score (0-1) and rank within the seat. |
| `must_have` | `object` | Map of must-have tech tags to match status (e.g. `{ "dotnet": true, "azure": true }`). |
| `nice_to_have` | `object` | Map of nice-to-have tags to match status. |
| `recency` | `object` | `{ "last_updated": "2025-10-14T05:57:00" }` — when the CV was last updated. |
| `llm_justification` | `object\|null` | LLM-generated verdict (see below). |
| `score_components` | `object\|null` | Detailed scoring breakdown (lexical scores, IDF coverage, LLM rank — for debugging). |

**LLM Justification** (`llm_justification`):

| Field | Type | Description |
|-------|------|-------------|
| `match_summary` | `string` | One-line summary of match quality. |
| `strength_analysis` | `string[]` | List of candidate strengths relevant to the role. |
| `gap_analysis` | `string[]` | List of gaps or concerns. |
| `overall_match_score` | `float` | LLM-assigned score (0-1), same as `score.value`. |

### Presale Search Response

`POST /api/v1/search/presale` returns a `PresaleSearchResponse`. It shares the same `SeatResult`, `CandidateResult`, `SearchMetrics`, and `seats` structure as the project search, plus a `presale_rationale` field:

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `string` | Unique UUID for this search run. |
| `status` | `string` | `"ok"`, `"skipped"`, or `"failed"`. |
| `criteria` | `object` | Full presale criteria including `minimum_team`, `extended_team`, `presale_rationale`, and the original parsed `team_size`. |
| `seats` | `SeatResult[]` | Results per seat (same structure as project search). |
| `gaps` | `int[]` | Seat indices where no candidates were found. |
| `presale_rationale` | `string\|null` | LLM-generated explanation for why these roles were chosen. |
| `note` | `string\|null` | User-facing message for edge cases. `null` on success. |
| `reason` | `string\|null` | Machine-readable status code. `null` when `status` is `"ok"`. |

### Authentication

Optional API key authentication can be enabled by setting `API_KEY` in `.env`:

```
API_KEY=your-secret-key
```

When set, all requests must include the `X-API-Key` header. In Swagger UI (`/docs`), click the **Authorize** button at the top to enter your key once — it will be sent automatically with all subsequent requests.

### Logging

The API uses structured Python logging with request IDs and duration tracking. Configure via `LOG_LEVEL` env var (default: `INFO`). In Docker, logs use `json-file` driver with rotation. View with:

```bash
docker compose logs api --tail 200
docker compose logs api --since 1h
```

### Version Badge

The Swagger UI (`/docs`) and `/health` endpoint both display the current git commit hash in the version string (e.g. `1.0.0-a3f8c2d`). This makes it easy to confirm which code is deployed.

How it works:
- **Local dev:** the API calls `git rev-parse --short HEAD` at startup
- **Docker deploy:** `deploy.ps1` writes a `BUILD_COMMIT` file before zipping, `deploy-vm.sh` passes it as a `--build-arg` to Docker, and the Dockerfile bakes it into the image
- **Fallback:** if neither git nor `BUILD_COMMIT` is available, the version shows `1.0.0-dev`

```bash
# Check deployed version
curl -s http://<host>:8000/health | jq .version
# "1.0.0-a3f8c2d"
```

---

## Testing

Use the dedicated `.env.test` so integration runs stay isolated from your dev data:

```powershell
# Start Postgres if not already running
PS C:\Users\<you>\Projects\cv-search-poc> docker compose -f docker/docker-compose.pg.yml up -d

# Run unit tests
PS C:\Users\<you>\Projects\cv-search-poc> uv run pytest tests\unit -q

# Run integration suite with test env vars
PS C:\Users\<you>\Projects\cv-search-poc> uv run python -m dotenv -f .env.test run -- pytest tests\integration -q
```

The `.env.test` defaults to `cvsearch_test` so test data stays isolated from `DB_URL` in your main `.env`.

---

## Production Deployment (Azure VM)

Deploy the API as a Docker Compose stack (Postgres 16 + FastAPI) on an Azure VM with Azure OpenAI.

### Prerequisites

- An Azure account ([free tier](https://azure.microsoft.com/free) gives $200 credit for 30 days)
- Azure CLI installed locally:

```powershell
# Windows (winget)
winget install Microsoft.AzureCLI

# macOS
brew install azure-cli

# Then log in
az login
```

### 1. Create Resource Group

All resources will live in one resource group for easy cleanup.

```bash
az group create --name cvsearch-rg --location eastus
```

### 2. Register Required Resource Providers

First-time Azure subscriptions need resource providers registered (one-time step):

```bash
# Register providers (takes ~1-2 minutes each)
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.Compute

# Wait until both show "Registered"
az provider show -n Microsoft.CognitiveServices --query registrationState -o tsv
az provider show -n Microsoft.Compute --query registrationState -o tsv
```

### 3. Azure OpenAI Resource

The app needs an Azure OpenAI endpoint for LLM ranking and brief parsing.

**Option A — Use an existing resource** (e.g. another tenant):

You just need three values for step 5:
- **Endpoint:** `https://<resource-name>.openai.azure.com/`
- **API Key:** the key for that resource
- **Deployment name:** the model deployment name (e.g. `gpt-4-1-mini`)

**Option B — Create a new resource in this subscription:**

```bash
# Create the Cognitive Services (OpenAI) account
az cognitiveservices account create \
  --name cvsearch-openai \
  --resource-group cvsearch-rg \
  --location eastus \
  --kind OpenAI \
  --sku S0

# Deploy gpt-4.1-mini model
az cognitiveservices account deployment create \
  --name cvsearch-openai \
  --resource-group cvsearch-rg \
  --deployment-name gpt-4-1-mini \
  --model-name gpt-4.1-mini \
  --model-version "2025-04-14" \
  --model-format OpenAI \
  --sku-name GlobalStandard \
  --sku-capacity 10

# Retrieve endpoint and key (save these for step 5)
az cognitiveservices account show \
  --name cvsearch-openai \
  --resource-group cvsearch-rg \
  --query properties.endpoint -o tsv

az cognitiveservices account keys list \
  --name cvsearch-openai \
  --resource-group cvsearch-rg \
  --query key1 -o tsv
```

### 4. Create Azure VM

**Option A — Via Azure Portal** (recommended if B-series VMs are unavailable via CLI):

1. Portal → Virtual machines → Create → Azure virtual machine
2. Resource group: `cvsearch-rg`, Name: `cvsearch-vm`, Region: `East US`
3. Image: **Ubuntu Server 22.04 LTS** by **Canonical** (make sure publisher is Canonical, not a paid marketplace image)
4. Size: `Standard_DC2as_v5` (2 vCPU, 8 GB) or larger
5. **Security type: Standard** (change from default "Trusted launch" — DC-series does not support Trusted launch)
6. Authentication: SSH public key, Username: `azureuser`
7. Inbound ports: Allow SSH (22)
8. Review + Create → Create
9. After deployment: VM → Networking → Add inbound port rule → Port **8000**, Allow

**Option B — Via CLI** (if `Standard_B2s` is available in your region):

```bash
az vm create \
  --resource-group cvsearch-rg \
  --name cvsearch-vm \
  --image Canonical:ubuntu-22_04-lts:server:latest \
  --size Standard_B2s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard

# Open API port
az vm open-port --resource-group cvsearch-rg --name cvsearch-vm --port 8000
```

> **Troubleshooting:** If you get `SkuNotAvailable` errors, your subscription may not have
> B/D-series quota. Check available sizes with:
> `az vm list-skus --location eastus --resource-type virtualMachines --query "[?restrictions==null || restrictions==``[]``].{Name:name, vCPUs:capabilities[?name=='vCPUs'].value|[0], Mem:capabilities[?name=='MemoryGB'].value|[0]}" -o table`
> Then use the portal (Option A) with a DC-series size and **Security type: Standard**.

Note the **publicIpAddress** from the VM overview page or CLI output.

### 5. Prepare Secrets

```powershell
Copy-Item .env.production.example .env.production
```

Fill in `.env.production` with the values from step 3:

```env
DB_USER=cvsearch
DB_PASSWORD=<strong-random-password>
DB_NAME=cvsearch
DB_PORT=5433

USE_AZURE_OPENAI=true
OPENAI_API_KEY=<key from step 3>
AZURE_ENDPOINT=<endpoint from step 3>
AZURE_API_VERSION=2024-12-01-preview
OPENAI_MODEL=gpt-4-1-mini

API_PORT=8000
API_KEY=<strong-random-api-secret>
API_CORS_ORIGINS=*
```

### 6. Deploy

Get the VM public IP from the Azure Portal (VM → Overview → Public IP address) or via CLI:

```bash
az vm show -d -g cvsearch-rg -n cvsearch-vm --query publicIps -o tsv
```

**6a. Create deployment zip** (from your local project root in PowerShell):

```powershell
Compress-Archive -Path src, data, scripts, docker, Dockerfile, .dockerignore, docker-compose.yml, pyproject.toml, api_server.py, .env.production, main.py, README.md -DestinationPath cv-search-poc.zip
```

**6b. Upload zip to the VM** (use the `.pem` key downloaded during VM creation):

```powershell
scp -i "$HOME\Downloads\cvsearch-vm_key.pem" cv-search-poc.zip azureuser@<VM_IP>:/home/azureuser/
```

**6c. SSH into the VM and deploy:**

```powershell
ssh -i "$HOME\Downloads\cvsearch-vm_key.pem" azureuser@<VM_IP>
```

Then on the VM:

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq unzip
unzip -o ~/cv-search-poc.zip -d ~/cv-search-poc
cd ~/cv-search-poc && sudo bash scripts/deploy-vm.sh
```

The script installs Docker, copies files to `/opt/cvsearch`, builds the image, starts Postgres + API, initializes the DB schema, and verifies health.

### 7. Verify

```bash
curl http://$VM_IP:8000/health
curl http://$VM_IP:8000/ready
# Swagger UI: http://$VM_IP:8000/docs
```

### 8. Restore Data (from backup)

If you have a `pg_dump` backup, restore it to populate the database with candidates.

**Upload the backup to the VM:**

```powershell
scp -i "$HOME\Downloads\cvsearch-vm_key.pem" backup.sql azureuser@<VM_IP>:/home/azureuser/
```

**Restore on the VM:**

```bash
ssh -i "$HOME/Downloads/cvsearch-vm_key.pem" azureuser@<VM_IP>
sudo docker compose -f /opt/cvsearch/docker-compose.yml exec -T postgres \
  psql -U cvsearch -d cvsearch < ~/backup.sql
```

**Verify data:**

```bash
curl http://<VM_IP>:8000/ready

sudo docker compose -f /opt/cvsearch/docker-compose.yml exec postgres \
  psql -U cvsearch -d cvsearch -c "SELECT COUNT(*) FROM candidate;"
```

**Creating new backups (from the VM):**

```bash
sudo docker compose -f /opt/cvsearch/docker-compose.yml exec postgres \
  pg_dump -U cvsearch --clean --if-exists cvsearch > backup_$(date +%Y%m%d).sql
```

### Cleanup

To tear down all Azure resources when no longer needed:

```bash
az group delete --name cvsearch-rg --yes --no-wait
```

### Deployment Files

| File | Role |
|------|------|
| `Dockerfile` | Builds API image (Python 3.11-slim, Uvicorn 4 workers) |
| `docker-compose.yml` | Orchestrates Postgres 16 + API with health checks, log rotation, volume mounts |
| `.dockerignore` | Excludes dev/test files from image |
| `.env.production.example` | Secrets template |
| `scripts/deploy.ps1` | One-step Windows deploy: zip → scp → deploy-vm.sh |
| `scripts/deploy-vm.sh` | Automated Ubuntu deployment script |
| `scripts/migrate_drop_vector.sql` | Legacy cleanup (only if DB had pgvector) |

### Estimated Cost

| Resource | SKU | ~Cost/mo |
|----------|-----|----------|
| VM (Standard_B2s) | 2 vCPU, 4 GB RAM | ~$30 |
| VM (Standard_DC2as_v5) | 2 vCPU, 8 GB RAM (if B-series unavailable) | ~$140 |
| OS Disk | 30 GB Standard SSD | ~$5 |
| Public IP | Standard static | ~$3 |
| Azure OpenAI | S0 + gpt-4.1-mini | Pay-per-token |
| **Total (infra)** | | **~$38–148 + tokens** |