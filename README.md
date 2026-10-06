# engineering-tc

Engineering TC v0.1 — Step 1 infrastructure scaffold.

## What this provides

A Docker Compose stack with:

- **PostgreSQL 16 Alpine** (`postgres:16-alpine`) with a named persistent volume.
- **Redis 7 Alpine** (`redis:7-alpine`) with AOF persistence and a named volume.
- Health checks for both services.
- An internal-only Docker bridge network (`tc-net`) — no host-published ports.
- No privileged containers, no Docker socket mount, no host bind mounts.

Plus a polyglot scaffold so the Step 1 static checks can run:

- `backend-rust/` — Rust crate (`cargo fmt`, `cargo check`).
- `services-python/` — Python package (`ruff`).
- `tc-ui/` — Next.js 14 / TypeScript app (`next lint`, `tsc`).

## Quick start

```bash
cp .env.example .env      # set POSTGRES_PASSWORD
docker compose up -d
docker compose ps
docker compose exec postgres pg_isready -U tc -d tc
docker compose exec redis redis-cli ping
```

## Static checks

See `AGENTS.md` for the full list of static-check commands.


## Phase 6
The current TC UI includes a command-center experience, theme persistence, keyboard command palette, and evidence-based task evaluation. See `TC_PHASE_6_PROGRESS.md`.

## Phase 7 — Engineering Memory Foundation

TC now derives a small set of auditable engineering lessons from completed and failed task evidence, persists them when PostgreSQL is configured, and feeds recent verified lessons into subsequent agent runs. The memory layer is advisory and isolated from the authoritative execution/approval path.

- `tc-orchestrator/src/tc_orchestrator/learning.py`
- `tc-orchestrator/migrations/0002_learning.sql`
- `GET /v1/learnings`
- `tc-ui/src/components/MemoryPanel.tsx`

## Phase 11 — Engineering Planning Engine
TC now supports a plan-first workflow: create a deterministic structured plan, review/approve it with an owner token, then attach the READY plan to a task. The approved plan is included in Brain context and the task/plan lifecycle is persisted when PostgreSQL is configured.

## Phases 17–20 — Multi-Brain Engineering Runtime
TC now defaults its primary Brain configuration to Qwen3.8-27B, supports an explicitly enabled higher brain (default model `gpt-6-astra`), and routes deterministically based on observable execution difficulty. Higher-brain usage is bounded by per-task call/USD limits and surfaced through `GET /v1/tasks/{task_id}/brain` and `GET /v1/brain`.

The higher brain is disabled by default and no secret is exposed by the routing-status API. Native GPT-6 Astra Responses API tool semantics are intentionally not claimed by this phase; use a compatible endpoint until the dedicated Responses adapter is added.

## Cybertron — the engineering capability inside TC

TC now routes engineering work through **Cybertron**
(`tc-orchestrator/src/tc_orchestrator/cybertron/`), a bounded, evidence-based
engineering state machine:

```
TC → Cybertron.execute(task)
     ORIENT → PLAN → APPROVE → ACT → OBSERVE → VERIFY → REVIEW → REPAIR* → REPORT
```

- Deterministic verification is a hard gate; a failing test/command can never
  be reported as success (final statuses: SUCCESS / PARTIAL / FAILED / BLOCKED).
- Model plans are proposals only — validated against hard rules before any
  execution; repository content is treated as untrusted data.
- Sandboxed execution: scrubbed env, process-group kill, rlimits, output caps,
  network off by default; honest isolation reporting (no fake sandbox claims).
- Hardened Git (hooks/config neutralized, safe argument boundaries), budgets
  enforced before every model call, independent read-only review.
- HTTP surface: `/v1/cybertron/*`.

See `docs/CYBERTRON.md` for the full architecture and security model.
