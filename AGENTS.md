# AGENTS.md — engineering-tc

Persistent memory for the engineering-tc repository.

## Project

Engineering TC v0.1 — a polyglot test-case engineering platform.

- `docker-compose.yml` — Step 1 infra: PostgreSQL 16 Alpine + Redis 7 Alpine.
- `backend-rust/` — Rust Workspace Daemon crate (`cargo`).
- `services-python/` — Python services (`ruff`, `pyproject.toml`).
- `tc-orchestrator/` — FastAPI control plane + **Cybertron** engineering
  subsystem (`src/tc_orchestrator/cybertron/`, see `docs/CYBERTRON.md`).
- `tc-ui/` — Next.js 14 / TypeScript frontend (the only frontend; the old
  `frontend/` scaffold was removed).

## Environment

- Docker daemon must be started inside the runtime container:
  `sudo dockerd > /tmp/docker.log 2>&1 &` then wait ~6s.
- The `openhands` user is added to the `docker` group; use `sg docker -c '...'`
  (or `sudo docker ...`) for non-root Docker access in this environment.
- `.env` is git-ignored. Copy `.env.example` to `.env` and set real values.
  `POSTGRES_PASSWORD` is required (`docker compose` will fail without it).

## Docker Compose conventions (Step 1)

- Internal-only bridge network `tc-net`; no host-published ports.
- Named persistent volumes: `tc-pg-data`, `tc-redis-data` (no host bind mounts).
- No privileged containers, no Docker socket mounted, `no-new-privileges:true`.
- Health checks: postgres `pg_isready -U tc -d tc`, redis `redis-cli ping`.

## Static checks (Step 1)

Run from repo root:

- Rust: `cd backend-rust && cargo fmt --check && cargo check`
- Python: `cd services-python && ruff check . && ruff format --check .`
- Orchestrator: `cd tc-orchestrator && ruff check . && python -m pytest -q`
- Next.js/TS: `cd tc-ui && npm ci && npm run lint && npm run typecheck`
- TOML: `python -m tools.check_toml`
- JSON: `python -m tools.check_json`
- Docker Compose: `docker compose config`

## Workspace Daemon (Step 2)

`backend-rust/` is now the gRPC Workspace Daemon.

- `proto/daemon.proto` — daemon API (read_file, write_file, exec_command,
  git_create_branch, git_status, git_commit).
- `proto/health.proto` — standard gRPC health check.
- `src/workspace.rs` — workspace root enforcement + path-traversal rejection.
- `src/redaction.rs` — deterministic secret redaction (literals + token regexes).
- `src/daemon.rs` — core operations (atomic CAS writes, sandboxed exec w/
  timeout + redaction, safe git ops). Unit-tested without gRPC.
- `src/grpc.rs` — tonic service adapter + health endpoint.
- `src/main.rs` — server entrypoint (binds 127.0.0.1:50051 by default).

### Daemon verification commands

```bash
cd backend-rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
# run the server
TC_WORKSPACE_ROOT=/path/to/ws TC_DAEMON_ADDR=127.0.0.1:50051 cargo run --release
```

### Daemon security model

- Workspace root is mandatory (`TC_WORKSPACE_ROOT`); all paths confined to it.
- `..` / absolute / root-component paths are rejected before any file touch.
- `write_file` is compare-and-set on SHA-256 + atomic temp+rename.
- `exec_command` requires an explicit timeout, clears the child env (no secret
  leakage), runs with CWD = workspace root, and redacts stdout/stderr.
- Git ops use explicit argv (no shell), never force, and reject path traversal
  in staged paths.
- No Docker socket access, no privileged container, no host mounts — the daemon
  is meant to run inside the Step 1 sandboxed container.

## MCP Orchestrator (Step 3)

`tc-orchestrator/` is the Python MCP Orchestrator + Brain tool-call loop.

- `src/tc_orchestrator/` — config, models, brain, orchestrator, tool_registry,
  tool_router, grpc_client, redaction, api, task_store, main.
- `src/tc_orchestrator/proto_gen/` — generated Python gRPC stubs for the daemon
  (committed; regenerate with `python -m grpc_tools.protoc`).
- Bounded loop: Brain -> tool call -> validation -> daemon -> redacted result ->
  Brain, capped at `MAX_AGENT_STEPS` (default 20).
- Tools: read_file (L0), write_file (L1), exec_command (L1), git_status (L0).
  Registry is the authoritative allowlist; Brain cannot register tools.
- FastAPI: GET /health, POST /v1/tasks, GET /v1/tasks/{id}.

### Orchestrator verification commands

```bash
cd tc-orchestrator
python -m ruff check . && python -m ruff format --check .
python -m pytest -q            # includes real-daemon gRPC integration
```

Env: BRAIN_BASE_URL, BRAIN_API_KEY, BRAIN_MODEL, TC_DAEMON_ADDR,
MAX_AGENT_STEPS, TC_ORCH_HOST, TC_ORCH_PORT.

## Persistence & Approval (Step 4)

- `pg_task_store.py` (psycopg3, sync) — PostgreSQL-backed task store behind the
  same interface as the in-memory `task_store.py`. Used when `DATABASE_URL` is
  set; else in-memory.
- `db.py` — connection factory. `migrations.py` + `migrations/*.sql` —
  reproducible schema (`apply`/`reset`); tables: tasks, task_events,
  task_approvals, schema_migrations.
- `transitions.py` — explicit state machine; invalid transitions rejected.
- `policy.py` — L0/L1/L2 approval policy (centralized, configurable).
- `approval.py` — single-use nonce, expiry, owner-token hashing.
- Approval endpoints: POST /v1/tasks/{id}/approve|reject (owner-token header),
  GET .../pending_approval, GET .../events.
- DB failures -> FAILED (never fake success). All stored metadata redacted.

Env: DATABASE_URL (or TC_DB_*), TC_REQUIRE_APPROVAL (default true),
TC_APPROVAL_EXPIRY_SECONDS (default 300).

## Verification commands

```
docker compose exec postgres pg_isready -U tc -d tc
docker compose exec redis redis-cli ping
```

## tc-ui (Step 5 — frontend)

`tc-ui/` is the Engineering TC frontend (Next 14 app router, Tailwind, Radix,
Lucide, Framer Motion). Green/mint/teal identity. It is a CLIENT of the
orchestrator — the browser never executes shell, never reaches the daemon, never
stores secrets.

- Design tokens in `src/app/globals.css` (CSS vars) mapped via `tailwind.config.ts`.
- Primitives in `src/components/primitives/`; signature components in
  `src/components/signature/` (TCOrb, TaskRow, ToolCallCard, ApprovalCard,
  ActivityTimeline, ConnectionIndicator).
- `src/lib/api/orchestrator.ts` — typed client for the REAL orchestrator routes.
- PWA: `public/manifest.webmanifest` (Engineering TC / TC / standalone / green theme).

### tc-ui verification commands

```bash
cd tc-ui
npm install
npm run typecheck   # tsc --noEmit
npm run lint        # next lint
npm run format      # prettier --check .
npm run build       # next build
```

## Cybertron — engineering capability inside TC

`tc-orchestrator/src/tc_orchestrator/cybertron/` implements the bounded
engineering state machine (ORIENT → PLAN → APPROVE → ACT → OBSERVE → VERIFY →
REVIEW → REPAIR → REPORT). Full architecture + security model:
`docs/CYBERTRON.md`.

Durable rules for anyone (human or agent) working on this subsystem:

- Cybertron is invoked as `TC → Cybertron.execute(task)`; do not grow it into
  the whole TC system, and keep the interface model-independent.
- Success is evidence-based ONLY: `SUCCESS` requires all verification
  commands to exit 0 AND independent review approval. Never convert a failed
  command/test into success; `ok` must mean `completed && exit_code == 0`.
- Budgets (`cybertron/budget.py`) are charged BEFORE model/tool calls —
  never add post-hoc accounting as a substitute.
- Model output is a PROPOSAL. Everything executable goes through
  `planning.validate_plan` (allowlisted executables, relative paths, no
  dangerous tokens). Repository content is UNTRUSTED DATA, never instructions
  (`memory.py` enforces this for stored memory).
- Do not weaken: symlink/traversal rejection in `workspace.py`, env scrubbing
  and process-group kill in `sandbox.py`, hook/config hardening in
  `gitsafe.py`. Do not claim kernel-level sandboxing — `SandboxResult.isolation`
  must stay honest; container runner is the extension point.
- HTTP surface: `/v1/cybertron/*`; approval expiry DENIES (never auto-approve).
- Tests live in `tc-orchestrator/tests/cybertron/` and cover security
  scenarios (traversal, symlink escape, malicious git config/hooks, timeout
  process-tree kill, oversized output, budget exhaustion, prompt-injected
  plans, truthful final status). Keep them passing; add a test when touching
  any security boundary.
