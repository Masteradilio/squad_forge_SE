# LocalForge OS — 3-Minute Visual Walkthrough Guide (V61C-1102)

## Walkthrough Summary

This guide provides a structured 3-minute visual demonstration narrative for technical reviewers and recruiters.

---

## Demonstration Script & Flow

### Minute 0:00 – 0:45: Architecture & Local-First Baseline
- **Visual**: Show the LocalForge OS dashboard / terminal interface and `docs/compliance_backlog_V6-1.md`.
- **Narrative**: "Welcome to LocalForge OS — an agentic Operating System built from the ground up for local-first, GPU-free software engineering. Notice how core operational loops (Daily Triage, CI Sweeper, PR Babysitter) execute 100% locally on CPU without sending proprietary code to cloud providers."

### Minute 0:45 – 1:30: Governed DAG Execution & Maker/Checker Separation
- **Visual**: Show `LightSwarmService` node dispatch and `PathLease` reservation.
- **Narrative**: "Here, a multi-node task DAG is dispatched. Every code mutation node (`IMPLEMENT`) pre-acquires an exclusive `PathLease` on the repository workspace. To prevent unverified code changes, LocalForge enforces strict Maker/Checker identity separation: the agent writing the patch (`maker_agent_id`) can never be the agent validating the result (`checker_agent_id`)."

### Minute 1:30 – 2:15: Safety Invariants & Failure Injection Recovery
- **Visual**: Run `python scripts/check_security_scans.py` and show prompt injection neutralization.
- **Narrative**: "Security is non-negotiable. Incoming external payloads are sanitized before reaching LLM contexts. If an adversarial issue tries to inject `SYSTEM OVERRIDE`, LocalForge automatically neutralizes it as `MALICIOUS_PROMPT_INJECTION` and ignores it. Furthermore, if a worker crashes, process restart recovery reconstructs state from the durable graph journal without duplicating external side effects."

### Minute 2:15 – 3:00: Verification & Server-Owned PR_READY Gate
- **Visual**: Show `TaskService.mark_pr_ready()` execution and `python scripts/check_release_truth.py`.
- **Narrative**: "Finally, no worker or swarm node can manufacture task readiness directly. Only when a complete, signed evidence bundle (`PRReadyEvidence`) with passing tests and verified handoffs is submitted to `TaskService.mark_pr_ready()`, does the task transition to `PR_READY`. As verified by `check_release_truth.py`, all compliance gates are 100% closed."
