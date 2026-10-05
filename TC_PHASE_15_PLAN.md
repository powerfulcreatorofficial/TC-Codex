# TC Engineering AI — Phase 15 Plan
## Relevance-Driven Context Retrieval

### Objective
Turn the Phase 14 bounded context packet into task-aware retrieval. TC should not send the same historical context to every task. It should select the most relevant verified project evidence while remaining deterministic, bounded, inspectable, and secret-free.

### Build order
1. Audit Phase 14 context/task/learning interfaces.
2. Define deterministic lexical relevance scoring over persisted task prompts, task outcomes, and verified lessons.
3. Implement a bounded retriever with minimum relevance and stable tie-breaking.
4. Add a retrieval API for UI inspection.
5. Inject the selected context into initial Brain runs and approval resumes.
6. Add a UI retrieval preview on project/task surfaces.
7. Add indexes/metadata only where they improve retrieval without changing security boundaries.
8. Add regression tests for relevance, bounds, project isolation, deterministic ordering, and secret exclusion.
9. Repair/document dependency mismatches if clean-install metadata is incomplete.
10. Verify source compilation, focused tests, and package integrity. Do not claim unavailable full-suite results.

### Safety
- Retrieval is read-only.
- Only records already authorized for the current project are candidates.
- No workspace permission changes.
- No secrets, owner tokens, or raw credentials enter retrieval context.
- No hidden model-generated ranking: scoring is deterministic and auditable.
- Candidate count, score, and context length are bounded.

### Success criteria
- A task prompt retrieves the most semantically relevant persisted task lessons/evidence.
- Unrelated project records are excluded.
- Retrieval order is stable.
- Brain receives only the bounded retrieved context plus existing project/plan context.
- UI can inspect what was retrieved and why.
