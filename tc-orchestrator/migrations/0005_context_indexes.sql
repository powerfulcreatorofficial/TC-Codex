-- Phase 14: indexes for bounded project context retrieval.
CREATE INDEX IF NOT EXISTS tasks_project_updated_idx
    ON tasks (project_id, updated_at DESC)
    WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS tc_learning_created_idx
    ON tc_learnings (created_at DESC);
