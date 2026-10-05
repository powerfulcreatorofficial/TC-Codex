-- Step 4 migration 0001: core task + event + approval schema.
-- All stored metadata is redacted by the orchestrator before write; this
-- schema never holds raw secrets, API keys, or credentials.

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    prompt          TEXT NOT NULL,
    status          TEXT NOT NULL,
    answer          TEXT,
    error           TEXT,
    current_step    INTEGER NOT NULL DEFAULT 0,
    max_steps       INTEGER NOT NULL DEFAULT 20,
    owner_token_hash TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Index for status queries (e.g. AWAITING_APPROVAL dashboards).
    CONSTRAINT tasks_status_chk CHECK (
        status IN ('PENDING','RUNNING','AWAITING_APPROVAL','COMPLETED','FAILED')
    )
);

CREATE INDEX IF NOT EXISTS tasks_status_idx ON tasks (status);
CREATE INDEX IF NOT EXISTS tasks_created_at_idx ON tasks (created_at);

-- Append-only event/history log for a task.
CREATE TABLE IF NOT EXISTS task_events (
    id                BIGSERIAL PRIMARY KEY,
    task_id           TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type        TEXT NOT NULL,
    tool_name         TEXT,
    -- Redacted, safe-to-store argument summary (no secrets).
    arguments_metadata JSONB,
    -- Redacted, safe-to-store result summary (no secrets).
    result_metadata   JSONB,
    status            TEXT,
    -- Nonce linking an approval event to the exact pending action.
    approval_nonce    TEXT
);

CREATE INDEX IF NOT EXISTS task_events_task_id_idx ON task_events (task_id, ts);

-- Pending and decided approvals. Nonces are single-use.
CREATE TABLE IF NOT EXISTS task_approvals (
    id                BIGSERIAL PRIMARY KEY,
    task_id           TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tool_name         TEXT NOT NULL,
    -- Redacted argument summary shown to the approver (no secrets).
    arguments_metadata JSONB NOT NULL,
    risk_level        TEXT NOT NULL,
    nonce             TEXT NOT NULL UNIQUE,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at        TIMESTAMPTZ,
    decided_by        TEXT,
    expires_at        TIMESTAMPTZ NOT NULL,
    CONSTRAINT approvals_status_chk CHECK (status IN ('pending','approved','rejected','expired','consumed'))
);

CREATE INDEX IF NOT EXISTS task_approvals_task_idx ON task_approvals (task_id);
CREATE INDEX IF NOT EXISTS task_approvals_nonce_idx ON task_approvals (nonce);
CREATE INDEX IF NOT EXISTS task_approvals_status_idx ON task_approvals (status);
