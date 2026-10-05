-- Phase 7: auditable deterministic self-improvement memory.
-- Lessons contain only task-derived evidence; no credentials or raw owner tokens.

CREATE TABLE IF NOT EXISTS tc_learnings (
    id          BIGSERIAL PRIMARY KEY,
    task_id     TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    lesson      TEXT NOT NULL,
    evidence    TEXT NOT NULL,
    score       INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tc_learnings_created_at_idx ON tc_learnings (created_at DESC);
CREATE INDEX IF NOT EXISTS tc_learnings_category_idx ON tc_learnings (category);
