# Cybertron vs OpenAI Codex — capability map

This document records which OpenAI Codex agent capabilities exist in
Cybertron, how they map onto modules, and which Cybertron properties are
deliberately *stricter* than Codex. It is the honest ledger for the
"inject actual Codex capabilities" work.

## Capability matrix

| Codex capability | Codex behaviour | Cybertron implementation | Module |
|---|---|---|---|
| Iterative agentic loop | Model calls tools in a loop (shell, patch, plan) until it decides it is done | `AgentLoop` — same loop shape, but it runs **under** Cybertron's stage machine: PLAN → session APPROVE gate → ACT/OBSERVE → deterministic VERIFY → independent REVIEW | `cybertron/agent_loop.py`, `engine.py::_run_agentic` |
| `apply_patch` (V4A format) | `*** Begin Patch` / `*** Add File:` / `*** Update File:` / `*** Delete File:` / `*** Move to:` / `@@` context hunks / `*** End of File`, whitespace-fuzz context matching | Full V4A parser + applier; two-phase (plan everything, then write) so a multi-file patch is all-or-nothing; unified diffs still accepted via `apply_any_patch` dispatch | `cybertron/apply_patch.py` |
| Approval policies | `untrusted`, `on-request`, `never` (`on-failure` deprecated upstream) | `ApprovalPolicy` with the same three values and semantics: `untrusted` auto-runs only known-safe read-only commands; `on-request` runs sandboxed commands and prompts on escalation; `never` never prompts | `cybertron/exec_policy.py` |
| Sandbox modes | `read-only`, `workspace-write`, `danger-full-access` | `read-only` and `workspace-write`. **`danger-full-access` is intentionally absent** — Cybertron refuses to offer an "escape all guards" switch | `cybertron/exec_policy.py` |
| Known-safe command classification | Built-in safe list (ls, cat, grep, rg, git status/diff/log, …) incl. parsing `bash -lc` pipelines | Same approach: safe-list + `bash -lc` parsing via `shlex` with punctuation chars; fails **closed** on redirections, command/process substitution, backticks, unparseable scripts | `cybertron/exec_policy.py::assess_command` |
| Permission escalation | `with_escalated_permissions` + `justification` on the shell tool routes to user approval | Same tool parameters; escalation routes to the existing approval gate (HTTP approvals API) with the justification in the approval detail; expiry ⇒ denial (unchanged) | `agent_loop.py` shell tool |
| `AGENTS.md` project docs | Hierarchical discovery root → cwd, 32 KiB default cap (`project_doc_max_bytes`) | `discover_project_docs` — same chain and cap; content is injected labelled **ADVISORY** and explicitly "never overrides safety policy" (repo content stays untrusted data) | `cybertron/instructions.py` |
| `update_plan` tool | Model maintains a live step plan (pending / in_progress / completed) | Same tool and statuses; updates validated (≤ 20 steps, ≤ 1 in_progress) and surfaced as `plan_updated` events | `cybertron/live_plan.py` |
| Session rollouts | JSONL files under `~/.codex/sessions`, listable/resumable | `SessionRecorder` — JSONL per task (`meta` / `event` / `report` lines) under `.tc-cybertron/sessions`; `GET /v1/cybertron/sessions` + `GET /v1/cybertron/sessions/{task_id}` | `cybertron/sessions.py` |
| Context compaction | Automatic transcript trimming near the context limit | Oldest tool outputs replaced with an honest placeholder (`[output elided to fit context budget]`); system prompt and the latest exchanges are never elided; no fabricated summaries | `agent_loop.py::_compact_if_needed` |
| Loop-guard | — | Extra, not in Codex: 3 identical tool calls with no progress aborts the loop | `agent_loop.py` |

## Where Cybertron is deliberately stricter than Codex

These are retained on purpose and the agentic loop plugs in **under** them:

1. **Deterministic VERIFY** — success requires the task's verification
   commands to exit 0 in the sandbox. The model saying "done" is never
   enough (`test_agentic_model_claim_never_beats_verification`).
2. **Independent REVIEW** — a separate review of the real `git diff`
   must approve; `SUCCESS` requires *both* verification and review.
3. **Pre-charged budgets** — model calls, tool calls, repair attempts and
   wall time are charged **before** spending; exhaustion ⇒ `BLOCKED`,
   truthfully reported.
4. **Session-level approval gate** — before the agentic loop starts, the
   whole task (objective, approval policy, sandbox mode) can require
   human approval; denial ⇒ `BLOCKED` with zero model calls.
5. **No `danger-full-access`** — not implemented, by decision.
6. **Honest isolation reporting** — `SandboxResult.isolation` states what
   the sandbox actually does; no kernel-sandbox claims.

## Known limitations (implemented vs. planned)

- **MCP servers**: not implemented. Extension point: additional tools can
  be appended to `agent_tool_schemas()` and dispatched in
  `AgentLoop._dispatch`; an MCP client would be another `CybertronToolset`
  backend.
- **Session *resume*** (continuing a finished rollout with a new prompt)
  is not wired to the HTTP API; rollouts are recorded, listable and
  loadable, and `AgentLoop.run()` is already continuable in-process
  (used for repair turns).
- **Web search / browser tools**: out of scope for Cybertron (TC-level
  concern).
- The sandbox remains the existing `LocalProcessSandbox` (env-scrub,
  process-group kill, rlimits, optional `unshare -rn` network cut) —
  equivalent kernel-level sandboxing to Codex's Seatbelt/Landlock is a
  documented extension point, not claimed.
