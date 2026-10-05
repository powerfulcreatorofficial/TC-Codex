# Engineering TC — Deployment

Engineering TC is a layered system. The browser/UI is a **client** only and
never executes commands or reaches the Rust daemon directly.

```
Browser (tc-ui)
   ↓  (Next.js rewrite proxy: /api/* → orchestrator)
Orchestrator (tc-orchestrator, FastAPI)
   ↓  (gRPC)
Rust daemon (backend-rust, WorkspaceDaemon)
   ↓  (sandboxed filesystem/exec)
Workspace / system
```

PostgreSQL backs persistent task/approval state (Step 4); Redis is provisioned
by the Step 1 compose for future use.

## Requirements

- Node 18+ (tc-ui), Python 3.11+ (orchestrator), Rust stable (daemon)
- Docker (for PostgreSQL via the Step 1 compose, or an external Postgres 16)

## Environment variables

### Orchestrator (`tc-orchestrator`)

| Var                          | Required                      | Purpose                                                                    |
| ---------------------------- | ----------------------------- | -------------------------------------------------------------------------- |
| `BRAIN_API_KEY`              | **Yes for real task success** | OpenAI-compatible Brain API key. Without it, tasks fail at the Brain call. |
| `BRAIN_BASE_URL`             | No (default OpenRouter)       | OpenAI-compatible base URL.                                                |
| `BRAIN_MODEL`                | No (default qwen)             | Model id.                                                                  |
| `TC_DAEMON_ADDR`             | No (default 127.0.0.1:50051)  | Rust daemon gRPC endpoint.                                                 |
| `DATABASE_URL`               | No (→ in-memory store)        | PostgreSQL DSN for persistent tasks.                                       |
| `TC_REQUIRE_APPROVAL`        | No (default true)             | Enable approval gating for L1/L2 tools.                                    |
| `TC_APPROVAL_EXPIRY_SECONDS` | No (default 300)              | Pending approval expiry.                                                   |

### Daemon (`backend-rust`)

| Var                 | Required                     | Purpose                                                   |
| ------------------- | ---------------------------- | --------------------------------------------------------- |
| `TC_WORKSPACE_ROOT` | **Yes**                      | The workspace root the daemon confines all operations to. |
| `TC_DAEMON_ADDR`    | No (default 127.0.0.1:50051) | gRPC bind address.                                        |

### tc-ui

| Var            | Required          | Purpose                                                                            |
| -------------- | ----------------- | ---------------------------------------------------------------------------------- |
| `ORCH_API_URL` | Yes (server-side) | Orchestrator base URL for the `/api` rewrite proxy (e.g. `http://127.0.0.1:8090`). |

> **BRAIN_API_KEY is required for real Brain-backed task success.** Without a
> valid key, task creation returns a real `FAILED` response (the orchestrator
> calls the Brain on every task). Never commit a real key — use `.env` (git-
> ignored) or your deployment's secret manager.

## Local development

```bash
# 1. Start the Rust daemon
cd backend-rust
TC_WORKSPACE_ROOT=/path/to/workspace cargo run --release

# 2. Start the orchestrator (in-memory store, no Postgres needed for dev)
cd ../tc-orchestrator
pip install -e .
PYTHONPATH=src TC_DAEMON_ADDR=127.0.0.1:50051 \
  python -m uvicorn tc_orchestrator.api:create_app --factory --port 8090

# 3. Start tc-ui with the proxy pointed at the orchestrator
cd ../tc-ui
npm install
ORCH_API_URL=http://127.0.0.1:8090 npm run dev
```

Open http://localhost:3000.

## Production build

```bash
cd tc-ui
npm install
npm run build
ORCH_API_URL=https://your-orchestrator npm run start
```

## With PostgreSQL (persistent tasks)

```bash
# Start Postgres 16 via the Step 1 compose (internal network)
docker compose up -d postgres

# Or run the orchestrator inside the tc-net network, or expose Postgres.
# Then point the orchestrator at it:
DATABASE_URL=postgresql://tc:tc@host:5432/tc python -m uvicorn ...
# Apply migrations:
python -m tc_orchestrator.migrations apply "$DATABASE_URL"
```

## Health check

```bash
curl http://<orchestrator>/health
# {"status":"ok","daemon":"reachable","database":"reachable"}
```

tc-ui's `/system` page shows this live status.

## Troubleshooting

- **Tasks return `FAILED: "Illegal header value b'Bearer '"`** — `BRAIN_API_KEY`
  is not set on the orchestrator. Set a valid OpenAI-compatible key.
- **UI shows "Connection to the orchestrator was lost"** — `ORCH_API_URL` is
  wrong or the orchestrator is down. Verify `/api/health` returns 200.
- **System shows daemon "unreachable"** — the Rust daemon isn't running or
  `TC_DAEMON_ADDR` doesn't match between orchestrator and daemon.
- **Approvals never appear** — approval requires `TC_REQUIRE_APPROVAL=true`
  (default) and a task that requests an L1/L2 tool; the Brain must be reachable
  to drive the loop to that point.

## Security boundaries (do not weaken)

- The browser never executes shell, accesses the filesystem, or talks to the
  daemon directly.
- Owner tokens (for approvals) are kept in memory only — never in localStorage,
  URLs, or logs.
- Approval nonces come only from the backend; the UI never manufactures them.
- No `dangerouslySetInnerHTML`; user/backend text is rendered safely.
