# TC Engineering AI — Phase 18 Plan
## Cost & Usage Control

### Goal
Make expensive higher-brain usage visible and bounded.

### Implemented
- Per-task higher-brain call ceiling.
- Per-task estimated higher-brain USD budget.
- Provider usage normalization for `prompt_tokens`/`completion_tokens` and `input_tokens`/`output_tokens`.
- Configurable pricing for telemetry; primary pricing defaults to zero for free routes.
- Persisted `brain_call` task events contain model/route/cost metadata only.
- Added `GET /v1/tasks/{task_id}/brain`.
