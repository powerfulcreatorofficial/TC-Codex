-- Phase 8: persistent project registry and task/project association.
-- Project metadata is non-secret; workspace paths are logical relative paths.

CREATE TABLE IF NOT EXISTS tc_projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    workspace_path TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tc_projects_updated_at_idx ON tc_projects (updated_at DESC);

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS project_id TEXT REFERENCES tc_projects(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS tasks_project_id_idx ON tasks (project_id);
