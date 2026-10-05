# TC Engineering AI — Phase 11 Plan

## Engineering Planning Engine

### Goal
Move TC from task -> tool loop toward plan -> approve -> build -> verify.

### Scope
- Structured plans with ordered steps, verification, acceptance criteria and risks.
- Persistent plans in PostgreSQL with an in-memory fallback.
- Explicit owner-protected plan approval.
- READY-plan gate before a task may execute.
- Approved plan context injected into the Brain.
- Plans UI and typed API client.
- Regression coverage for planning, ownership, task gating and project mismatch.
- Repair the checked-in protobuf runtime dependency mismatch.

### Non-goals
- No autonomous self-modification.
- No automatic production deployment.
- No bypass of task/tool approvals.
- No claim that TC's model intelligence exceeds Gemini.

### Success criteria
1. Plans can be created without a paid Brain provider.
2. Draft plans cannot execute tasks.
3. Owner-approved READY plans can be attached to tasks.
4. Plan context reaches the Brain.
5. Project/plan mismatch is rejected.
6. Clean installs declare a protobuf runtime compatible with checked-in stubs.
7. Verification claims are based only on commands actually executed.
