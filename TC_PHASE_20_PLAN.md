# TC Engineering AI — Phase 20 Plan
## Brain Operations Surface

### Goal
Expose routing state to the UI and make the brain layer operationally understandable without exposing secrets.

### Implemented
- Added `GET /v1/brain`.
- Added frontend `brainStatus()` and task brain usage API contracts.
- System page now shows actual primary/higher model configuration instead of a fabricated Brain health status.
- Cost and route telemetry remains derived from persisted execution events.

### Deliberate limitation
The checked-in higher-brain adapter is OpenAI-compatible Chat Completions. Native GPT-6 Astra Responses API semantics remain a separate adapter task because OpenAI's current guidance requires Responses API for some tool-calling scenarios. TC therefore does not claim native Astra tool execution from this phase alone.
