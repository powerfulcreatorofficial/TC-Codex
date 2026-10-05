# TC Engineering AI — Phase 8

## Project Intelligence Foundation — implemented

This phase adds persistent project/workspace awareness on top of the verified agent core.

### Backend
- Added `tc_projects` persistent registry and migration `0003_projects.sql`.
- Added `project_id` association to tasks.
- Added CRUD-style project API: list/create/get/update/delete.
- Task creation accepts an optional `project_id` and rejects unknown projects.
- Active project metadata is injected into the orchestrator system context for both initial and resumed runs.
- In-memory and PostgreSQL stores implement the same project surface.

### Frontend
- Added `/projects` workspace registry.
- Added `/projects/[id]` project detail page.
- Added Projects navigation to desktop and mobile shell.
- Added typed project API helpers and optional `project_id` support on task creation.

### Design intent
Project context is descriptive and bounded. The daemon workspace remains the execution/security boundary; project metadata does not grant extra filesystem privileges.

### Verification
- Python source compilation: PASS.
- Focused pytest attempt: BLOCKED in this container by the pre-existing protobuf gencode/runtime mismatch (gencode 7.35.1 vs runtime 6.33.6), before test collection.
- Frontend dependency/build verification was not completed in this container because dependencies are not guaranteed to be locally cached.
- No claim of full-suite verification is made.
