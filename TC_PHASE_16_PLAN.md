# TC Engineering AI — Phase 16 Plan
## Repository Snapshot + Change Awareness

### Goal
Give TC a bounded, evidence-first view of the current repository state so planning
and reasoning can distinguish historical memory from what actually exists now.

### Scope
1. Read-only repository snapshot derived through the Rust Workspace Daemon.
2. Git branch/cleanliness + bounded changed-file list.
3. Bounded hashes/sizes for changed files, without dumping entire files into context.
4. Common project manifest/config discovery (package.json, pyproject.toml, Cargo.toml,
   requirements.txt, go.mod, Dockerfile, docker-compose.yml, README.md, tsconfig.json).
5. Bounded previews only for small text manifests; no binary content.
6. Repository context injected into initial and resumed Brain runs.
7. Project repository endpoint for UI/debugging.
8. Regression tests for path scoping, limits, deterministic ordering, and secret safety.
9. Keep Rust daemon as the filesystem/security boundary.

### Non-goals
- No shell/subprocess calls from the Python orchestrator.
- No unrestricted repository dumping.
- No automatic commits/deployments.
- No autonomous self-modification.
- No external web dependency.

### Success criteria
- Snapshot can be produced from a project using WorkspaceClient only.
- Changed files are limited to the project's workspace path when configured.
- All output is bounded and deterministic.
- Snapshot is included in Brain context.
- API exposes repository state without credentials or owner tokens.
- Python sources compile; tests are added and run where dependencies permit.
