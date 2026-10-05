# TC Engineering AI — Phase 9

## Project Context Engine

Implemented a persistent project context surface that combines project metadata, recent project tasks, and verified project-specific lessons.

### Backend
- Added `GET /v1/projects/{project_id}/context`.
- Added project-scoped task and learning queries to both in-memory and PostgreSQL stores.
- Project context is now injected into initial and resumed Brain runs with bounded recent history.
- The daemon security boundary remains unchanged.

### Frontend
- Project detail now shows recent engineering runs, project memory, live task status badges, and the bounded context supplied to TC.

### Safety
- Context uses persisted task metadata/events-derived lessons only; it does not grant filesystem permissions.
- No credentials or owner tokens are included.
