# LocalForge OS - PRD.md

> Version: 0.5
> Status: Open-source alpha product contract
> Intended readers: OpenAI Codex, Google Antigravity, local coding agents, human maintainer
> Project type: clean-room reimplementation inspired by public open-source agent orchestration systems
> Product owner: Adilio Farias
> Next companion document: MASTER_BACKLOG.md

---

## 0. Reader Contract for Coding Agents

This document is the source of product and architecture truth for LocalForge OS.

Read this document fully on first pass. On later passes, use the section index and only reload the section relevant to the task being implemented.

Do not copy code, database schemas, UI layouts, function names, file structures, prompts, or internal protocols from the reference repositories. The reference repositories are provided so implementation agents can understand proven behavior, edge cases, and architectural trade-offs. Implement LocalForge OS as an original clean-room system.

If a referenced repository solves a problem well, reproduce the behavior at the product or protocol level using original code, original names, original schemas, and original tests.

Do not implement any tasks from this PRD unless they are listed in MASTER_BACKLOG.md. This PRD defines product direction, architecture, constraints, and acceptance principles.

---

## 1. Token-Saving Section Index

Use this table when working on one part of the system.

| Section | Purpose | Read when implementing |
|---|---|---|
| 0 | Reader contract | Always before work |
| 2 | Product vision | Product behavior, docs, README, landing page |
| 3 | Clean-room policy | Any code inspired by reference repos |
| 4 | Reference contribution map | Architectural ownership boundaries |
| 5 | Source reading list | Research before implementing comparable behavior |
| 6 | Product goals and non-goals | Scope decisions |
| 7 | Target user journeys | UX/API/CLI decisions |
| 8 | System architecture | Backend integration work |
| 9 | Core domain model | Database and service design |
| 10 | Execution lifecycle | Scheduler, daemon, task runner |
| 11 | Agent runtime | Local models, tools, subagents, skills |
| 12 | Engineering protocol | Worktrees, roles, handoffs, QA gates |
| 13 | Self-healing | Repair loops, failure classification |
| 14 | Safety kernel | Command permissions, sandboxing, secrets |
| 15 | Git and PR factory | Branches, commits, PR artifacts |
| 16 | Frontend product | Dashboard, mission control, PR review |
| 17 | CLI | Commands and automation surface |
| 18 | API/events | Backend API and WebSocket/SSE contracts |
| 19 | Storage | SQLite/Postgres, filesystem, artifacts |
| 20 | Local model support | Ollama/vLLM/OpenAI-compatible adapters |
| 21 | Observability | Logs, audit, metrics, replay |
| 22 | Configuration | Project config and policy config |
| 23 | Security and privacy | Local-first safety rules |
| 24 | Quality gates | Definition of done for agent output |
| 25 | Implementation order | Backend/frontend sequencing only |
| 26 | Acceptance criteria | Product-level acceptance |
| 27 | Glossary | Terms |

---

## 2. Product Vision

LocalForge OS is a local-first autonomous software engineering operating system.

It converts a PRD and backlog into small, testable engineering tasks. It assigns those tasks to local AI agents running on the user's machine, coordinates work in isolated sandboxes and Git worktrees, executes tests, performs bounded self-repair, and opens human-reviewable Pull Requests.

The human remains the final reviewer and merger to `main`. LocalForge OS may create branches and PRs but must not merge to `main` automatically.

Product promise:

> Transform PRD.md into reviewable Pull Requests using local models, safe automation, worktrees, tests, evidence artifacts, and autonomous self-healing.

Primary mode:

```bash
localforge import-prd PRD.md
localforge plan
localforge run --unattended
localforge prs
```

### 2.1 V5 architecture amendment

Local-first describes ownership, deployment, and the default privacy boundary; it does not
require every model call to run locally. The control plane, database, policies, worktrees,
artifacts, and audit log remain on the user's machine.

Execution is economy-aware:

- deterministic checks and local models handle bounded, verifiable work;
- configured API models may receive scoped task evidence for architecture, semantic repair,
  or high-risk review;
- zero-egress users can disable API lanes and accept reduced task coverage;
- every paid or remote call must be budgeted, attributed, and visible in the audit ledger.

The core product is the contract, policy, routing, evidence, and review system—not a claim
that small local models can autonomously complete every software project.

Expected evening result after an unattended run:

- completed tasks have PRs ready for review;
- blocked tasks have precise blocker reports;
- failed tasks are safe-reverted or isolated;
- no destructive action occurred outside the configured workspace;
- every PR includes tests, risks, changed files, and reasoning artifacts.

---

## 3. Clean-Room Reimplementation Policy

LocalForge OS must be built as an original product.

Implementation agents may read public repositories, READMEs, docs, and selected code to understand:

- what user-facing behavior works;
- what state machines are necessary;
- what edge cases exist;
- what safety measures are important;
- what abstractions are useful.

Implementation agents must not:

- copy code;
- copy tests verbatim;
- copy UI layout or styling;
- copy database schema exactly;
- copy prompts or role instructions verbatim;
- copy function/class/module names when they are specific to the reference project;
- copy configuration formats wholesale;
- create a fork-based derivative.

Implementation agents must:

- write original code;
- create original data models;
- use original names unless they are generic industry terms;
- create original tests based on LocalForge requirements;
- cite reference behavior only in developer notes, not in product claims;
- keep a `docs/clean-room-notes.md` file explaining design inspiration at a high level without copied code.

Legal note: this PRD is not legal advice. Treat repositories with unclear licenses conservatively.

---

## 4. Reference Contribution Map

Each reference repository contributes only one primary concept area to avoid functional redundancy.

| Reference | LocalForge role | What to learn | What not to copy |
|---|---|---|---|
| DeerFlow | Agent Runtime Kernel | Long-horizon runtime, lead agent, subagents, sandbox, skills, memory, context compression, tool-call recovery | Exact LangGraph graph, source code, prompts, UI, API structure |
| SwarmForge | Engineering Protocol | Role-based engineering workflow, worktrees, durable handoffs, batch/task receive modes, QA gates | Babashka scripts, exact handoff file format, role prompt text |
| Multica | Engineering Control Plane | Issues, agents as teammates, local daemon, workspaces, task lifecycle, comments, metadata, runtime detection | Server schema, Go implementation, UI, exact CLI |
| Paperclip | Governance Layer | Org chart, heartbeats, budgets, goal ancestry, approvals, pause/terminate, immutable audit | Business-company metaphor, UI, server code, exact plugin model |
| Ollama | Local Model Gateway | OpenAI-compatible local API, model listing, chat, JSON mode, tools, streaming | N/A; integrate through documented API |

Design rule:

- If a feature belongs to task/project management, model it after Multica-like concepts.
- If a feature belongs to governance, model it after Paperclip-like concepts.
- If a feature belongs to runtime intelligence, model it after DeerFlow-like concepts.
- If a feature belongs to engineering workflow discipline, model it after SwarmForge-like concepts.

---

## 5. Required Source Reading List for Codex/Antigravity

These URLs are for behavioral study only. Do not copy source code.

### 5.1 SwarmForge - Engineering Protocol Reference

Purpose: understand role-based engineering packs, worktree orchestration, and durable handoffs.

Read first:

- https://github.com/unclebob/swarm-forge
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/handoff-protocol.md

Read code for behavior and edge cases:

- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/swarmforge.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/handoffd.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/swarm_handoff.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/ready_for_next.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/done_with_current.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/ready_for_next_task.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/ready_for_next_batch.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/done_with_current_task.bb
- https://github.com/unclebob/swarm-forge/blob/main/swarmforge/scripts/done_with_current_batch.bb

Read workflow topology examples:

- https://github.com/unclebob/swarm-forge/blob/two-pack/swarmforge/swarmforge.conf
- https://github.com/unclebob/swarm-forge/blob/four-pack/swarmforge/swarmforge.conf
- https://github.com/unclebob/swarm-forge/blob/six-pack/swarmforge/swarmforge.conf
- https://github.com/unclebob/swarm-forge/tree/six-pack/swarmforge/roles
- https://github.com/unclebob/swarm-forge/tree/six-pack/swarmforge/constitution/articles

LocalForge implementation guidance:

- Implement an original `EngineeringPipeline` abstraction.
- Implement original task/role handoff records in the database, not SwarmForge's exact files.
- Use Git worktrees or safe branch directories for isolation.
- Preserve the behavioral idea: agents do not directly message each other; they emit structured handoff artifacts consumed by the scheduler.

### 5.2 Multica - Engineering Control Plane Reference

Purpose: understand issues, local daemon, workspaces, runtime registration, comments, metadata, and agent teammate UX.

Read first:

- https://github.com/multica-ai/multica
- https://github.com/multica-ai/multica/blob/main/CLI_AND_DAEMON.md
- https://github.com/multica-ai/multica/blob/main/SELF_HOSTING.md
- https://github.com/multica-ai/multica/blob/main/SELF_HOSTING_AI.md

Read code/directories for behavior and edge cases:

- https://github.com/multica-ai/multica/tree/main/server
- https://github.com/multica-ai/multica/tree/main/server/cmd
- https://github.com/multica-ai/multica/tree/main/server/internal
- https://github.com/multica-ai/multica/tree/main/server/internal/daemon
- https://github.com/multica-ai/multica/tree/main/server/internal/daemonws
- https://github.com/multica-ai/multica/tree/main/server/internal/scheduler
- https://github.com/multica-ai/multica/tree/main/server/internal/realtime
- https://github.com/multica-ai/multica/tree/main/server/internal/issueguard
- https://github.com/multica-ai/multica/tree/main/server/internal/skill
- https://github.com/multica-ai/multica/tree/main/server/internal/service
- https://github.com/multica-ai/multica/tree/main/server/internal/storage
- https://github.com/multica-ai/multica/tree/main/apps
- https://github.com/multica-ai/multica/tree/main/packages

LocalForge implementation guidance:

- Implement an original project/issue/agent control plane.
- Implement issue comments and metadata because long-running agents need compact context retrieval.
- Implement a local daemon that registers local runtimes and sends heartbeats.
- Do not implement SaaS/cloud features in MVP.
- Do not use Multica's modified license code.

### 5.3 Paperclip - Governance Layer Reference

Purpose: understand agent hierarchy, heartbeat, budgets, audit, governance, approvals, and goal ancestry.

Read first:

- https://github.com/paperclipai/paperclip
- https://github.com/paperclipai/paperclip/blob/master/README.md
- https://github.com/paperclipai/paperclip/blob/master/ROADMAP.md
- https://github.com/paperclipai/paperclip/blob/master/SECURITY.md

Read code/directories for behavior and edge cases:

- https://github.com/paperclipai/paperclip/tree/master/server/src
- https://github.com/paperclipai/paperclip/tree/master/server/src/routes
- https://github.com/paperclipai/paperclip/tree/master/server/src/services
- https://github.com/paperclipai/paperclip/tree/master/server/src/storage
- https://github.com/paperclipai/paperclip/tree/master/server/src/realtime
- https://github.com/paperclipai/paperclip/tree/master/server/src/secrets
- https://github.com/paperclipai/paperclip/blob/master/server/src/board-claim.ts
- https://github.com/paperclipai/paperclip/blob/master/server/src/runtime-api.ts
- https://github.com/paperclipai/paperclip/blob/master/server/src/dev-runner-worktree.ts
- https://github.com/paperclipai/paperclip/blob/master/server/src/worktree-config.ts
- https://github.com/paperclipai/paperclip/tree/master/tools/agent-shim
- https://github.com/paperclipai/paperclip/tree/master/ui

LocalForge implementation guidance:

- Implement governance as safety and execution control, not as "AI company management."
- Implement heartbeats, budgets, pause/terminate, approval gates, and audit log.
- Implement goal ancestry from PRD -> epic -> task -> run -> PR.
- Do not copy Paperclip's UI or business metaphor.

### 5.4 DeerFlow - Runtime Kernel Reference

Purpose: understand long-running runtime, lead agent, subagents, sandbox, skills, memory, and context engineering.

Read first:

- https://github.com/bytedance/deer-flow
- https://github.com/bytedance/deer-flow/blob/main/README.md
- https://github.com/bytedance/deer-flow/blob/main/backend/README.md
- https://github.com/bytedance/deer-flow/blob/main/config.example.yaml
- https://github.com/bytedance/deer-flow/blob/main/Install.md

Read code/directories for behavior and edge cases:

- https://github.com/bytedance/deer-flow/tree/main/backend/src/agents
- https://github.com/bytedance/deer-flow/tree/main/backend/src/agents/lead_agent
- https://github.com/bytedance/deer-flow/tree/main/backend/src/agents/middlewares
- https://github.com/bytedance/deer-flow/tree/main/backend/src/agents/memory
- https://github.com/bytedance/deer-flow/tree/main/backend/src/sandbox
- https://github.com/bytedance/deer-flow/tree/main/backend/src/subagents
- https://github.com/bytedance/deer-flow/tree/main/backend/src/skills
- https://github.com/bytedance/deer-flow/tree/main/backend/src/tools
- https://github.com/bytedance/deer-flow/tree/main/backend/src/gateway
- https://github.com/bytedance/deer-flow/tree/main/backend/src/models
- https://github.com/bytedance/deer-flow/tree/main/skills/public
- https://github.com/bytedance/deer-flow/tree/main/frontend

LocalForge implementation guidance:

- Implement an original local runtime optimized for engineering tasks.
- Use the lead-agent/subagent pattern, but name and structure it differently.
- Implement sandbox providers with strict safety defaults.
- Implement memory as project-local engineering memory, not general personal memory first.
- Implement skills as versioned engineering procedures.

### 5.5 Ollama and Local Models

Purpose: implement local LLM support through a stable adapter.

Read:

- https://docs.ollama.com/api/openai-compatibility
- https://docs.ollama.com/api/anthropic-compatibility
- https://docs.ollama.com/api
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/tags

LocalForge implementation guidance:

- Use OpenAI-compatible client interface where possible.
- Support Ollama base URL `http://localhost:11434/v1/`.
- Support model discovery.
- Support structured JSON output validation.
- Support streaming.
- Support tool-call fallback when local models fail to comply.

---

## 6. Product Goals and Non-Goals

### 6.1 Goals

LocalForge OS must:

1. Import `PRD.md` and optionally `BACKLOG.md`.
2. Convert PRD into epics, tasks, dependencies, acceptance criteria, and risk levels.
3. Run entirely on the user's machine.
4. Use local models through Ollama or any OpenAI-compatible local endpoint.
5. Assign tasks to local agents with specialized roles.
6. Execute tasks in isolated worktrees and sandboxes.
7. Run tests and quality gates automatically.
8. Attempt bounded self-repair when tests fail.
9. Open PRs or prepare branch artifacts for human review.
10. Provide a web dashboard/desktop-like mission control UI.
11. Provide a CLI for automation and debugging.
12. Provide full audit logs and replayable runs.
13. Never merge to `main` automatically.
14. Never perform destructive actions outside allowed workspace boundaries.

### 6.2 Non-Goals

LocalForge OS must not initially:

1. Become a SaaS product.
2. Depend on Codex, Antigravity, Claude, or cloud agents at runtime.
3. Replace GitHub/GitLab code review.
4. Build a full IDE from scratch.
5. Guarantee that all tasks can be completed autonomously.
6. Run arbitrary shell commands without safety mediation.
7. Do production deploys.
8. Handle secrets beyond detection/redaction/protection.
9. Execute tasks against production databases.
10. Implement mobile app in MVP.

### 6.3 Runtime Constraint

Codex and Antigravity may be used to implement LocalForge OS during development. They must not be runtime dependencies of LocalForge OS.

---

## 7. Target User Journeys

### 7.1 Morning Unattended Run

1. User writes or updates `PRD.md`.
2. User runs `localforge import-prd PRD.md`.
3. LocalForge proposes epics and tasks.
4. User reviews or accepts generated plan.
5. User runs `localforge run --unattended`.
6. Agents work during the day.
7. LocalForge opens PRs for completed tasks.
8. User reviews PRs at night.

### 7.2 PR Review Journey

1. User opens LocalForge dashboard.
2. User sees PR queue grouped by risk.
3. User opens one PR artifact page.
4. User reviews summary, acceptance criteria, tests, changed files, risk report, agent review notes, and repair attempts.
5. User opens PR in GitHub or local IDE.
6. User merges manually or sends adjustment request.

### 7.3 Blocked Task Journey

1. Agent exceeds repair limit or detects ambiguity.
2. Task is marked `BLOCKED`.
3. System saves concise blocker report.
4. Scheduler continues independent tasks.
5. User later resolves ambiguity or edits task.

### 7.4 Safety Intervention Journey

1. Agent requests a risky action.
2. Safety kernel blocks or queues approval.
3. Dashboard shows alert.
4. User can approve once, deny, or adjust policy.
5. Denial is logged and agent must choose a safer path.

---

## 8. System Architecture

### 8.1 Recommended Technology Stack

MVP recommendation:

- Backend: Python 3.12 + FastAPI
- Agent runtime: Python async services
- CLI: Python Typer or Click
- Database: SQLite for single-user MVP; PostgreSQL optional after MVP
- Queue: database-backed queue in MVP; Redis optional later
- Frontend: Next.js + React + TypeScript
- Realtime: WebSocket or Server-Sent Events
- Sandbox: Docker provider first; restricted local provider for trusted workflows
- Git: system Git CLI wrapped by a safe adapter
- Local LLM: Ollama/OpenAI-compatible adapter
- Packaging: local web app first; Tauri desktop later

Rationale:

- Python is appropriate for agent runtime, local model adapters, and sandbox orchestration.
- FastAPI exposes a simple local API for frontend and CLI.
- Next.js gives a strong dashboard UX without building a full IDE.
- SQLite avoids infrastructure overhead in the first usable version.
- Docker sandbox is safer than host-shell execution.

### 8.2 High-Level Components

```text
LocalForge OS
├── CLI
├── Local API Server
├── Web Dashboard
├── PRD Compiler
├── Control Plane
├── Governance Engine
├── Scheduler
├── Agent Runtime Kernel
├── Model Router
├── Skill Registry
├── Safety Kernel
├── Sandbox Manager
├── Git Worktree Manager
├── Engineering Protocol Engine
├── Self-Healing Engine
├── PR Factory
├── Artifact Store
├── Audit Log
└── Observability / Replay
```

### 8.3 Component Responsibilities

#### CLI

Runs project setup, PRD import, plan generation, unattended execution, status, logs, pause/resume, and PR listing.

#### Local API Server

Serves project state, run state, tasks, events, artifacts, models, policies, and frontend actions.

#### Web Dashboard

Provides Mission Control, PRD Studio, Agent Manager, Safety Center, Run Timeline, PR Review Center, Models, Skills, Memory, Worktrees, and Settings.

#### PRD Compiler

Reads product documents and emits epics, tasks, dependencies, acceptance criteria, risk estimates, and implementation hints.

#### Control Plane

Manages projects, epics, tasks, agents, squads, runs, comments, metadata, statuses, and events.

#### Governance Engine

Manages policies, budgets, heartbeats, approvals, pause/terminate, risk escalation, and audit enforcement.

#### Scheduler

Selects runnable tasks, respects dependencies, concurrency, resource budgets, model availability, and safety state.

#### Agent Runtime Kernel

Coordinates lead agents and subagents, tool calls, skills, memory, context compression, and long-running sessions.

#### Model Router

Maps role and task type to local model profile.

#### Skill Registry

Stores reusable engineering procedures.

#### Safety Kernel

Approves, rejects, or queues actions based on policy.

#### Sandbox Manager

Creates isolated filesystem and shell execution contexts.

#### Git Worktree Manager

Creates branches, worktrees, checkpoints, diffs, commits, and cleanup.

#### Engineering Protocol Engine

Runs role-based pipelines such as specifier -> coder -> tester -> reviewer -> PR writer.

#### Self-Healing Engine

Classifies failures and executes bounded repair strategies.

#### PR Factory

Creates PR branches, PR descriptions, evidence artifacts, and review summaries.

#### Artifact Store

Stores plans, diffs, test logs, risk reports, screenshots, summaries, PR notes, and replay metadata.

#### Audit Log

Records every material decision and tool action.

---

## 9. Core Domain Model

Use original schema names in implementation. The names below define product concepts, not required table names.

### 9.1 Project

A repository or software product managed by LocalForge.

Fields:

- id
- name
- root_path
- default_branch
- remote_url
- localforge_config_path
- created_at
- updated_at

### 9.2 ProductDocument

Represents PRD, backlog, architecture notes, or user-supplied docs.

Fields:

- id
- project_id
- kind: prd | backlog | architecture | policy | note
- path
- content_hash
- imported_at
- parsed_summary

### 9.3 Epic

A major product objective derived from PRD or manually created.

Fields:

- id
- project_id
- title
- summary
- source_document_id
- priority
- status
- acceptance_summary

### 9.4 Task

A small engineering work item.

Fields:

- id
- project_id
- epic_id
- key
- title
- description
- acceptance_criteria
- dependency_task_ids
- risk_level
- status
- assigned_agent_id
- metadata
- created_at
- updated_at

Allowed statuses:

```text
BACKLOG
READY
CLAIMED
PLANNING
IMPLEMENTING
TESTING
REPAIRING
REVIEWING
PR_READY
BLOCKED
FAILED_SAFE
DONE
CANCELLED
```

### 9.5 Agent

A logical worker, not necessarily a single model.

Fields:

- id
- name
- role
- model_profile_id
- active
- max_concurrent_tasks
- permissions_profile_id
- heartbeat_at
- current_task_id

Roles:

- Planner
- Specifier
- Coder
- Tester
- Fixer
- Reviewer
- Architect
- Hardener
- PRWriter
- SafetyAuditor

### 9.6 Run

A bounded execution session.

Fields:

- id
- project_id
- mode: interactive | unattended | dry_run
- status
- started_at
- ended_at
- initiated_by
- resource_limits
- summary

### 9.7 TaskRun

An attempt to complete one task.

Fields:

- id
- run_id
- task_id
- status
- worktree_path
- branch_name
- sandbox_id
- attempt_count
- started_at
- ended_at
- final_summary

### 9.8 Handoff

A structured transition from one role to another.

Fields:

- id
- task_run_id
- from_role
- to_role
- kind: plan | implementation | test_result | review | repair_request | pr_ready | blocker
- payload_json
- priority
- status
- created_at
- consumed_at

### 9.9 Artifact

Evidence object produced during execution.

Types:

- PlanArtifact
- DiffArtifact
- TestArtifact
- LintArtifact
- TypecheckArtifact
- RiskArtifact
- ReviewArtifact
- RepairArtifact
- PRArtifact
- BlockerArtifact
- ReplayArtifact

### 9.10 Policy

Execution rules.

Examples:

- allowed commands;
- blocked commands;
- max diff lines;
- max files touched;
- require approval for dependency installation;
- require approval for migration changes;
- max repair attempts;
- max run duration;
- allowed directories.

### 9.11 AuditEvent

Immutable append-only event.

Fields:

- id
- project_id
- run_id
- task_id
- actor_type
- actor_id
- event_type
- payload_redacted
- created_at

---

## 10. Execution Lifecycle

### 10.1 Project Initialization

```bash
localforge init
```

Creates:

```text
.localforge/
  config.yaml
  policies/
  skills/
  memory/
  artifacts/
  runs/
  logs/
```

Adds recommended `.gitignore` entries.

### 10.2 PRD Import

```bash
localforge import-prd PRD.md
```

Steps:

1. Parse Markdown.
2. Extract product goals.
3. Extract user stories and requirements.
4. Generate epics.
5. Generate small tasks.
6. Generate dependencies.
7. Generate acceptance criteria.
8. Assign risk levels.
9. Save all generated items as draft.
10. Require user approval before unattended run.

### 10.3 Run Startup

```bash
localforge run --unattended
```

Steps:

1. Validate project cleanliness or create checkpoint.
2. Validate local models are reachable.
3. Validate safety policy.
4. Validate Git remote and default branch.
5. Start scheduler.
6. Start daemon heartbeat.
7. Start realtime event stream.
8. Begin task execution.

### 10.4 Task Execution

For each task:

1. Claim task.
2. Create worktree and branch.
3. Create sandbox.
4. Load task context.
5. Run Specifier.
6. Run Coder.
7. Run Tester.
8. If tests fail, enter Self-Healing.
9. Run Reviewer.
10. Run PRWriter.
11. Create PR or PR artifact.
12. Mark task `PR_READY`.

### 10.5 Run Shutdown

A run ends when:

- all runnable tasks are `PR_READY`, `BLOCKED`, `FAILED_SAFE`, or `DONE`;
- user pauses or terminates run;
- safety policy stops the run;
- resource budget is exhausted;
- time limit is reached.

Shutdown must:

- stop agent loops;
- save summaries;
- save audit events;
- leave worktrees intact for PR_READY tasks;
- cleanup only safe generated artifacts;
- never delete source changes for PR_READY tasks.

---

## 11. Agent Runtime

### 11.1 Lead Agent Pattern

Each task run has one coordinator agent.

Responsibilities:

- read task;
- select skills;
- spawn role-specific subagents;
- summarize progress;
- enforce context budget;
- request safe tool actions;
- stop on bounded failure.

### 11.2 Subagents

Subagents are role-specialized workers.

Required subagent types:

- Specifier: turns task into implementation spec and acceptance checks.
- Coder: edits code.
- Tester: runs tests and summarizes failures.
- Fixer: performs bounded repair.
- Reviewer: reviews diff and risks.
- PRWriter: creates PR summary and evidence bundle.

Subagent constraints:

- each subagent gets scoped context;
- subagents do not see unrelated tasks;
- subagents do not execute tools directly;
- all tool use goes through Safety Kernel;
- completed subagent output is summarized and stored as artifact.

### 11.3 Skills

Skills are reusable procedures loaded only when relevant.

Examples:

```text
skills/
  python-pytest/
  fastapi-endpoint/
  nextjs-component/
  sqlalchemy-migration/
  react-testing-library/
  github-pr-writer/
  git-worktree-debugging/
```

Skill file format must be original. It may be Markdown or YAML+Markdown.

Skill requirements:

- name;
- purpose;
- trigger conditions;
- allowed tools;
- expected artifacts;
- failure modes;
- test command hints;
- examples.

### 11.4 Context Engineering

Runtime must avoid unbounded prompt growth.

Strategies:

- use task-local summaries;
- store intermediate files in artifacts;
- compress old tool outputs;
- include only relevant code snippets;
- retrieve comments by recent thread or task scope;
- keep structured state outside LLM context;
- limit raw logs in prompts.

### 11.5 Memory

MVP memory is project-local, not personal-global.

Store:

- project stack;
- test commands;
- known pitfalls;
- coding conventions;
- previous blocker resolutions;
- model performance statistics;
- user preferences for this project.

Do not store:

- secrets;
- full logs;
- credentials;
- private personal data unrelated to engineering.

---

## 12. Engineering Protocol

### 12.1 Role Pipeline

Default pipeline:

```text
Planner -> Specifier -> Coder -> Tester -> Fixer -> Reviewer -> PRWriter
```

Strict mode pipeline:

```text
Planner -> Specifier -> Coder -> Cleaner -> Architect -> Hardener -> QA -> PRWriter
```

Fast mode pipeline:

```text
Coder -> Tester -> Reviewer -> PRWriter
```

### 12.2 Worktree Isolation

Each task run must use a dedicated branch and worktree.

Example:

```text
.localforge/worktrees/LF-123-auth-user-model/
```

Branch name format:

```text
localforge/<task-key>-<slug>
```

Rules:

- never edit default branch directly;
- never run code changes outside task worktree;
- never mix unrelated tasks in same branch;
- never reuse dirty worktree for a new task without checkpointing.

### 12.3 Handoffs

Handoffs are structured database/artifact records, not free-form chat.

Each handoff must include:

- sender role;
- receiver role;
- task id;
- kind;
- priority;
- summary;
- payload;
- artifact links;
- status.

Handoff kinds:

- `spec_ready`
- `implementation_ready`
- `tests_failed`
- `repair_requested`
- `repair_done`
- `review_requested`
- `review_passed`
- `review_failed`
- `pr_ready`
- `blocked`

### 12.4 Engineering Gates

No task may become `PR_READY` unless:

- branch exists;
- diff is non-empty and relevant;
- acceptance criteria checked;
- tests run or explicitly marked unavailable;
- risk artifact produced;
- reviewer artifact produced;
- PR artifact produced.

---

## 13. Self-Healing

### 13.1 Failure Classification

The Self-Healing Engine must classify failures before repair.

Failure classes:

```text
TEST_ASSERTION_FAILURE
TYPECHECK_FAILURE
LINT_FAILURE
BUILD_FAILURE
DEPENDENCY_MISSING
IMPORT_ERROR
RUNTIME_EXCEPTION
MODEL_BAD_EDIT
CONFLICTING_REQUIREMENT
AMBIGUOUS_REQUIREMENT
COMMAND_BLOCKED_BY_POLICY
SANDBOX_FAILURE
MODEL_TIMEOUT
MODEL_FORMAT_ERROR
GIT_CONFLICT
UNKNOWN_FAILURE
```

### 13.2 Repair Loop

Default repair policy:

```text
max_repair_attempts_per_task: 3
max_same_failure_repeats: 2
max_files_touched_after_failure: 5
max_diff_growth_after_failure: 300 lines
```

Loop:

1. Capture failure.
2. Classify failure.
3. Generate repair plan.
4. Apply minimal fix.
5. Run focused test.
6. If fixed, continue.
7. If repeated, change strategy once.
8. If still failing, revert last risky edit and mark BLOCKED or FAILED_SAFE.

### 13.3 Stop Conditions

Stop repairing when:

- same failure repeats too many times;
- diff grows beyond policy;
- tests become worse;
- agent requests forbidden command;
- requirement ambiguity is detected;
- model output is invalid too many times;
- sandbox is unstable.

### 13.4 Blocker Report

A blocker artifact must include:

- task key;
- exact failing command;
- summarized error;
- attempted fixes;
- current branch/worktree;
- suspected root cause;
- recommended human decision;
- safe next tasks, if any.

---

## 14. Safety Kernel

### 14.1 Principle

Agents do not execute actions directly. They request actions. The Safety Kernel decides.

### 14.2 Action Request Format

Every tool request must be normalized:

```json
{
  "action": "run_command",
  "task_id": "LF-123",
  "worktree": ".localforge/worktrees/LF-123-auth",
  "command": "pytest tests/test_auth.py",
  "declared_purpose": "Run focused tests for auth task",
  "risk": "low"
}
```

### 14.3 Safety Modes

Modes:

- `observe`: agents can only analyze.
- `interactive`: agents request approval for medium/high risk.
- `unattended_conservative`: low-risk actions auto-allowed; medium/high blocked or queued.
- `unattended_trusted`: medium-risk actions auto-allowed only inside sandbox/worktree.
- `dry_run`: no file writes.

MVP default:

```text
unattended_conservative
```

### 14.4 Allowed by Default

Inside task worktree only:

- `git status`
- `git diff`
- `git log`
- `pytest`
- `npm test`
- `pnpm test`
- `ruff`
- `mypy`
- `tsc --noEmit`
- `npm run lint`
- file read/write inside repo
- create local branch
- create commit
- create PR after tests/artifacts

### 14.5 Approval Required

- installing dependencies;
- modifying lockfiles;
- modifying database migrations;
- changing auth/security files;
- touching `.env.example`;
- touching CI/CD config;
- touching Docker/Kubernetes config;
- diff above threshold;
- more than N files touched;
- network access beyond configured remotes.

### 14.6 Always Blocked

- deleting outside project root;
- writing outside allowed workspace;
- reading secrets;
- printing secrets in logs;
- `git push --force`;
- merging to main;
- production deploy;
- destructive database commands;
- changing global system config;
- disabling safety policies.

---

## 15. Git and PR Factory

### 15.1 Branch Creation

Branch format:

```text
localforge/<task-key>-<slug>
```

### 15.2 Commit Rules

Each task should produce small commits.

Commit message format:

```text
<task-key>: <short imperative summary>
```

Examples:

```text
LF-123: add user model validation
LF-123: cover duplicate email rejection
```

### 15.3 PR Creation

PR creation must happen only after engineering gates pass.

PR title:

```text
[LF-123] Add user model validation
```

PR description must include:

- summary;
- task link;
- acceptance criteria;
- changed files;
- tests run;
- risk assessment;
- repair attempts;
- screenshots/appshots if UI;
- known limitations;
- human review checklist.

### 15.4 PR Review Artifacts

Every PR must link to local artifacts:

```text
.localforge/artifacts/runs/<run-id>/tasks/<task-key>/
  plan.md
  diff.patch
  tests.md
  risk.md
  review.md
  repair.md
  pr.md
```

### 15.5 Merge Policy

LocalForge must not merge PRs automatically in MVP.

Human must review and merge.

---

## 16. Frontend Product

The frontend is not just a chatbot. It is a local engineering mission control.

### 16.1 Surfaces

LocalForge should have three user surfaces:

1. CLI
2. Web dashboard / desktop-like local app
3. IDE extension later

MVP requires CLI and web dashboard.

Desktop packaging with Tauri or Electron is post-MVP.

IDE extension is post-MVP.

### 16.2 Navigation

Sidebar:

```text
LocalForge
├── Mission Control
├── PRD & Backlog
├── Agents
├── Runs
├── Pull Requests
├── Worktrees
├── Models
├── Skills
├── Memory
├── Safety
└── Settings
```

### 16.3 Mission Control

Purpose: show whether unattended engineering is safe and productive.

Cards:

- Current Run
- Project Health
- Agent Fleet
- Task Graph
- PR Queue
- Risk Alerts
- System Resources
- Timeline

Example summary:

```text
Project: my-app
Mode: unattended_conservative
Models: gemma4:12b, qwen-coder:7b, tester-small
GPU: 12.4 / 16 GB VRAM
Tasks: 18 total | 5 done | 3 running | 2 blocked | 8 pending
PRs ready: 4
Risk: medium
Last safe checkpoint: 14:32
```

### 16.4 PRD & Backlog Studio

Purpose: import, inspect, edit, split, and approve generated tasks.

Features:

- PRD viewer;
- generated epic list;
- dependency graph;
- task editor;
- acceptance criteria editor;
- risk label editor;
- execution mode selector;
- approve plan button.

### 16.5 Agent Manager

Purpose: observe and control agent roles.

Agent card fields:

- name;
- role;
- model;
- current task;
- state;
- attempt count;
- last action;
- last failure;
- worktree;
- resource usage.

Actions:

- pause agent;
- terminate current task;
- view plan;
- view diff;
- view logs;
- revert last attempt;
- mark blocked.

### 16.6 Runs

Purpose: inspect past and current runs.

Run page includes:

- start/end time;
- mode;
- tasks completed;
- PRs opened;
- blocked tasks;
- failures recovered;
- fatal failures;
- resource usage;
- event timeline;
- replay button.

### 16.7 PR Review Center

Purpose: the evening workflow.

PR cards:

- PR title;
- task key;
- risk level;
- tests passed/failed;
- changed files count;
- diff size;
- repair attempts;
- reviewer confidence;
- open in GitHub button;
- open in IDE button.

PR detail page:

- summary;
- acceptance criteria;
- evidence artifacts;
- tests;
- risk report;
- diff viewer;
- reviewer notes;
- repair history;
- user actions.

Actions:

- open PR;
- rerun tests;
- request agent adjustment;
- mark accepted;
- mark rejected;
- reopen task;
- archive.

### 16.8 Safety Center

Purpose: make autonomy trustworthy.

Shows:

- current safety mode;
- allowed commands;
- approval-required actions;
- blocked actions;
- pending approvals;
- recent blocked actions;
- policy editor;
- kill switch.

Required buttons:

- Pause all agents
- Stop run
- Lock project
- Revert unsafe worktree
- Export audit log

### 16.9 Models

Purpose: manage local model routing.

Shows:

- local provider status;
- available models;
- model profiles;
- role mapping;
- performance stats;
- failure rates.

Example:

```text
planner: gemma4:12b-q4
coder: qwen-coder:7b-q4
tester: small-fast-model
reviewer: gemma4:12b-q4
```

### 16.10 Skills

Purpose: manage engineering procedures.

Features:

- skill list;
- skill detail;
- trigger conditions;
- last used;
- success rate;
- enable/disable;
- edit local skill.

### 16.11 Memory

Purpose: inspect project-local memory.

Must support:

- view extracted facts;
- delete fact;
- pin fact;
- mark stale;
- reload memory;
- export memory.

### 16.12 Worktrees

Purpose: inspect isolated task branches.

Shows:

- task key;
- branch;
- path;
- dirty state;
- last commit;
- PR link;
- cleanup eligibility.

### 16.13 Settings

Includes:

- project paths;
- Git provider;
- default branch;
- PR provider;
- local model endpoint;
- sandbox mode;
- resource limits;
- UI preferences.

---

## 17. CLI

### 17.1 Required Commands

```bash
localforge init
localforge doctor
localforge import-prd PRD.md
localforge plan
localforge run
localforge run --unattended
localforge status
localforge pause
localforge resume
localforge stop
localforge tasks
localforge task get LF-123
localforge prs
localforge logs
localforge replay <run-id>
localforge models list
localforge skills list
localforge safety status
```

### 17.2 CLI Output

All key commands must support:

```bash
--json
--project <path>
--config <path>
```

### 17.3 Doctor Command

`localforge doctor` checks:

- Git installed;
- repo detected;
- default branch detected;
- Ollama/local endpoint reachable;
- models available;
- Docker available if sandbox mode requires it;
- GitHub CLI or token available if PR creation enabled;
- database writable;
- policy valid.

---

## 18. API and Events

### 18.1 API Requirements

Backend API must expose:

- projects;
- documents;
- epics;
- tasks;
- runs;
- task runs;
- agents;
- models;
- skills;
- safety policies;
- action approvals;
- artifacts;
- audit events;
- PRs.

### 18.2 Realtime Events

Use WebSocket or SSE.

Event types:

```text
run.started
run.paused
run.stopped
task.claimed
task.status_changed
agent.heartbeat
agent.action_requested
safety.action_allowed
safety.action_blocked
test.started
test.finished
repair.started
repair.failed
repair.succeeded
pr.created
artifact.created
audit.event
```

### 18.3 Event Design

Events must be:

- append-only;
- replayable;
- small;
- safe-redacted;
- tied to project/run/task when applicable.

---

## 19. Storage

### 19.1 Database

MVP: SQLite.

Later: PostgreSQL.

Store:

- project metadata;
- task graph;
- agents;
- model profiles;
- run state;
- handoffs;
- approvals;
- audit events;
- artifact metadata.

### 19.2 Filesystem

Store large artifacts outside DB.

Path:

```text
.localforge/artifacts/
.localforge/runs/
.localforge/logs/
.localforge/memory/
.localforge/worktrees/
```

### 19.3 Artifact Retention

Default:

- keep PR_READY artifacts until user deletes;
- keep run summaries indefinitely;
- cleanup build outputs safely;
- never delete `.git`;
- never delete source changes without explicit user action.

---

## 20. Local Model Support

### 20.1 Providers

MVP providers:

- Ollama via OpenAI-compatible API
- vLLM/OpenAI-compatible local endpoint

Provider config:

```yaml
models:
  providers:
    - id: ollama
      kind: openai_compatible
      base_url: http://localhost:11434/v1/
      api_key: ollama
```

### 20.2 Model Profiles

```yaml
model_profiles:
  planner:
    provider: ollama
    model: gemma4:12b-q4
    temperature: 0.2
    max_tokens: 4096
  coder:
    provider: ollama
    model: qwen-coder:7b-q4
    temperature: 0.1
    max_tokens: 4096
  tester:
    provider: ollama
    model: small-fast-model
    temperature: 0.0
    max_tokens: 2048
```

### 20.3 Structured Output

All model outputs that drive state transitions must be validated against JSON schemas.

If invalid:

1. ask model to repair JSON once;
2. if still invalid, use fallback parser;
3. if still invalid, mark model output failure;
4. do not mutate state.

### 20.4 Tool Calls

Local models may not reliably follow native tool calling.

Implement fallback:

- JSON action proposals;
- strict parser;
- safety validation;
- repair prompt;
- no direct execution.

---

## 21. Observability and Replay

### 21.1 Logs

Log levels:

- debug;
- info;
- warning;
- error;
- audit.

Never log secrets.

### 21.2 Replay

A run must be replayable from stored events and artifacts.

Replay shows:

- task sequence;
- agent actions;
- safety decisions;
- tests;
- repair attempts;
- PR creation.

### 21.3 Metrics

Track:

- tasks completed;
- tasks blocked;
- average attempts;
- model success rate;
- model invalid output rate;
- test pass rate;
- repair success rate;
- average task duration;
- PR rejection rate;
- safety blocks.

---

## 22. Configuration

### 22.1 Project Config

`.localforge/config.yaml`

Required sections:

```yaml
project:
  name: my-app
  root: .
  default_branch: main

git:
  provider: github
  remote: origin
  create_prs: true

runtime:
  mode: unattended_conservative
  max_parallel_tasks: 1
  max_active_model_calls: 1

sandbox:
  provider: docker
  allow_host_bash: false

models:
  providers: []
  profiles: {}

policies:
  file: .localforge/policies/default.yaml
```

### 22.2 Policy Config

`.localforge/policies/default.yaml`

Sections:

- allowed_commands;
- blocked_commands;
- approval_required_patterns;
- max_diff_lines;
- max_files_touched;
- max_repair_attempts;
- protected_paths;
- allowed_write_roots;
- network_policy.

---

## 23. Security and Privacy

### 23.1 Local-First

LocalForge OS must support a zero-egress configuration that uses only deterministic and local
model lanes. When the user enables an API lane, only the scoped task evidence required by that
lane may leave the machine, and the provider, purpose, token/cost budget, and result must be
recorded in the local audit ledger.

### 23.2 Secrets

The system must:

- detect common secret patterns;
- redact logs;
- prevent agents from reading `.env` by default;
- prevent agents from printing secrets;
- block PRs that include likely secrets.

### 23.3 Sandboxing

Default shell execution should be inside Docker sandbox when available.

Host shell is allowed only in trusted mode and only inside configured project root.

### 23.4 Kill Switch

Always provide:

- CLI kill switch;
- dashboard kill switch;
- signal handler to stop runs safely.

---

## 24. Quality Gates

A task is complete only when:

- acceptance criteria are addressed;
- tests run or justified;
- diff is scoped;
- no protected files changed without approval;
- no secret detected;
- PR artifact exists;
- review artifact exists;
- risk artifact exists.

A PR is review-ready only when:

- branch pushed or local PR artifact created;
- title and description generated;
- tests summarized;
- risks listed;
- human checklist generated.

---

## 25. Recommended Implementation Order

Detailed tasks go in MASTER_BACKLOG.md. This section only defines dependency order.

### 25.1 Backend First

Build first:

1. project config and storage;
2. task model and state machine;
3. CLI skeleton;
4. local model adapter;
5. safety kernel;
6. Git worktree manager;
7. basic task runner;
8. PRD compiler;
9. test runner;
10. self-healing loop;
11. artifact store;
12. PR factory.

Reason: the frontend should display real state, not mocked state.

### 25.2 Frontend Second, But Early Enough

Build initial frontend after the backend can produce:

- projects;
- tasks;
- runs;
- events;
- artifacts.

Initial UI:

1. Mission Control;
2. PRD & Backlog;
3. Runs;
4. Tasks;
5. Safety;
6. Pull Requests.

### 25.3 Advanced Runtime Later

After basic task-to-PR works:

1. subagents;
2. skills;
3. memory;
4. strict pipeline roles;
5. dashboard polish;
6. IDE extension;
7. desktop packaging.

---

## 26. Product-Level Acceptance Criteria

### 26.1 MVP Acceptance

Given a small repository with tests and a PRD containing 3 simple tasks:

- LocalForge imports the PRD;
- creates tasks;
- runs at least one task in a worktree;
- edits code using local model;
- runs tests;
- repairs one simple failure;
- creates branch;
- creates PR artifact;
- updates dashboard;
- records audit events;
- does not touch main branch.

### 26.2 Unattended Acceptance

Given approved tasks with clear acceptance criteria:

- LocalForge runs without user interaction;
- completes independent tasks;
- blocks ambiguous tasks safely;
- never loops indefinitely;
- never executes blocked commands;
- provides evening review summary.

### 26.3 Safety Acceptance

Given an agent requests a forbidden command:

- Safety Kernel blocks it;
- event is logged;
- task continues via safe path or becomes blocked;
- no destructive command executes.

### 26.4 Frontend Acceptance

The user can:

- import PRD;
- approve task plan;
- start unattended run;
- observe agents;
- inspect task status;
- view safety alerts;
- review PR artifacts;
- open PR in GitHub or local path.

---

## 27. Glossary

Agent: A logical worker assigned a role and model profile.

Artifact: Evidence file or structured record produced during execution.

Backlog: Ordered collection of tasks.

Clean-room reimplementation: Original implementation based on observed behavior and public documentation, not copied code.

Control Plane: Project/task/agent management layer.

Engineering Protocol: Role and quality-gate workflow for software tasks.

Goal Ancestry: Relationship from PRD goal to epic to task to run to PR.

Handoff: Structured transfer between roles.

Local Model: LLM running on the user's machine.

Mission Control: Dashboard showing current autonomous engineering state.

PR Factory: Component that creates branches, PR artifacts, and PR descriptions.

Safety Kernel: Policy layer that mediates all tool actions.

Self-Healing: Bounded repair behavior after failures.

Skill: Reusable engineering procedure.

TaskRun: One attempt to complete a task.

Unattended Mode: Execution mode where agents work without user interaction within configured safety limits.

Worktree: Isolated Git working directory for one task or role.
