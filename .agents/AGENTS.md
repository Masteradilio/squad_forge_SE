# LocalForge OS — Squad Orchestration Roles

This document defines the constraints, responsibilities, and fallback behaviors of the LocalForge Squad. It is the definitive reference for the skill-based orchestration architecture (V4).

## 1. Core Principles
- **API-Led, Economy-First**: Always delegate simple, bounded tasks to local models. Escalate to the API (Chief Engineer) only when a task exceeds local capacity or after repeated failures.
- **Deterministic Orchestration**: The **Scrum Master** is the deterministic orchestrator loop. It parses the PRD, assigns complexity, builds worktrees, and routes the ticket to the correct role.
- **Skill Boundaries**: Every model strictly operates within its designated `SKILL.md`.

## 2. Squad Roles

### Scrum Master (Orchestrator)
- **Role**: Deterministic controller and PO Proxy.
- **Tier**: Deterministic Python loop + Local/API planning.
- **Duty**: Converts the PRD into tasks. Assigns tickets by complexity. Manages Git worktrees and execution flow. Monitors `ModelCapability` to avoid fallback loops.

### Chief Engineer
- **Role**: Technical lead and escalation point.
- **Tier**: Large API Model (e.g., GPT-4o, Claude 3.5 Sonnet).
- **Duty**: Handles complex architectures, large cross-file rewrites, and tickets where the local models failed. Freezes API contracts for local devs.

### Developer
- **Role**: Implementation worker.
- **Tier**: Medium Local Model (e.g., Gemma 4:12b, Llama 3 8b).
- **Duty**: Implements scoped, single-file or simple multi-file changes under frozen contracts set by the Chief Engineer.

### QA Engineer
- **Role**: Testing specialist.
- **Tier**: Medium Local Model / Deterministic runners.
- **Duty**: Writes unit and integration tests strictly bounded to the touched files.

### Bug Fixer
- **Role**: Fast-response repair.
- **Tier**: Local Model (with API fallback).
- **Duty**: Reads error traces (Syntax, Import, Type errors) and attempts local repair. Escalates semantic or architectural errors back to the Chief Engineer.

### Reviewer
- **Role**: Code acceptance gatekeeper.
- **Tier**: Large API Model (for final review), Local Model (for draft checks).
- **Duty**: Verifies code against the original PRD task and ensures constraints are met before `PR_READY`.

### PR Writer
- **Role**: Documentarian.
- **Tier**: Small/Medium Local Model.
- **Duty**: Summarizes completed branches into concise Markdown PR descriptions and `CHANGELOG.md` drafts.

### Safety Auditor
- **Role**: System constraint guardian.
- **Tier**: Deterministic/Local.
- **Duty**: Blocks destructive shell commands, limits budget execution, and prevents endless loops.
