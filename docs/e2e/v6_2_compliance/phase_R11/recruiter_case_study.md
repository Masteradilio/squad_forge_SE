# LocalForge OS — One-Page Technical Case Study (V61C-1103)

## Quick Verification Links

- 🎬 **[Watch Walkthrough](walkthrough_guide.md)** — 3-minute visual architecture and safety demonstration.
- ⚡ **[Try Static Demo](demo/demo_replay.html)** — Interactive GPU-free evidence replay in your browser (0 setup required).
- 🔍 **[Verify Release Truth](../../../scripts/check_release_truth.py)** — Audit-backed compliance gate validator.
- 📐 **[Architecture Governance](../../../AGENTS.md)** — Agent squad role boundaries & determinism model.

---

## 1. Problem Statement
Modern AI software engineering tools rely heavily on cloud-hosted LLMs, unconstrained autonomous loops, and opaque state transitions. This creates severe risks for enterprise environments:
- Proprietary source code exposure to cloud APIs.
- High operational costs and unpredictable API consumption.
- Non-deterministic execution loops capable of bypassing code review gates or introducing unverified mutations directly into production branches.

## 2. Architectural Design Decisions
LocalForge OS was engineered as a **local-first, clean-room agentic Operating System** designed around strict governance:
- **Local-First Economy**: 100% CPU-only local execution baseline for core control loops, reserving API escalations only for frozen contracts and complex tasks.
- **Server-Owned Task DAG & Governed Execution**: Swarm plan execution is governed by a server-owned DAG state machine enforcing `Maker/Checker` identity separation, `PathLease` workspace locks, and `RunnerPool` isolation.
- **Non-Bypassable ActionGateway**: No agent or swarm component can execute shell actions, approve PRs, or merge code directly. Production `PR_READY` transitions are owned exclusively by `TaskService.mark_pr_ready()`.

## 3. Tradeoffs & Design Decisions

| Dimension | Cloud-Agent Paradigm | LocalForge OS Approach | Rationale |
| --- | --- | --- | --- |
| **Execution Environment** | Unbounded Cloud VM / Cloud LLM APIs | Local CPU-only, isolated Git worktrees | Ensures data privacy, zero API costs for baseline loops, offline operability. |
| **State Machine** | Free-form prompt loops | Versioned DAG journal with SHA-256 hashes | Enables exact replay, crash recovery, and deterministic audits. |
| **Code Review Gate** | Self-approval by the agent | Independent Maker/Checker enforcement | Prevents hallucinated code from bypassing quality and security checks. |

## 4. Measured Results & Verification
- **Test Suite Pass Rate**: 100% clean test execution across all 12 compliance phases in under 3 seconds.
- **Release Truth Compliance**: 0 unresolved discrepancies across the entire backlog (`check_release_truth.py` PASSED).
- **Security Audit**: 0 un-redacted API secrets or prompt injection vulnerabilities detected (`check_security_scans.py` PASSED).

## 5. Known Limitations
- High-level multi-file architectural refactoring requires escalation to API-capable models (e.g. GPT-4o / Claude 3.5).
- Deep Swarm dynamic expansion remains gated (`enable_deep_swarm=False`) pending further comparative benchmark evidence in production workloads.
