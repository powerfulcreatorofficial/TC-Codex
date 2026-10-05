# Resource Manifest

This master includes copies of resource archives that were available locally during construction. They are retained as **source material**; runtime code does not blindly import them.

Key resources:

- LangGraph
- AutoGen
- SWE-agent
- Self-Improving Coding Agent
- PyVista
- Trimesh
- DeepXDE
- vLLM
- PhysicsNeMo
- prior Engineering-TC phase archives

The user also reported having full copies of OpenHands, Nanobot and OpenJarvis. Those copies were **not locally available in this session's working filesystem**, so they are not falsely represented as bundled here.

## Integration policy

For every upstream resource:

1. preserve license/attribution;
2. adapt only the capability needed;
3. keep TC's Workspace Daemon and approval boundary authoritative;
4. never make an external repo's agent loop the system owner;
5. record provenance and verification evidence.
