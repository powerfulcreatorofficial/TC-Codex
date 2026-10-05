# TC ENGINEERING AI — Master Repository

This repository is the **master integration base** for TC ENGINEERING AI (“Jarvis”). It starts from the previously verified Phase-20 architecture and adds a bounded specialist-agent delegation layer plus optional engineering/scientific adapters.

## What is in the master

- Rust Workspace Daemon: path confinement, filesystem operations, execution boundary, gRPC.
- FastAPI Orchestrator: tasks, plans, approvals, retrieval, repository intelligence, recovery, learning, evaluation.
- Multi-Brain router: primary Qwen-compatible Brain + optional higher Brain.
- Higher-Brain Responses adapter for `gpt-6-astra`.
- Cost/budget and brain-call telemetry.
- Specialist delegation protocol and packet-based worker handoff.
- Engineering capability discovery for PyVista, Trimesh, DeepXDE, vLLM and PhysicsNeMo when installed.
- Evidence records and mission preparation layer.
- Existing Next.js TC UI and Rust integration tests from Phase 20.
- Preserved historical TC phase archives and inspected upstream resource archives under `resources/archives/`.

## Important reality check

This is a **master engineering repository**, not a claim that a frontier model or every optional dependency has already been installed and verified on the current 4-core/16-GB/no-GPU machine.

Heavy scientific/inference components remain optional. The repo can run the control plane with external model providers, while heavier components can be enabled later on suitable hardware or hosted infrastructure.

## Model defaults

Primary:
- `qwen/qwen3.8-27b` through an OpenAI-compatible provider.

Higher:
- `gpt-6-astra` through the OpenAI Responses API.

Both are configurable through environment variables. Higher-brain use is disabled by default and budget bounded.

## Specialist delegation

The new delegation layer deliberately keeps worker agents subordinate to TC:

```text
Creator
  -> TC Brain / Orchestrator
      -> choose specialist
          -> worker packet / optional HTTP worker
              -> evidence + changed files + tests
      -> TC review / policy / approval
      -> integration
```

By default, delegation only creates an auditable job packet. HTTP workers require explicit opt-in via `TC_ALLOW_HTTP_AGENTS=1` and an operator-configured endpoint.

## Suggested startup

```bash
cp .env.example .env
# fill PRIMARY_BRAIN_API_KEY and (optionally) HIGHER_BRAIN_API_KEY

# control plane dependencies
python -m pip install -e tc-orchestrator

# optional local services
# docker compose up -d postgres redis

# daemon
cd backend-rust
cargo run -- --workspace-root /path/to/a/workspace

# orchestrator
cd ../tc-orchestrator
tc-orchestrator
```

See `docs/MASTER_BUILD_STATUS.md` for the exact verification performed while creating this archive.
