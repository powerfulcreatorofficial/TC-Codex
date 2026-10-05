# TC Integration Map

## Control plane

`tc-orchestrator/` is the authoritative control plane. It owns task state, approvals, tool schemas, brain routing, recovery and evidence.

## Secure execution

`backend-rust/` is the execution boundary. External worker agents should not receive a second unrestricted shell path.

## Specialist resources

- **SWE-agent** → repository-aware repair methodology.
- **AutoGen / LangGraph** → multi-agent graph and coordination patterns.
- **Self-Improving Coding Agent** → reflection/evaluation patterns, isolated behind TC boundaries.
- **PyVista** → 3D visualization adapter.
- **Trimesh** → geometry/mesh adapter.
- **DeepXDE** → PINN/PDE capability adapter.
- **PhysicsNeMo** → future physics-ML adapter/catalog capability.
- **vLLM** → future high-throughput inference service.

## Worker delegation

`tc_orchestrator/delegation.py` creates a bounded task packet by default. A worker returns:

- task status
- changed files
- tests run
- evidence
- warnings

The TC lead then decides whether work is accepted.
