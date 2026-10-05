# TC Engineering AI — Phase 13 Plan
## Adaptive Engineering Loop

### Objective
Turn the existing plan/execution/evaluation stack into a bounded, evidence-driven
adaptive loop. TC should classify failures, choose a bounded recovery strategy,
request targeted re-verification, and expose the recovery state to the UI.

### Build order
1. Repair known Phase 11 integration defects (plan-context wiring + task plan_id plumbing).
2. Add adaptive failure classification and recovery policy.
3. Add recovery telemetry derived from actual task events.
4. Add recovery API endpoints.
5. Feed recovery guidance into the Brain loop after tool failures.
6. Add frontend recovery panel to task detail.
7. Add deterministic regression/smoke coverage.
8. Repair dependency declarations and add reproducibility notes.
9. Run compile/static checks and only report tests that actually execute.

### Recovery classes
- verification_failure: rerun/inspect verification; repair only when evidence warrants it
- tool_failure: inspect concrete tool error; make one targeted correction
- provider_failure: no code mutation; surface external/provider blocker
- approval_blocked: wait for external approval; never bypass
- repeated_action: stop and ask for a new strategy
- unknown_failure: bounded generic diagnosis

### Safety limits
- maximum repair attempts per task: 3 by default
- no self-modification of TC source
- no approval bypass
- no automatic production deployment
- no secret logging
- all recovery recommendations are derived from persisted evidence

### Success criteria
- failures are classified deterministically from real event/task evidence
- retry budget is enforced
- Brain receives explicit recovery guidance after failed tools
- task recovery endpoint returns actionable state
- UI shows recovery state without inventing progress
- existing approval and workspace boundaries remain intact
- known plan-context wiring defects are repaired
- source compiles cleanly
