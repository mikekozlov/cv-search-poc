# cv-search

This repo provides a simple CV search POC with a CLI and a small Streamlit UI.

Installation and usage now use uv for dependency management and running.

## Install and setup (uv)

1. Install uv (if you don't have it):
   - macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh
   - Windows (PowerShell): iwr https://astral.sh/uv/install.ps1 -UseBasicParsing | iex
2. Create a virtual environment and install dependencies:
   - uv venv
   - source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   - uv sync
3. Create/update your .env with your OpenAI API key:
   - OPENAI_API_KEY=sk-proj-*****************

## Initialize data

- Init DB (if not done yet):
  - uv run cv_search init-db
- Ingest mock CVs (local DB + vector store upsert):
  - uv run cv_search ingest-mock

## Run the UI

- uv run app

## CLI examples

- Parse request:
  - uv run cv_search parse-request
- Search seat:
  - uv run cv_search search-seat
- Search (hybrid by default) with explicit criteria:
  - uv run cv_search search-seat --criteria ./criteria.json --topk 2

## Presale / Project flows

1) Presale — roles only (budget ignored):
   - uv run cv_search presale-plan --text "Mobile + web app with Flutter/React; AI chatbot for goal setting; partner marks failures; donation on failure."

2) Project phase — free text → seats → per-seat shortlists:
   - uv run cv_search project-search --db ./cvsearch.db --text "Mobile+web app in Flutter/React; AI chatbot; partner marks failures; donation on failure." --topk 3

3) Or, with explicit canonical criteria (JSON):
   - uv run cv_search project-search --criteria ./criteria.json --topk 3



