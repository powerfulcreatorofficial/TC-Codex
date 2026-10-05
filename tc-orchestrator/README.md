# tc-orchestrator

Engineering TC v0.1 — **Step 3: MCP Orchestrator + Brain tool-call loop.**

A minimal but genuinely functional Python orchestrator that drives an
OpenAI-compatible Brain through a bounded tool-call loop, executing each tool
through the Step 2 **Workspace Daemon** (gRPC) and redacting secrets before
anything reaches the Brain.

```
Creator prompt
      ↓
Orchestrator  ──►  Brain (OpenAI-compatible Chat Completions)
      │                 │
      │ ◄ structured tool call
      │
Tool validation (registry + Pydantic + path checks)
      ↓
Workspace Daemon (gRPC, the security boundary)
      ↓
Redacted tool result
      ↓
Brain  ──►  next tool call / final answer   (repeat, bounded)
```

## Architecture

| Module | Responsibility |
|---|---|
| `config.py` | Env-driven settings (Brain + daemon + loop bound). |
| `models.py` | Pydantic models: chat messages, tool calls/results, tasks. |
| `brain.py` | OpenAI-compatible client (`httpx`) + `MockBrain`/`RepeatingToolBrain` for tests. |
| `tool_registry.py` | Authoritative tool allowlist: name, schema, permission, read-only, handler. |
| `tool_router.py` | Validate name + args (Pydantic) + path checks; dispatch via `WorkspaceClient`. |
| `grpc_client.py` | `WorkspaceClient` — the **only** path to the workspace (gRPC). |
| `redaction.py` | Orchestrator-side redaction (literal env secrets + token regexes). |
| `orchestrator.py` | The bounded agent loop (max steps, repeated-call detection). |
| `task_store.py` | In-memory task store (replaceable with PostgreSQL later). |
| `api.py` | FastAPI: `GET /health`, `POST /v1/tasks`, `GET /v1/tasks/{id}`. |
| `main.py` | Uvicorn entrypoint. |
| `proto_gen/` | Generated Python gRPC stubs for the Workspace Daemon. |

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `BRAIN_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible base URL. |
| `BRAIN_API_KEY` | (none) | API key for the Brain. **Never logged / never in message body.** |
| `BRAIN_MODEL` | `qwen/qwen-2.5-72b-instruct` | Model id. |
| `TC_DAEMON_ADDR` | `127.0.0.1:50051` | Workspace Daemon gRPC endpoint. |
| `MAX_AGENT_STEPS` | `20` | Bound on the agent loop. |
| `TC_ORCH_HOST` / `TC_ORCH_PORT` | `127.0.0.1` / `8080` | HTTP bind address. |

Provider-independent: change `BRAIN_BASE_URL` / `BRAIN_MODEL` to target
OpenRouter, OpenAI, or a local OpenAI-compatible server.

## How to run

```bash
# 1. Start the Workspace Daemon (Step 2)
cd ../backend-rust
TC_WORKSPACE_ROOT=/path/to/ws TC_DAEMON_ADDR=127.0.0.1:50051 cargo run --release

# 2. Run the orchestrator
cd ../tc-orchestrator
BRAIN_API_KEY=... python -m tc_orchestrator.main
```

## API endpoints

- `GET /health` → `{"status":"ok","daemon":"reachable"|"unreachable"}`
- `POST /v1/tasks` body `{"prompt": "..."}` → task summary (synchronous execution)
- `GET /v1/tasks/{id}` → task summary

Task states: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `AWAITING_APPROVAL`.

## Brain contract

- Uses `POST {BRAIN_BASE_URL}/chat/completions` with `tools` (function calling).
- The Brain only **requests** tools; it never executes anything itself.
- The API key is sent only in the `Authorization: Bearer` header.

## Tool registry (Step 3 allowlist)

| Tool | Permission | Read-only | Daemon RPC |
|---|---|---|---|
| `read_file` | L0 | yes | `ReadFile` |
| `write_file` | L1 | no | `WriteFile` (compare-and-set on SHA-256) |
| `exec_command` | L1 | no | `ExecCommand` (explicit timeout) |
| `git_status` | L0 | yes | `GitStatus` |

The registry is authoritative; the Brain cannot register tools. Unknown tools
are hard-rejected; malformed args fail closed.

## Workspace Daemon integration

`WorkspaceClient` (`grpc_client.py`) maps directly to the Step 2 daemon API.
**The orchestrator never uses `open()`, `pathlib` writes, `subprocess`, or
`os.system()` for workspace operations** — everything goes through the daemon,
which remains the security boundary.

gRPC stubs are generated from `backend-rust/proto/{daemon,health}.proto` into
`proto_gen/` (committed). See `proto_gen/__init__.py` for regeneration steps.

## Security boundaries

1. No arbitrary model-generated shell execution outside registered tools.
2. Tool arguments validated with Pydantic (fail closed).
3. All workspace operations go through the Workspace Daemon.
4. Secrets are never inserted into Brain prompts.
5. Tool output is redacted before Brain consumption (defense in depth: the
   daemon redacts too).
6. API keys / tokens / passwords / private keys are never logged.
7. `MAX_AGENT_STEPS` enforced; obvious repeated identical calls are aborted.
8. Command timeouts enforced (daemon + tool schema).
9. Paths outside the workspace are rejected (client-side pre-check + daemon).
10. Fail closed on unknown/malformed tools.

## Tests

```bash
python -m ruff check . && python -m ruff format --check .
python -m pytest -q
```

Coverage: tool registry (A), argument validation (B), fake-brain single &
multi-turn loops (C, D), unknown-tool rejection (E), secret redaction (F),
workspace boundary (G), max-loop termination (H), API (I), Brain parsing,
and a **real-daemon gRPC integration test** that boots the daemon binary.

## Known limitations

- Step 3/4 task execution is synchronous and single-process. The approval
  resume transcript is held in-process (`pending_resume`); a process restart
  while a task is `AWAITING_APPROVAL` fails safely (FAILED) rather than
  guessing. Persisting the transcript for cross-process resume is a future step.
- The Brain is provider-independent but a live provider test requires an
  OpenAI-compatible `BRAIN_API_KEY`; if absent, the mock-Brain suite is the
  source of truth and the live test is reported as SKIPPED.

## Step 4: PostgreSQL persistence + approval workflow

### PostgreSQL persistence

When `DATABASE_URL` (or `TC_DB_*`) is set, the orchestrator uses a
PostgreSQL-backed task store (`pg_task_store.py`) instead of the in-memory
store. Migrations are auto-applied on startup.

Schema (`migrations/0001_core.sql`):
- `tasks(id, prompt, status, answer, error, current_step, max_steps, owner_token_hash, created_at, updated_at)`
- `task_events(id, task_id, ts, event_type, tool_name, arguments_metadata, result_metadata, status, approval_nonce)` — append-only history
- `task_approvals(id, task_id, tool_name, arguments_metadata, risk_level, nonce, status, created_at, decided_at, decided_by, expires_at)`
- `schema_migrations(filename, applied_at)`

All stored `arguments_metadata`/`result_metadata` is **redacted** before write;
no raw secrets, API keys, or credentials are ever persisted.

### Migrations

```bash
# apply (idempotent; tracked in schema_migrations)
python -m tc_orchestrator.migrations apply "$DATABASE_URL"
# dev reset (drop + re-apply)
python -m tc_orchestrator.migrations reset  "$DATABASE_URL"
```

No manual SQL editing required. Works against PostgreSQL 16 (Step 1 image).

### Task lifecycle & state transitions

`PENDING → RUNNING → {AWAITING_APPROVAL, COMPLETED, FAILED}`;
`AWAITING_APPROVAL → {RUNNING, FAILED}`. `COMPLETED`/`FAILED` are terminal.
Invalid transitions are rejected (`transitions.py`); the API cannot set
arbitrary states.

### Approval lifecycle & security levels

| Level | Tools | Approval |
|---|---|---|
| L0 | read_file, git_status | none (execute immediately) |
| L1 | write_file, exec_command | required (pause → AWAITING_APPROVAL) |
| L2 | (future destructive/system-wide) | always required |

Policy is centralized in `policy.py` and configurable
(`TC_REQUIRE_APPROVAL`, default on). The Brain can never bypass it.

Approval flow:
1. Brain requests an L1/L2 tool → orchestrator pauses, persists a pending
   approval (redacted summary + single-use nonce + expiry), task →
   `AWAITING_APPROVAL`.
2. The task **owner** (holder of the owner token returned at creation in the
   `x-tc-owner-token` header) views/approves via the API. The Brain never
   receives the owner token.
3. `POST /v1/tasks/{id}/approve` (or `/reject`) with the exact nonce.
4. On approve: the loop resumes executing the **exact** approved action; on
   reject: task → FAILED (no mutation performed).

Approval protections: single-use nonce (replay rejected), expiry (stale
rejected), action-match (wrong tool/task rejected), terminal-task rejection,
owner-token authorization, atomic decision (concurrent attempts allow one).
DB failures surface as `FAILED` rather than fake success.

### Approval API

- `POST /v1/tasks/{id}/approve` — body `{approved, nonce, decided_by}`, header `x-tc-owner-token`
- `POST /v1/tasks/{id}/reject` — same
- `GET  /v1/tasks/{id}/pending_approval` — owner-only view of the pending action
- `GET  /v1/tasks/{id}/events` — task event history

### Environment variables (Step 4 additions)

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | (none) | PostgreSQL DSN; if unset → in-memory store |
| `TC_DB_USER/PASSWORD/HOST/PORT/NAME` | tc/tc/127.0.0.1/5432/tc | DSN components (used if `DATABASE_URL` unset) |
| `TC_REQUIRE_APPROVAL` | true | Enable approval gating for L1/L2 |
| `TC_APPROVAL_EXPIRY_SECONDS` | 300 | Pending approval expiry |
