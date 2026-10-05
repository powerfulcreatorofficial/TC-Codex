# TC Build Manifest — Phase 20 bundle

Base: Engineering TC Phase 16

Completed in this bundle:
- Phase 17 — Multi-Brain Routing
- Phase 18 — Cost & Usage Control
- Phase 19 — Provider Resilience & Safe Fallback
- Phase 20 — Brain Operations Surface
- Phase 21 — Native Higher-Brain Responses Adapter

Primary brain default: `qwen/qwen3.8-27b`
Higher brain default: `gpt-6-astra`
Higher brain: disabled by default; enable explicitly with a key and compatible endpoint.

Verification in this environment:
- Python compileall: PASS
- Brain router smoke: PASS
- Responses adapter parse smoke: PASS
- Primary-provider fallback smoke: PASS
- Config smoke: PASS
- Full pytest: BLOCKED by installed protobuf 6.33.6 vs checked-in gencode 7.35.1 and no network access for dependency installation.
- Full Next.js build/typecheck: NOT CLAIMED because frontend dependencies are not installed.
- Full Rust build: NOT CLAIMED because the container lacks the Rust toolchain.
