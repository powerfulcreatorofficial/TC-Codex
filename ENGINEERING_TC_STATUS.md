# Engineering TC — Build Status

Engineering TC v0.1 — incremental build status. Each step distinguishes
**VERIFIED** (genuinely executed and tested in this environment) from
**UNVERIFIED**.

## Step 1 — Repository / infrastructure scaffold — VERIFIED

- `docker-compose.yml`: PostgreSQL 16 Alpine + Redis 7 Alpine.
- Named persistent volumes (`tc-pg-data`, `tc-redis-data`).
- Health checks, internal-only network (`tc-net`), no privileged containers,
  no Docker socket, no host bind mounts, `.env` git-ignored.
- Runtime verified: `docker compose up/down`, `pg_isready`, `redis-cli ping`,
  persistence survives restart **and** full `down`/`up`.
- Static checks (Rust/Python/TS/TOML/JSON/Compose) pass.
- Commit: `f33b366` (branch `step-1-infra-scaffold`).

## Step 2 — Workspace Daemon (gRPC, Rust/tonic) — VERIFIED

- Located in `backend-rust/` (intentional deviation from the original
  `tc-daemon/` blueprint — kept to preserve working Step 2 code).
- API: `read_file`, `write_file` (atomic compare-and-set on SHA-256),
  `exec_command` (sandboxed, timeout, redacted), `git_create_branch`,
  `git_status`, `git_commit`.
- Protobuf: `backend-rust/proto/{daemon,health}.proto`.
- Security: mandatory workspace root, path-traversal rejection, env_clear for
  child processes, no Docker socket, no privileged container, no host mounts.
- Verified: `cargo fmt`, `cargo clippy -D warnings`, 34 unit + 1 gRPC
  integration test; release binary boots and binds.
- Commit: `d909cd1` (branch `step-2-workspace-daemon`).

## Step 3 — MCP Orchestrator + Brain tool-call loop — VERIFIED

- Located in `tc-orchestrator/` (Python 3.11+, FastAPI, Pydantic, httpx, gRPC).
- Bounded agent loop: Brain → structured tool call → validation → Workspace
  Daemon → redacted result → Brain (repeat until completion / `MAX_AGENT_STEPS`).
- Tool registry is the authoritative allowlist (`read_file`, `write_file`,
  `exec_command`, `git_status`); unknown tools hard-rejected; args validated
  with Pydantic; paths confined to workspace (client-side + daemon).
- `WorkspaceClient` is the only path to the workspace (gRPC); orchestrator
  never uses `open()`/`subprocess`/`os.system` for workspace ops.
- Redaction middleware (literal env secrets + token regexes) on top of the
  daemon's own redaction — defense in depth; secrets never reach the Brain.
- FastAPI: `GET /health`, `POST /v1/tasks`, `GET /v1/tasks/{id}`; in-memory
  task store (PostgreSQL-swappable).
- Verified:
  - `ruff check` + `ruff format --check` clean.
  - `pytest`: 40 passing (registry, router, brain, orchestrator, redaction,
    boundary, max-loop, API, **real-daemon gRPC integration**).
  - FastAPI live startup.
  - Full E2E: real daemon (gRPC) → real `WorkspaceClient` → orchestrator with
    mock Brain → HTTP `POST /v1/tasks` returns `COMPLETED`.
- **Mock Brain loop: VERIFIED** (single-turn, multi-turn, unknown-tool,
  repeated-call, redaction, boundary).
- **Real Brain live test: SKIPPED** — no OpenAI-compatible `BRAIN_API_KEY`
  available in this environment. Not an implementation failure; the Brain
  client code path is covered by mocked-transport tests.

## Structural deviations (intentional)

- Workspace Daemon lives in `backend-rust/`, not `tc-daemon/`. Preserved to
  avoid destroying verified Step 2 code. The orchestrator consumes the daemon
  via its actual gRPC API.
- No Temporal / PostgreSQL persistence in Step 3 by design (scope limit); the
  task store interface is swappable.

## Step 5 — Frontend (tc-ui): design system foundation — VERIFIED

`tc-ui/` is the Engineering TC frontend (Next 14 app router, Tailwind, Radix,
Lucide, Framer Motion). It is a **CLIENT** of the orchestrator — the browser
never executes shell, never reaches the Rust daemon directly, and never stores
secrets/API keys.

- Visual identity: distinctive **green / mint / teal** (NOT blue/gray, NOT dark
  hacker). TC Green `#35E58C`, Deep Emerald `#0B8F62`, Mint `#8FFFD0`, Teal
  `#25C7B5`; light `#F4FBF7` background, white surfaces, charcoal-green text.
  Gradients reserved for small identity elements + the TC Orb only.
- Design token system (CSS variables in `globals.css` → Tailwind): colors,
  radii, shadows, spacing, typography, motion, z-index.
- Typography: Inter (UI) + JetBrains Mono (code/terminal) via `next/font`.
- TC Orb (`signature/TCOrb.tsx`): pure SVG/CSS, six states (idle, thinking,
  executing, waiting, success, error); no WebGL/Three.js; reduced-motion aware.
- Primitives: Button, Input, Textarea, Badge, StatusPill, IconButton, Card,
  Modal, Sheet, Skeleton, Spinner, Divider, Tooltip — accessible, keyboard
  focus, 44px+ touch targets, reduced-motion.
- Signature components: TCOrb, ActivityTimeline, ToolCallCard, ApprovalCard,
  TaskRow, ConnectionIndicator — typed props, reusable; demo data clearly
  labeled and separate from production API state.
- Motion system (Framer Motion where useful; 150–420ms; spring/smooth;
  `prefers-reduced-motion` respected).
- PWA foundation: `manifest.webmanifest` (Engineering TC / TC / standalone /
  orientation any / green theme `#35E58C` / pale-mint bg `#F4FBF7`) + SVG icon
  placeholders.
- Backend integration: `OrchestratorClient` maps the REAL orchestrator routes
  (Steps 3/4); owner token kept in-memory only, never persisted/logged.
- No fake backend, no fake tasks/metrics in production paths.
- Verified:
  - `tsc --noEmit`: clean.
  - `next lint`: no warnings/errors.
  - `prettier --check .`: clean.
  - `next build`: succeeds; home First Load JS ~116 kB.
  - PWA manifest valid JSON; served correctly.
  - Dev server: home HTTP 200, manifest 200, no console/hydration errors;
    green identity present in SSR HTML.
- Backends (Steps 1–4) untouched and unchanged.

### Structural notes (Step 5)

- A new `tc-ui/` package is the primary frontend. The Step 1 `frontend/`
  scaffold is left untouched (its Step 1 static checks remain independent).
- Full Command Center (wired task views, live approval flows, navigation) is
  **not** built yet — by design (Phase 5.1 = foundation only).

## Next recommended step

**PHASE 5.3 — Real-time, persistence & depth**: (a) add a backend `GET /v1/tasks`
list endpoint + persist a server-side approval queue so the UI can show
cross-session history and a global approvals queue; (b) add SSE/WebSocket
streaming to replace polling; (c) wire the Composer to stream live tool
activity; (d) add TOTP/2FA to the approval flow only if/when the backend
implements it (not faked). Keep the daemon as the security boundary and the
orchestrator authoritative.

## Step 5 Phase 5.2 — Command Center + responsive app shell — VERIFIED

Turned the Phase 5.1 design foundation into a real Command Center wired to the
actual orchestrator (Steps 3/4). The browser is a CLIENT only: it never
executes shell, never reaches the Rust daemon, never stores secrets/owner
tokens in localStorage (kept in memory only, never logged).

Verified real backend contract (from tc-orchestrator api.py — authoritative):
- GET /health -> {status, daemon, database}
- POST /v1/tasks {prompt} -> TaskSummary; owner token in `x-tc-owner-token`
  response header (one-time)
- GET /v1/tasks/{id} -> TaskSummary
- GET /v1/tasks/{id}/events -> TaskEvent[]
- GET /v1/tasks/{id}/pending_approval -> ApprovalView (owner-gated)
- POST /v1/tasks/{id}/approve|reject {approved, nonce, decided_by} (owner-gated)
  -> TaskSummary

Frontend→backend integration uses a Next.js rewrite proxy (`/api/*` ->
`ORCH_API_URL`): no CORS, NO backend modification.

Backend gaps (documented, NOT faked):
- **Owner tokens remain in memory only.** The browser never persists approval
  credentials. The read-only task list is safe to reload because it returns
  task summaries without owner tokens.
- **Streaming is available.** Task event history remains available via GET, and
  the event stream endpoint emits real Server-Sent Events until terminal state.
- **No global approvals endpoint.** The Approvals queue remains limited to
  tasks whose owner token is held by the current browser session.
- **Brain status not exposed** by /health — not shown (no invented metrics).
- **Full success/approval E2E requires a Brain API key** (BRAIN_API_KEY), which
  is unavailable in this environment. The real failure path (task -> FAILED
  with real error + owner token capture + real events) IS verified against the
  live orchestrator+daemon through the proxy. The full success/approval path is
  verified at the Python integration layer (Step 4, MockBrain + real PG + real
  daemon).

Implemented:
- Responsive app shell: mobile top bar + bottom nav (Home/Tasks/Approvals/
  System), desktop left rail; safe-area, 44px targets, reduced-motion.
- Command Center (`/`): identity greeting, Composer (Enter/Shift+Enter, send,
  loading), current task state (real status -> Orb state), recent activity
  (real events). Orb state derived from real task status.
- Composer wired to real `POST /v1/tasks`; owner token captured to in-memory
  session.
- Tasks (`/tasks`): session task list with live statuses; loading/empty/error.
- Task detail (`/tasks/[id]`): status, activity timeline (real events), approval
  card (owner-gated, real approve/reject), answer/error.
- Approvals (`/approvals`): session AWAITING_APPROVAL queue; real approve/reject.
- System (`/system`): only real /health data (orchestrator/daemon/database).
- Global approval indicator: badge with real pending count in nav.
- Connection state: useHealth drives the connection indicator; never shows
  healthy when unreachable.

Verified:
- `tsc --noEmit`: clean. `next lint`: no warnings/errors. `prettier --check`:
  clean. `next build`: succeeds (6 routes; ~125 kB First Load JS).
- Dev server: `/`, `/tasks`, `/tasks/[id]`, `/approvals`, `/system`,
  manifest all HTTP 200; no hydration/app console errors; green identity in SSR.
- Real API integration via proxy: `/api/health` -> real; `POST /api/v1/tasks`
  -> real FAILED (no Brain key) + owner token header captured; `GET
  /api/v1/tasks/{id}` -> real; `GET /api/v1/tasks/{id}/events` -> real
  ['task_started','task_failed'].

Files changed: tc-ui only (18 files). Steps 1–4 untouched and unchanged.

## Step 4 — PostgreSQL persistence + approval workflow — VERIFIED

- PostgreSQL-backed task store (`pg_task_store.py`, psycopg3, sync to match
  the existing sync API surface) replacing the in-memory store behind the
  same interface. Step 1 Postgres 16 image unchanged (dev/test uses an
  ephemeral `postgres:16-alpine` container; the production compose is not
  weakened).
- Schema (`migrations/0001_core.sql`): `tasks`, `task_events` (append-only
  history), `task_approvals`, `schema_migrations`. Reproducible migration
  runner (`migrations.py`: `apply` / `reset`); no manual SQL.
- Explicit state machine (`transitions.py`): PENDING→RUNNING→{AWAITING_APPROVAL,
  COMPLETED, FAILED}; AWAITING_APPROVAL→{RUNNING, FAILED}; terminal states
  locked. Invalid transitions rejected; API cannot set arbitrary states.
- Approval workflow: centralized policy (`policy.py`) with L0/L1/L2 levels
  (L2 reserved). L1 tools (write_file, exec_command) pause →
  AWAITING_APPROVAL. Single-use nonce, expiry, action-match, terminal-task
  rejection, owner-token authorization, atomic decision (concurrent-safe).
  The Brain cannot approve (no owner token). DB failures → FAILED, never
  fake success.
- Approval API: `POST /v1/tasks/{id}/approve|reject`, `GET .../pending_approval`
  (owner-only), `GET .../events`.
- All stored metadata redacted; no raw secrets/API keys/credentials persisted.
- Verified:
  - `ruff check` + `ruff format --check` clean.
  - `pytest`: 99 passing (40 Step 3 + 59 Step 4, incl. PG-parametrized store
    & approval tests and 3 real-PG + real-daemon HTTP end-to-end tests).
  - Step 2 Rust regression: 35 tests, fmt + clippy clean.
  - Real PostgreSQL integration: VERIFIED (ephemeral docker postgres:16).
  - Real Workspace Daemon integration: VERIFIED (read_file, write_file via
    approval flow, file actually written through the daemon).
  - Task survives app restart (PG persistence): VERIFIED.

### Structural deviations (Step 4)

- psycopg3 used in sync mode (not async) to avoid rewriting the verified
  Step 3 sync API/orchestrator surface; documented as intentional.
- Approval-resume transcript held in-process (single-process sync execution
  by design); a restart while AWAITING_APPROVAL fails safely.

## Phase 11 — Engineering Planning Engine — IMPLEMENTED / VERIFICATION IN PROGRESS

- Added deterministic structured planning engine.
- Added persistent plan schema and owner-protected plan approval.
- Tasks may attach only READY plans.
- Approved plan context is injected into Brain context.
- Added Plans API and UI.
- Added regression tests.
- Explicitly declared protobuf >=7.35.1,<8 to match checked-in generated stubs.
- Added safe plan lifecycle updates on task completion/failure/rejection.

## Phase 13 — Adaptive Engineering Loop — IMPLEMENTED / VERIFICATION IN PROGRESS

- Added deterministic failure classification and bounded recovery policy.
- Added configurable MAX_REPAIR_ATTEMPTS (default 3).
- Failed tool results now feed explicit bounded recovery guidance back into the Brain context.
- Added GET /v1/tasks/{task_id}/recovery.
- Added Task Recovery UI on failed/approval-blocked task detail screens.
- Repaired plan-context wiring into the orchestrator config.
- Added Phase 13 plan document and dependency/reproducibility notes.
- Full-suite verification remains dependent on installing the repository's pinned Python/Node dependencies in a clean environment.

## Phase 13 verification notes

- Fixed Phase 11 task plan_id persistence/PG project-task row compatibility.
- Fixed Settings backward compatibility by defaulting MAX_REPAIR_ATTEMPTS to 3.
- Fixed TaskRecoveryOut API import and frontend TaskSummary plan fields.
- Added deterministic adaptive recovery tests.

## Phase 14 — Context + Execution Memory — IMPLEMENTED / VERIFICATION IN PROGRESS

- Added a deterministic bounded context engine that combines project metadata,
  recent tasks, verified lessons, and approved plan state.
- Added GET /v1/projects/{project_id}/context/packet for inspectable context
  packets and project health telemetry.
- Reused the context engine for Brain project/plan context assembly.
- Added project-context health metrics to the UI.
- Added migration indexes for project task and learning retrieval.
- Added deterministic context-engine regression tests.
- Kept the Rust daemon as the filesystem/security boundary and did not expand
  tool permissions.


## Phase 15 — Relevance-Driven Context Retrieval — IMPLEMENTED / VERIFICATION IN PROGRESS

- Added deterministic lexical retrieval over project-scoped persisted tasks and verified learnings.
- Added bounded retrieval packets with stable ordering, minimum relevance threshold, and inspectable reasons.
- Added GET /v1/projects/{project_id}/context/retrieve for UI inspection.
- Injected retrieved project evidence into initial and approval-resumed Brain contexts.
- Added frontend API support for retrieval inspection.
- Added regression tests for relevance, deterministic ordering, bounds, and thresholding.
- Added Phase 15 plan before implementation.

## Phase 15 verification notes

- Planned first in `TC_PHASE_15_PLAN.md`.
- Source compilation passes.
- Deterministic retrieval smoke test passes after excluding generic task outcomes from the primary relevance score.
- Project-scoped retrieval only reads the current project's persisted tasks/learnings.
- Retrieval context is bounded to at most six evidence items per request.
- Frontend project detail now includes a retrieval preview using the live API contract.
- Full pytest collection/build remains environment-dependent and is not claimed here.## Phase 16 — Repository Snapshot + Change Awareness — IMPLEMENTED / VERIFICATION IN PROGRESS

- Added read-only repository snapshotting through `WorkspaceClient` only.
- Added project-scoped Git branch/cleanliness and bounded changed-file evidence.
- Added bounded file hashes/sizes and common manifest discovery.
- Injected current repository evidence into initial and approval-resumed Brain contexts.
- Added `GET /v1/projects/{project_id}/repository`.
- Added deterministic/path-safety regression tests.
- No filesystem or shell access was added to the Python orchestrator.

## Phase 16 — Repository Snapshot + Change Awareness — IMPLEMENTED / VERIFICATION IN PROGRESS

Planning-first repository intelligence layer added. Current project context now includes
read-only Git cleanliness/branch state, bounded changed-file metadata and common manifest
evidence collected through WorkspaceClient. Repository evidence is injected into initial
and approval-resumed Brain context and is visible at the project repository endpoint/UI.


## Phases 17–20 — IMPLEMENTED / VERIFICATION IN PROGRESS

- Phase 17: multi-brain router with Qwen3.8-27B primary and optional higher brain.
- Phase 18: bounded higher-brain cost/call budget plus persisted brain-call telemetry and per-task usage endpoint.
- Phase 19: bounded primary-provider failover to the higher brain; provider failures remain visible through the safe task failure path.
- Phase 20: brain routing status endpoint and live UI display.
- Source compilation passes.
- Focused router smoke test passes without external dependencies.
- Full pytest remains blocked in this container because installed protobuf runtime is 6.33.6 while checked-in generated stubs require 7.35.1; network access is unavailable for dependency installation.
- Native Rust and Next.js full builds are not claimed in this container because the required toolchains/dependencies are unavailable.


## Phase 21 — IMPLEMENTED / VERIFICATION IN PROGRESS

- Added native Responses API adapter for the configured higher brain.
- Added function-call output correlation IDs in the internal transcript.
- Kept tool execution and approvals inside TC; the model still cannot execute tools directly.
