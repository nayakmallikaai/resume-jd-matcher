-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Main resume table: one row per resume
CREATE TABLE IF NOT EXISTS resumes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    email           TEXT,
    seniority       TEXT,          -- junior | mid | senior | staff | principal | executive
    total_years     INTEGER,
    location        TEXT,
    open_to_remote  BOOLEAN,
    employment_type TEXT,          -- full-time | part-time | contract | freelance
    summary         TEXT,
    key_topics      TEXT[],
    raw_text        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Experience chunks table: one row per job, linked to resume
CREATE TABLE IF NOT EXISTS experience_chunks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    resume_id   UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    company     TEXT,
    title       TEXT,
    duration    TEXT,
    chunk_text  TEXT NOT NULL,
    embedding   vector(384),   -- all-MiniLM-L6-v2 produces 384-dim vectors
    position    INTEGER,       -- order of appearance in the resume (0-indexed)
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- IVFFlat index for approximate nearest-neighbor search on embeddings
-- Tune `lists` to roughly sqrt(number of rows) once the table is populated
CREATE INDEX IF NOT EXISTS idx_experience_embedding
    ON experience_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
