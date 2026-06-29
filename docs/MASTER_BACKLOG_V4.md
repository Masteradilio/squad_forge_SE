# LocalForge OS - MASTER_BACKLOG_V4.md

> Version: 0.4
> Status: Skill-Based Squad Orchestration
> Date: 2026-06-29
> Continues: `MASTER_BACKLOG.md`, `MASTER_BACKLOG_V2.md`, and `MASTER_BACKLOG_V3.md` phases 1-63
> Companion documents: `LocalForge_OS_PRD.md`, `CHANGELOG.md`

---

## 0. Why This Backlog Exists

V3 successfully proved that LocalForge can use an API-led, economy-first model to execute engineering tasks successfully (e.g., 100% PR_READY for Pomodoro Tracker). However, the definition of agent roles and responsibilities remained hardcoded in Python modules like `context.py` and `squads.py`. 

V4 introduces the **Skill-Based Squad Orchestration** model. It moves away from hardcoded prompts in Python scripts and adopts a clean, deterministic architecture:
1. **Agent Skills Directory**: A central directory where each Squad role is defined by a `SKILL.md`. This gives precise boundaries, goals, and restrictions to each role.
2. **`AGENTS.md`**: A global manifest explaining the role of each squad member and how they interact.
3. **Scrum Master Orchestrator**: The Scrum Master is elevated to a deterministic loop/controller rather than just another LLM call. It parses the PRD, maps tasks, assigns roles based on complexity, and routes execution.
4. **Fallback Memory**: `ModelCapability` will track task success/failure per role to ensure the Orchestrator intelligently escalates without endless loops.
5. **PO Kanban Board**: A real-time, Cline-inspired Kanban frontend so the human Product Owner (PO) can monitor the entire squad's progress.

---

## 1. V4 Architecture Overview

- **PO (Human)**: Provides the PRD, monitors the Kanban board, and reviews PRs.
- **Scrum Master (Orchestrator)**: Deterministic core that runs the squad. Compiles PRD into backlog, maps task complexity, creates `git worktree` isolation, and handles model fallback logic.
- **Chief Engineer (API Model)**: Writes architecture, complex scripts, and unblocks hard failures.
- **Developer / QA / etc. (Local Models)**: Handle bounded, simpler tasks to preserve API tokens and reduce costs.

---

## 2. Implementation Phases

| Phase | Title | Primary Outcome |
| --- | --- | --- |
| Phase 64 | `AGENTS.md` and Skill Directory Architecture | `AGENTS.md` and role-specific `SKILL.md` files are created. |
| Phase 65 | Role Prompt Refactoring (`context.py`) | Agent context is dynamically loaded from `SKILL.md` files instead of hardcoded strings. |
| Phase 66 | Scrum Master Orchestrator (`squads.py`) | The orchestrator loop deterministically routes tasks based on the backlog. |
| Phase 67 | Fallback Memory (`ModelCapability`) | The engine avoids fallback loops by persisting failure state per task/role. |
| Phase 68 | PO Kanban Board (Real-time Frontend) | A Web UI is provided for the PO to monitor tasks and PRs in real time. |
| Phase 69 | V4 Architecture Regression and E2E | All benchmarks pass under the new architecture. |

---

### Phase 64 - `AGENTS.md` and Skill Directory Architecture
- Create `docs/AGENTS.md` or place it at the project root depending on standard conventions, defining the squad.
- Create an `agents/skills/` directory structure.
- Define a `SKILL.md` for each major role (Scrum Master, Chief Engineer, Developer, Reviewer, QA).
- *Validation: Ensure files exist and document precise constraints.*

### Phase 65 - Role Prompt Refactoring (`context.py`)
- Refactor `backend/localforge/pipeline/context.py` to read directly from the new `skills` directory.
- Remove hardcoded string prompts for roles.
- Ensure `RoleContext` properly parses and injects the `SKILL.md` content into the agent system prompt.
- *Validation: Unit tests for `context.py` pass and properly load external MD files.*

### Phase 66 - Scrum Master Orchestrator (`squads.py` & `engine.py`)
- Refactor `backend/localforge/cli/squad.py` and `engine.py` to position the Scrum Master as the deterministic driver of the workflow.
- The Orchestrator must:
  1. Parse the PRD.
  2. Map tasks to specific roles (by complexity).
  3. Execute via `git worktree` for isolation.
- *Validation: A dummy PRD is successfully decomposed and assigned to roles.*

### Phase 67 - Fallback Memory (`ModelCapability`)
- Update `backend/localforge/models/domain.py` and relevant DB models to persist task failures.
- Implement logic where if a local model fails a task repeatedly, it escalates to the Chief Engineer (API).
- Record this in `ModelCapability` so the system learns the capacity limit of the local model for that specific project or task pattern.
- *Validation: Simulated failure forces an escalation which is recorded in the DB.*

### Phase 68 - PO Kanban Board (Real-time Frontend)
- Create a lightweight frontend dashboard (HTML/JS/Vanilla CSS or via existing React if applicable).
- Connect the dashboard to the backend SQLite DB (or JSON events) to reflect real-time task statuses (TODO, IN PROGRESS, REVIEW, PR_READY).
- Provide visual distinction between roles executing the tasks (e.g., Local vs API).
- *Validation: The dashboard successfully displays a live run.*

### Phase 69 - V4 Architecture Regression and E2E (COMPLETED)
- Run the full benchmark suite (e.g., `run_benchmark_v3_only.py` updated for V4).
- Ensure V4 maintains or exceeds the 100% PR_READY success rate achieved in V3.
- Update `CHANGELOG.md` reflecting the V4 migration completion.
- Synchronize with the final GitHub repository structure.
- *Validation: All benchmarks return ACCEPTED. Final user approval obtained.*

