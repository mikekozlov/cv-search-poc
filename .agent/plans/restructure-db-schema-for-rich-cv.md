# Restructure CV storage for detailed PPTX ingestion

This ExecPlan is a living document. Maintain it according to .agent/PLANS.md and keep it self-contained for a novice contributor.

## Purpose / Big Picture

The current ingestion loses responsibilities/project descriptions from PPTX CVs and flattens rich sections into limited tags. After this change, a user can ingest a PPTX like the provided sample and then query Postgres to see contact info, qualifications, project descriptions, responsibilities (as bullet text), technologies, domains, and embeddings that include those details. Searches and filters should be able to use these richer fields.

## Progress

- [x] (2025-12-03 12:45Z) Drafted ExecPlan after reviewing current schema, ingestion, and PPTX-to-JSON output for pptx-27ebd91cce.
- [x] (2025-12-03 13:10Z) Added schema changes (project_description, responsibilities_text, candidate_qualification) with ALTER safety.
- [x] (2025-12-03 13:25Z) Updated LLM contract/fixtures and ingestion to persist responsibilities, project descriptions, qualifications; added env-based deterministic embedder fallback.
- [x] (2025-12-03 13:35Z) Added integration assertions for responsibilities/qualifications and ran `python -m pytest tests\integration -q` with offline flags.

## Surprises & Discoveries

- Existing test DBs retained old schema; added ALTER statements to schema_pg.sql/schema.sql so initialize_schema upgrades columns.
- LocalEmbedder tried to hit HuggingFace during CLI ingest; added env-controlled DeterministicEmbedder fallback to keep tests offline.

## Decision Log

- Decision: Treat responsibilities as first-class per-experience text (multi-line) rather than dropping them or forcing them into highlights. Rationale: PPTX samples supply rich bullet lists that must be queryable and should influence embeddings. Date/Author: 2025-12-03 / assistant.
- Decision: Add candidate_qualification table (category + item) and include qualification tokens in tags_text/embeddings while keeping canonical tags intact. Rationale: Preserve grouped skill sections for search without overloading tag tables. Date/Author: 2025-12-03 / assistant.
- Decision: Prefer deterministic embedder when USE_DETERMINISTIC_EMBEDDER or HF_HUB_OFFLINE is set, including ingestion flows, to avoid network downloads in tests/CI. Date/Author: 2025-12-03 / assistant.
- Decision: Drop contact_email and period_text from scope to keep schema lean and avoid storing extra PII/date text; rely on description/responsibilities for experience detail. Date/Author: 2025-12-03 / assistant.

## Outcomes & Retrospective

Responsibilities/project descriptions now persist to Postgres and feed embeddings/FTS; qualifications and contact_email are stored. Integration suite passes offline with deterministic embedder. Future work: consider explicit backfill for existing prod data and richer period parsing.

## Context and Orientation

Current storage lives in Postgres (schema in src/cv_search/db/schema_pg.sql) with tables: candidate, candidate_tag, experience, experience_tag, candidate_doc (vector + tsv). Ingestion (`src/cv_search/ingestion/pipeline.py` and `async_pipeline.py`) builds `summary_text`, `experience_text`, `tags_text`; embeddings come from concatenated header + tags + summary + experience_text. Responsibilities from the LLM JSON land in `experience.description` in the JSON but are discarded because the pipeline only stores `experience.highlights`. Contact info (email) and grouped qualifications are absent from the schema. Lexicons live under data/lexicons; structured CVs are saved to data/ingested_cvs_json for debugging. Tests use `uv run pytest tests\integration -q` after setting env vars and running docker-compose.pg.yml.

## Plan of Work

Describe the DB and ingestion redesign end-to-end, ensuring a novice can follow. First, design a richer schema: add contact fields (email), a qualifications table or structured skill buckets (languages, databases, tools), and extend experience to include project_description and responsibilities_text (as array or newline-joined text). Keep canonical tag tables for search but also store raw sections for fidelity. Add migrations to schema_pg.sql and ensure CVDatabase supports the new columns/tables. Next, update the LLM structured CV prompt/contract to emit responsibilities as a list (not just description) and qualifications grouped per the PPTX sample; ensure Stub backend/test fixtures are updated. Modify ingestion pipeline to map new JSON fields into the DB: upsert contact info into candidate, persist project_description and responsibilities per experience, populate new skill tables, and include these fields in `candidate_doc` text/embedding. Update search/ranking layers if they rely on specific fields, ensuring embeddings include responsibilities/project descriptions. Plan data migration/backfill: either re-ingest from raw files or write a one-time SQL update to copy legacy highlights into responsibilities where missing. Document how to rerun ingestion idempotently. Finally, add tests (unit + integration) to cover new schema, ingestion mapping, and retrieval of responsibilities/qualifications; run the full integration suite.

## Concrete Steps

1) Design schema changes and write migrations: update src/cv_search/db/schema_pg.sql (and schema.sql if still used in tests) to add new columns/tables; update CVDatabase to read/write them. 2) Adjust structured CV contract in src/cv_search/clients/openai_client.py (Live and Stub) to emit project_description, responsibilities (list), and grouped qualifications. Update fixtures in data/test/mock_cvs.json or stub files as needed. 3) Update ingestion pipeline modules to persist new fields and build candidate_doc text/embedding with project descriptions and responsibilities. 4) Update search/indexing logic if it assumes old fields; ensure vector dims unchanged. 5) Provide migration/backfill guidance. Commands to run during implementation (from repo root):  
    PS C:\Users\mykha\Projects\cv-search-poc> docker compose -f docker-compose.pg.yml up -d  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DB_URL = "postgresql://cvsearch:cvsearch@localhost:5433/cvsearch_test"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:RUNS_DIR = "data/test/tmp/runs"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:DATA_DIR = "data/test"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:GDRIVE_LOCAL_DEST_DIR = "data/test/gdrive_inbox"  
    PS C:\Users\mykha\Projects\cv-search-poc> $env:OPENAI_API_KEY = "test-key"  
    PS C:\Users\mykha\Projects\cv-search-poc> uv run pytest tests\integration -q

## Validation and Acceptance

Acceptance hinges on behavior: after ingesting the provided PPTX, querying Postgres should show (a) candidate.email populated, (b) each experience row with project_description and responsibilities text/bullets retained, (c) technologies and domains mapped to tags, and (d) candidate_doc embedding and tsv include responsibilities/project descriptions. Example verification in psql:  
    select project_description, responsibilities_text, tech_tags_csv from experience where candidate_id = '<id>';  
    select summary_text, experience_text from candidate_doc where candidate_id = '<id>';  
    select * from qualifications where candidate_id = '<id>' (or equivalent table once defined).  
Tests: run `uv run pytest tests\integration -q` and ensure added tests for responsibilities/qualifications pass and fail on old schema.

## Idempotence and Recovery

Migrations must be repeatable and safe; upserts should remain idempotent. Re-ingestion should overwrite a candidate cleanly (remove derived rows first). Document rollback: if migration fails mid-way, restore from backup or drop/recreate the test DB via docker-compose and rerun initialize_schema. Ensure new fields have defaults or nullable settings to avoid breaking existing rows.

## Artifacts and Notes

Keep short evidence snippets once implemented, such as a sample psql output showing responsibilities text and a candidate_doc excerpt that includes project descriptions. Include any migration notes (e.g., how legacy highlights were copied into responsibilities when absent).

## Interfaces and Dependencies

Specify expected interfaces once implemented: CVDatabase.upsert_candidate should accept email; upsert_candidate_doc should include new concatenated text that covers responsibilities/project descriptions. Experience records should store project_description text and responsibilities_text (newline-joined or JSON array); consider an experience_responsibility table if normalization is chosen. Structured CV output should include fields: contact_email, qualifications grouped (languages, databases, tools/other), experiences[*].project_description, experiences[*].responsibilities (list of strings), experiences[*].technologies (canonical tags), and period/start/end metadata. Ensure pgvector remains on candidate_doc.embedding (dim 384); update any search path that consumes experience_text to include responsibilities.
