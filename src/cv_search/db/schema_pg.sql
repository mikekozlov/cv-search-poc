CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS candidate (
    candidate_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT,
    seniority TEXT,
    last_updated TEXT,
    source_filename TEXT,
    source_gdrive_path TEXT,
    source_category TEXT,
    source_folder_role_hint TEXT
);

CREATE TABLE IF NOT EXISTS candidate_tag (
    candidate_id TEXT NOT NULL REFERENCES candidate(candidate_id) ON DELETE CASCADE,
    tag_type TEXT NOT NULL,
    tag_key TEXT NOT NULL,
    weight DOUBLE PRECISION DEFAULT 1.0,
    PRIMARY KEY (candidate_id, tag_type, tag_key)
);

CREATE INDEX IF NOT EXISTS idx_candidate_tag_type_key ON candidate_tag(tag_type, tag_key);
CREATE INDEX IF NOT EXISTS idx_candidate_tag_candidate ON candidate_tag(candidate_id);

CREATE TABLE IF NOT EXISTS experience (
    id BIGSERIAL PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidate(candidate_id) ON DELETE CASCADE,
    title TEXT,
    company TEXT,
    start TEXT,
    "end" TEXT,
    project_description TEXT,
    responsibilities_text TEXT,
    domain_tags_csv TEXT,
    tech_tags_csv TEXT,
    highlights TEXT
);

CREATE TABLE IF NOT EXISTS experience_tag (
    experience_id BIGINT NOT NULL REFERENCES experience(id) ON DELETE CASCADE,
    tag_type TEXT NOT NULL,
    tag_key TEXT NOT NULL,
    PRIMARY KEY (experience_id, tag_type, tag_key)
);

CREATE INDEX IF NOT EXISTS idx_experience_candidate ON experience(candidate_id);

CREATE TABLE IF NOT EXISTS candidate_doc (
    candidate_id TEXT PRIMARY KEY REFERENCES candidate(candidate_id) ON DELETE CASCADE,
    summary_text TEXT,
    experience_text TEXT,
    tags_text TEXT,
    embedding VECTOR(384),
    tsv_document tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(summary_text, '')), 'A')
        || setweight(to_tsvector('english', coalesce(experience_text, '')), 'B')
        || setweight(to_tsvector('english', coalesce(tags_text, '')), 'C')
    ) STORED,
    last_updated TEXT,
    location TEXT,
    seniority TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidate_doc_embedding ON candidate_doc USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_candidate_doc_tsv ON candidate_doc USING GIN (tsv_document);

CREATE TABLE IF NOT EXISTS candidate_qualification (
    candidate_id TEXT NOT NULL REFERENCES candidate(candidate_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    item TEXT NOT NULL,
    weight DOUBLE PRECISION DEFAULT 1.0,
    PRIMARY KEY (candidate_id, category, item)
);

CREATE INDEX IF NOT EXISTS idx_candidate_qualification_candidate ON candidate_qualification(candidate_id);

ALTER TABLE experience ADD COLUMN IF NOT EXISTS project_description TEXT;
ALTER TABLE experience ADD COLUMN IF NOT EXISTS responsibilities_text TEXT;
