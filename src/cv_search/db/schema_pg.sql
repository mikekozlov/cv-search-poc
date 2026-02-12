CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS search_run (
    run_id TEXT PRIMARY KEY,
    run_kind TEXT NOT NULL,
    run_dir TEXT,
    user_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'running',
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    result_count INTEGER,
    error_type TEXT,
    error_message TEXT,
    error_stage TEXT,
    error_traceback TEXT,
    criteria_json TEXT,
    raw_text TEXT,
    top_k INTEGER,
    seat_count INTEGER,
    note TEXT,
    feedback_sentiment TEXT CHECK (feedback_sentiment IN ('like','dislike')),
    feedback_comment TEXT,
    feedback_submitted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_search_run_created_at ON search_run(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_run_feedback_at ON search_run(feedback_submitted_at);

ALTER TABLE search_run ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'running';
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS duration_ms INTEGER;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS result_count INTEGER;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS error_type TEXT;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS error_stage TEXT;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS error_traceback TEXT;
ALTER TABLE search_run ADD COLUMN IF NOT EXISTS user_email TEXT;

CREATE TABLE IF NOT EXISTS candidate (
    candidate_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
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
    tech_tags_csv TEXT
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
    tsv_document tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(summary_text, '')), 'A')
        || setweight(to_tsvector('english', coalesce(experience_text, '')), 'B')
        || setweight(to_tsvector('english', coalesce(tags_text, '')), 'C')
    ) STORED,
    last_updated TEXT,
    seniority TEXT
);

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
ALTER TABLE candidate DROP COLUMN IF EXISTS location;
ALTER TABLE experience DROP COLUMN IF EXISTS highlights;
ALTER TABLE candidate_doc DROP COLUMN IF EXISTS location;
