# TC Engineering AI — Phase 17 Plan
## Multi-Brain Routing

### Goal
Make Qwen3.8-27B the default primary engineering brain while allowing TC to escalate difficult runs to an explicitly configured higher brain.

### Implemented
- Added `BrainRouter` around the existing provider-independent Brain protocol.
- Primary model defaults to `qwen/qwen3.8-27b` and remains configurable.
- Higher brain defaults to `gpt-6-astra`, but is disabled unless explicitly enabled and configured.
- Deterministic escalation from observable tool failures, repeated actions, or provider failure.
- Escalated route remains active for the current task.
- Brain router never executes tools or receives owner credentials.
