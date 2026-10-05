-- Phase 11: structured planning and explicit plan approval.
CREATE TABLE IF NOT EXISTS tc_plans (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    project_id TEXT REFERENCES tc_projects(id) ON DELETE SET NULL,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    acceptance_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
    risks JSONB NOT NULL DEFAULT '[]'::jsonb,
    owner_token_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tc_plans_project_id_idx ON tc_plans (project_id);
CREATE INDEX IF NOT EXISTS tc_plans_updated_at_idx ON tc_plans (updated_at DESC);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS plan_id TEXT REFERENCES tc_plans(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS tasks_plan_id_idx ON tasks (plan_id);
