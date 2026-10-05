# TC Engineering AI — Phase 19 Plan
## Provider Resilience & Safe Fallback

### Goal
Avoid a single primary-provider outage taking down an entire engineering task.

### Implemented
- Primary-provider exception triggers one bounded higher-brain fallback when higher brain is enabled and within budget.
- Higher-brain failures are not hidden; the task fails through the existing safe error path.
- No credential or raw provider response is placed into persistent telemetry.
- Added explicit `/v1/brain` routing configuration endpoint with no secret fields.
