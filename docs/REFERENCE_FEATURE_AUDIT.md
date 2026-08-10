# ForgeOS reference-feature audit

This document is the clean-room audit of the five public repositories that
influenced ForgeOS. ForgeOS does not import their source code or runtime
dependencies. Each adopted idea is expressed through a ForgeOS contract,
local implementation, and deterministic test or benchmark evidence.

## Adoption matrix

| Reference | Adopted ForgeOS capability | Current evidence | Boundary |
| --- | --- | --- | --- |
| [OmniRoute](https://github.com/diegosouzapw/OmniRoute) | One local OpenAI-compatible gateway boundary, live catalog discovery, structured preflight, bounded route ladder, provider/model/cost evidence | `backend/localforge/llm/openai_compatible.py`, `backend/localforge/cli/run.py`, `scripts/run_benchmark_v3_only.py`, `backend/tests/test_cloud_compliance.py`, V9 evidence | ForgeOS does not claim that every upstream route is healthy, free, or available at every moment. |
| [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) | Typed bounded Agent Harness, durable supplemental prompts/memory/skills/subagents, evidence-backed refinement, snapshots, bounded subagent lifecycle | `backend/localforge/runtime/agent_harness.py`, `harness_state.py`, `subagents.py`, `backend/tests/test_agent_harness.py`, `test_harness_state.py`, `test_subagents.py` | ForgeOS keeps execution behind its Safety Kernel; it does not embed a trusted arbitrary Python REPL or a daemon that bypasses ForgeOS gates. |
| [NVIDIA OO Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents) | Pythonic method contracts, typed input/output validation, Predict/CodeAct-style strategy selection, bounded retries, context blocks, nested traces | `backend/localforge/runtime/agent_harness.py`, `backend/localforge/observability/tracer.py`, `backend/tests/test_agent_harness.py` | CodeAct is a bounded proposal strategy. It is not permission to execute arbitrary model-generated Python. |
| [LoopX](https://github.com/huangruiteng/loopx) | Lifetime goal identity, server-owned todo frontier, leases, receipts, quota, gates, signals, repair handoffs, pause/resume and worker bridge | `backend/localforge/control_plane/`, `backend/localforge/runtime/run_control.py`, `backend/tests/test_control_plane_v9.py`, V9 PulseBoard evidence | Hash-chain replay, full external PR lifecycle adapters, and production multi-tenant governance remain explicit backlog work. |
| [Matt Pocock skills](https://github.com/mattpocock/skills) | Native declarative `grill-with-docs`, `to-tickets`, and `tdd` skills plus dependency-aware PRD contracts and observable acceptance tests | `backend/localforge/skills/registry.py`, `backend/localforge/prd/`, `backend/tests/test_phase24_25_skills_memory.py`, reference benchmark | These are ForgeOS-native bounded skills; the reference repository is not copied and no claim is made that a human interview is automatically completed without agent/user interaction. |

## Supporting ForgeOS capabilities

The repository also contains local implementations for Graphify AST indexing,
MemPalace JSON memory, rule synthesis, Context7 MCP discovery, Redis cache /
pub-sub / lock primitives, OpenTelemetry-style timeline events, HITL gates,
worktree isolation, and an optional Helm deployment template. These are
separately testable capabilities, not prerequisites for the CPU/local reference
benchmark. A live Context7 service, Redis deployment, Kubernetes cluster, tenant
RLS, or production Docker boundary must not be inferred from a passing benchmark.

## Review verdict

The high-value ideas from all five references are represented without changing
ForgeOS ownership boundaries:

1. OmniRoute remains the only model egress boundary.
2. The Harness adds typed, durable, recoverable context but never replaces the
   domain database, Scheduler, ActionGateway, or Safety Kernel.
3. The control plane owns decisions and evidence; it does not execute shell or
   model actions itself.
4. Skills are data-only manifests unless a validated allowlisted executor is
   explicitly selected; arbitrary imports remain rejected.
5. `PR_READY` is evidence for review. It triggers a human approval gate by
   default; an explicit full-access local release policy may promote it through
   merge and post-merge gates, but never grants production deploy permission.

The reference benchmark report is the authoritative run-level proof. This audit
is the architecture-level map and intentionally distinguishes implemented,
optional, and unfinished capabilities.
