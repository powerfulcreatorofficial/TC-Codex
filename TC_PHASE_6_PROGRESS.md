# TC Engineering AI — Phase 6 progress

## Implemented in this pass

### Command Center UI
- Reworked the home experience into an engineering command center.
- Added live task/run statistics sourced from `GET /v1/tasks`.
- Added recent engineering runs panel linked to task detail.
- Added real-time active task panel driven by task status + event stream.
- Added engineering starter prompts that prefill the real composer.
- Improved execution/progress presentation without inventing backend metrics.

### Composer and conversation UX
- Rounded premium composer with TC execution affordances.
- Real starter prompt prefill event.
- Improved message hierarchy and copy actions.
- Better task/status badges and long-response handling.
- Clipboard failures are handled without crashing the UI.

### UI command palette
- `Ctrl/Cmd + K` opens a keyboard command palette.
- Navigation shortcuts for Command Center, Tasks, Approvals, System, Settings.
- Keyboard navigation with arrow keys + Enter.

### Appearance
- Added persisted light/dark/system theme selection.
- Added a darker engineering-oriented surface palette while preserving TC green/mint/teal identity.
- Theme preference is UI-only and does not contain secrets.

### Evidence-based task evaluation
- Added `tc-orchestrator/src/tc_orchestrator/evaluation.py`.
- Added `GET /v1/tasks/{task_id}/evaluation`.
- Evaluation is deterministic and based only on observable task state/event evidence.
- It explicitly does NOT claim to judge semantic answer quality.
- Added focused regression tests for completed, failed, and approval-compliance scoring.
- Task detail UI displays the evaluation as an evidence review.

## Verification status

- Python source compilation for the new evaluation/API/model files: PASS.
- Full backend pytest in this container: BLOCKED by an environment-level protobuf mismatch (`daemon_pb2` gencode 7.35.1 vs installed runtime 6.33.6).
- `npm ci` / frontend typecheck could not be completed in this container because dependency installation timed out; an offline retry also failed because required packages were not cached.

No claim of full-suite verification is made here.

## Phase 7 — deterministic engineering memory foundation

- Added `tc-orchestrator/src/tc_orchestrator/learning.py` to derive auditable lessons from task outcomes and event evidence.
- Added migration `0002_learning.sql` with persistent `tc_learnings` storage.
- Both PostgreSQL and in-memory stores support recent learning retrieval.
- Terminal task outcomes persist lessons automatically when supported by the store.
- Recent lessons are injected into the next orchestrator run as bounded context; the Brain cannot write lessons directly.
- Added `GET /v1/learnings` for the command center to display recent lessons without secrets.
- Learning is advisory and failure-isolated: a learning-store failure cannot turn a successful engineering task into FAILED.
- Added regression coverage for repair/verification/efficiency lesson derivation.

This is the first self-improvement layer: TC learns from observable engineering outcomes while keeping the core execution and approval boundaries authoritative.
