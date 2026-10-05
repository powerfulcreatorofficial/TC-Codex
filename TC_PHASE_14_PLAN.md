# TC Engineering AI — Phase 14 Plan
## Context + Execution Memory

### Objective
Unify project metadata, recent execution evidence, verified lessons, and approved
plan state into one bounded context packet that is inspectable, deterministic,
and reusable by both the Brain and the UI.

### Build order
1. Audit Phase 13 task/project/learning/plan surfaces.
2. Design the bounded context packet and project health model.
3. Implement deterministic bounded context assembly.
4. Reuse it in Brain project/plan context generation.
5. Add an inspectable context-packet API.
6. Add UI health/context telemetry.
7. Add DB retrieval indexes.
8. Add deterministic regression tests.
9. Compile/static-check and document environment-only blockers.

### Safety
- Context never expands filesystem permissions.
- Secrets and owner tokens are excluded.
- No hidden model judgment is persisted.
- Retrieval is bounded by record count.
- Rust remains the filesystem/security boundary.
