# LocalForge OS — MASTER_BACKLOG.md

> Version: 0.1
> Status: Implementation backlog for coding agents
> Companion document: `LocalForge_OS_PRD.md`
> Required root document: `CHANGELOG.md`
> Intended executors: OpenAI Codex, Google Antigravity, local coding agents, human maintainer
> Runtime product constraint: LocalForge OS must not depend on Codex, Antigravity, Claude, or cloud agents at runtime.

---

## 0. Mandatory Operating Instructions for LLM Implementers

### 0.1 Read Order

Before implementing any task, read:

1. `LocalForge_OS_PRD.md`
2. This `MASTER_BACKLOG.md`
3. Existing `CHANGELOG.md`, if present
4. Current repository structure
5. The task-specific files referenced by the current backlog item

Do not implement features that are not in this backlog unless they are required to complete an explicitly listed task.

### 0.2 No Socratic Gate Behavior

Do not block progress with broad clarification questions such as:

- "What would you like me to do next?"
- "Should I implement X or Y?"
- "Can you clarify the architecture?"
- "Do you want me to continue?"
- "Would you prefer option A or B?"

This project owner does not want Socratic gate behavior.

Required behavior:

- Be Data-Driven.
- Read `PRD.md`, `MASTER_BACKLOG.md`, source files, tests, logs, and current implementation.
- If information is missing, research current best practices and official documentation.
- Make the best engineering decision for LocalForge OS.
- Document assumptions in code comments, ADRs, task notes, or `CHANGELOG.md`.
- Proceed with implementation.
- Ask a question only when the next action would be unsafe, destructive, legally ambiguous, or impossible without external credentials.

### 0.3 Data-Driven Decision Rule

When the PRD and backlog do not fully specify a detail:

1. Prefer safe local-first behavior.
2. Prefer reversible changes.
3. Prefer explicit state machines over implicit agent behavior.
4. Prefer small, testable units.
5. Prefer official documentation and stable APIs.
6. Prefer conservative defaults for unattended execution.
7. Prefer a blocked/safe state over risky automation.
8. Prefer backend correctness before frontend polish.
9. Prefer simple implementation over framework complexity.
10. Document the chosen decision and rationale.

### 0.4 Mandatory CHANGELOG.md Updates

A `CHANGELOG.md` file must exist in the repository root.

At the end of every phase, the implementing LLM must update `CHANGELOG.md` with:

- phase identifier and title;
- implementation date;
- summary of implemented features;
- added files;
- changed files;
- removed files, if any;
- tests added;
- tests run;
- known limitations;
- deferred items;
- migration notes, if any;
- safety or security changes;
- follow-up recommendations.

Use this format:

```markdown
# Changelog

All notable changes to LocalForge OS will be documented in this file.

## [Unreleased]

## [Phase N] - YYYY-MM-DD - <Phase Title>

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Security
- ...

### Tests
- ...

### Known Limitations
- ...

### Deferred
- ...
```

Do not dump raw git logs into the changelog. Summarize human-relevant changes.

A phase is not complete until `CHANGELOG.md` is updated.

### 0.5 Clean-Room Rule

Implementation agents may read reference repositories listed in `LocalForge_OS_PRD.md` to understand behavior and edge cases.

Implementation agents must not copy:

- source code;
- schemas;
- prompts;
- UI layouts;
- filenames that are unique to the reference project;
- implementation-specific protocol formats;
- comments;
- tests verbatim.

Implement LocalForge OS as original code.

### 0.6 Definition of Done for Every Task

A task is done only when:

- implementation is complete;
- tests exist or the task explicitly explains why tests do not apply;
- tests pass locally;
- public APIs are documented where relevant;
- no unsafe shell execution bypasses Safety Kernel;
- no runtime dependency on Codex/Antigravity/cloud agents was introduced;
- changelog is updated if the task completes a phase;
- the implementation respects local-first operation.

---

## 1. Backlog Index

| Phase | Title | Primary Outcome |
|---|---|---|
| 0 | Repository Foundation | Working repo skeleton, tooling, docs, changelog |
| 1 | Core Domain and Storage | Persistent project/task/run state |
| 2 | CLI Skeleton and Doctor | Usable command entrypoint |
| 3 | Configuration and Policies | Project config and safety policy files |
| 4 | Local Model Adapter | Ollama/OpenAI-compatible model access |
| 5 | Safety Kernel | Action mediation and command policy |
| 6 | Git Worktree Manager | Branch/worktree isolation |
| 7 | Artifact Store and Audit Log | Evidence, logs, immutable events |
| 8 | Task State Machine and Scheduler | Runnable task lifecycle |
| 9 | PRD Compiler | PRD.md to epics/tasks/dependencies |
| 10 | Basic Agent Runtime | Single task agent loop |
| 11 | Test Runner and Quality Gates | Focused tests and completion gates |
| 12 | Self-Healing Engine | Bounded repair attempts |
| 13 | PR Factory | Branch summaries and PR artifacts |
| 14 | Local API Server | FastAPI backend for UI/CLI |
| 15 | Realtime Events | WebSocket/SSE event stream |
| 16 | Frontend Foundation | Next.js app shell |
| 17 | Mission Control UI | Run/task/agent overview |
| 18 | PRD & Backlog Studio | Import/review/edit task plan |
| 19 | Safety Center UI | Policies, approvals, kill switch |
| 20 | PR Review Center | Evening PR review workflow |
| 21 | Agent Manager UI | Agent cards, logs, control actions |
| 22 | Models, Skills, Memory UI | Runtime management views |
| 23 | Multi-Agent Engineering Pipeline | Specifier/Coder/Tester/Reviewer/PRWriter |
| 24 | Skills Registry | Versioned engineering skills |
| 25 | Project Memory | Local project facts and retrieval |
| 26 | Sandbox Manager | Docker/local restricted execution |
| 27 | Unattended Mode Hardening | Long-running autonomous execution |
| 28 | Packaging and Developer Experience | install, scripts, docs |
| 29 | End-to-End Demo | PRD to PR-ready artifact |
| 30 | Stabilization and Hardening | reliability, security, cleanup |

---

## Phase 0 — Repository Foundation

### Goal

Create a maintainable project foundation for LocalForge OS.

### Dependencies

None.

### Deliverables

- Repository structure.
- Backend package skeleton.
- Frontend package skeleton.
- CLI entrypoint placeholder.
- `README.md`.
- `LocalForge_OS_PRD.md` copied into repository docs or root.
- `MASTER_BACKLOG.md` copied into repository docs or root.
- Root `CHANGELOG.md`.
- `.gitignore`.
- Development scripts.
- Initial test setup.

### Suggested Structure

```text
localforge/
  backend/
    localforge/
      __init__.py
      core/
      cli/
      api/
      agents/
      models/
      safety/
      gitops/
      storage/
      artifacts/
      scheduler/
      prd/
      testing/
      pr/
    tests/
    pyproject.toml
  frontend/
    package.json
    src/
  docs/
    LocalForge_OS_PRD.md
    MASTER_BACKLOG.md
    clean-room-notes.md
    adr/
  CHANGELOG.md
  README.md
```

### Tasks

#### LF-0001 — Initialize repository layout

Create backend, frontend, docs, and root-level project structure.

Acceptance criteria:

- directories exist;
- project can be opened by a coding agent without ambiguity;
- `README.md` explains product goal;
- `docs/clean-room-notes.md` exists.

Tests:

- no runtime tests required;
- verify paths exist.

#### LF-0002 — Create Python backend packaging

Set up backend packaging.

Recommended tools:

- Python 3.12
- `pyproject.toml`
- `pytest`
- `ruff`
- `mypy`
- `pydantic`
- `typer` or `click`

Acceptance criteria:

- `python -m pytest` runs;
- `ruff check .` runs;
- `mypy` can be configured, even if strictness is low initially.

#### LF-0003 — Create frontend skeleton

Set up a Next.js + TypeScript frontend.

Acceptance criteria:

- `npm install` or `pnpm install` works;
- `npm run lint` or equivalent exists;
- app renders placeholder LocalForge page.

#### LF-0004 — Create CHANGELOG.md

Create root `CHANGELOG.md` using the required format in section 0.4.

Acceptance criteria:

- file exists at repository root;
- includes `[Unreleased]`;
- includes Phase 0 section at end of phase.

### Phase Completion Gate

Phase 0 is complete when:

- backend tests run;
- frontend app starts;
- root changelog has Phase 0 entry.

---

## Phase 1 — Core Domain and Storage

### Goal

Implement persistent domain state for projects, documents, epics, tasks, runs, task runs, agents, handoffs, artifacts, policies, and audit events.

### Dependencies

Phase 0.

### Design Notes

MVP storage should use SQLite. Use an abstraction so PostgreSQL can be added later.

### Tasks

#### LF-0101 — Define domain models

Implement models for:

- Project
- ProductDocument
- Epic
- Task
- Agent
- Run
- TaskRun
- Handoff
- Artifact
- Policy
- AuditEvent

Acceptance criteria:

- models validate required fields;
- enum values match PRD;
- tests cover valid and invalid states.

#### LF-0102 — Implement SQLite storage layer

Create a storage adapter that persists core models.

Acceptance criteria:

- database initializes automatically;
- CRUD operations exist for core entities;
- tests use temporary SQLite database.

#### LF-0103 — Implement migration/bootstrap mechanism

Add simple schema initialization and version tracking.

Acceptance criteria:

- new database bootstraps;
- existing schema version is detectable;
- migration errors fail clearly.

#### LF-0104 — Implement repository/service layer

Add service APIs for:

- project creation;
- task creation;
- run creation;
- state transition;
- artifact metadata;
- audit insertion.

Acceptance criteria:

- services hide raw SQL/ORM details;
- tests cover common operations.

### Phase Completion Gate

- domain tests pass;
- storage tests pass;
- Phase 1 changelog entry added.

---

## Phase 2 — CLI Skeleton and Doctor

### Goal

Create a usable CLI foundation.

### Dependencies

Phase 1.

### Tasks

#### LF-0201 — Implement `localforge` CLI entrypoint

Commands:

```bash
localforge --help
localforge init
localforge doctor
localforge status
```

Acceptance criteria:

- CLI runs from development environment;
- help text is clear;
- command failures use non-zero exit codes.

#### LF-0202 — Implement `localforge init`

Creates `.localforge/` structure and config placeholders.

Acceptance criteria:

- idempotent;
- refuses to overwrite unsafe existing config;
- creates project record in database.

#### LF-0203 — Implement `localforge doctor`

Checks:

- Git installed;
- Python version;
- repo presence;
- SQLite write access;
- Ollama endpoint optional warning;
- Docker optional warning;
- frontend dependency optional warning.

Acceptance criteria:

- machine-readable `--json`;
- human-readable default;
- tests mock missing dependencies.

#### LF-0204 — Implement `localforge status`

Prints current project, task counts, run state, and model endpoint status if configured.

Acceptance criteria:

- works with empty project;
- supports `--json`.

### Phase Completion Gate

- CLI smoke tests pass;
- Phase 2 changelog entry added.

---

## Phase 3 — Configuration and Policies

### Goal

Implement project configuration and safety policies.

### Dependencies

Phase 2.

### Tasks

#### LF-0301 — Define config schema

Implement `.localforge/config.yaml` validation.

Acceptance criteria:

- schema covers project, git, runtime, sandbox, models, policies;
- invalid config errors are actionable.

#### LF-0302 — Define policy schema

Implement `.localforge/policies/default.yaml`.

Acceptance criteria:

- allowed commands;
- blocked commands;
- protected paths;
- approval-required patterns;
- repair limits;
- diff/file limits.

#### LF-0303 — Implement config loading precedence

Order:

1. CLI flags
2. Environment variables
3. `.localforge/config.yaml`
4. defaults

Acceptance criteria:

- tests cover precedence;
- sensitive values are not printed.

#### LF-0304 — Create default conservative policy

Default mode: `unattended_conservative`.

Acceptance criteria:

- no destructive commands allowed;
- main branch protected;
- `.env` protected;
- write access limited to project/worktree.

### Phase Completion Gate

- config and policy tests pass;
- Phase 3 changelog entry added.

---

## Phase 4 — Local Model Adapter

### Goal

Implement local model access through Ollama/OpenAI-compatible APIs.

### Dependencies

Phase 3.

### Reference Docs

- Ollama OpenAI-compatible API.
- Ollama model list/tags API.
- OpenAI-compatible chat completions.

### Tasks

#### LF-0401 — Implement provider abstraction

Create a provider interface for:

- list models;
- chat completion;
- streaming completion;
- structured JSON completion.

Acceptance criteria:

- provider interface is testable with fake provider;
- no provider-specific logic leaks into agents.

#### LF-0402 — Implement Ollama/OpenAI-compatible provider

Default base URL:

```text
http://localhost:11434/v1/
```

Acceptance criteria:

- supports model list where possible;
- supports chat completion;
- supports timeout;
- handles connection failure clearly.

#### LF-0403 — Implement structured output validator

All state-changing model output must validate against JSON schema.

Acceptance criteria:

- invalid JSON triggers one repair attempt;
- invalid second attempt fails safely;
- tests cover malformed output.

#### LF-0404 — Implement model profiles

Map roles to model profiles.

Acceptance criteria:

- config supports planner/coder/tester/reviewer/pr_writer;
- fallback profile exists;
- missing model fails in doctor/status.

### Phase Completion Gate

- fake provider tests pass;
- Ollama provider can be manually tested if Ollama installed;
- Phase 4 changelog entry added.

---

## Phase 5 — Safety Kernel

### Goal

Implement action mediation.

### Dependencies

Phase 3.

### Tasks

#### LF-0501 — Define action request model

Normalize all tool actions.

Action kinds:

- read_file
- write_file
- run_command
- git_command
- create_branch
- create_commit
- create_pr
- network_request

Acceptance criteria:

- action request validates path, task, purpose, and risk.

#### LF-0502 — Implement policy evaluator

Given an action request and policy, return:

- ALLOW
- DENY
- REQUIRE_APPROVAL

Acceptance criteria:

- blocked commands denied;
- protected paths denied or approval-required;
- writes outside worktree denied;
- tests cover path traversal.

#### LF-0503 — Implement approval queue

Store pending approvals.

Acceptance criteria:

- medium/high-risk action can be queued;
- approval/denial is audited;
- unattended mode does not wait forever.

#### LF-0504 — Implement safe command runner wrapper

All shell execution goes through Safety Kernel.

Acceptance criteria:

- direct shell calls are isolated to one module;
- command output is captured;
- secrets are redacted;
- timeouts enforced.

### Phase Completion Gate

- safety tests pass;
- blocked dangerous commands are verified;
- Phase 5 changelog entry added.

---

## Phase 6 — Git Worktree Manager

### Goal

Implement safe Git branch/worktree isolation.

### Dependencies

Phase 5.

### Tasks

#### LF-0601 — Implement Git adapter

Functions:

- status;
- current branch;
- default branch;
- create branch;
- create worktree;
- diff;
- commit;
- push optional later.

Acceptance criteria:

- all Git commands go through Safety Kernel;
- tests use temporary Git repo.

#### LF-0602 — Implement task worktree creation

Create deterministic worktree path and branch for task.

Acceptance criteria:

- branch format `localforge/<task-key>-<slug>`;
- default branch never edited;
- dirty worktree detected.

#### LF-0603 — Implement checkpoint and rollback support

Before risky repair, save checkpoint.

Acceptance criteria:

- can diff since checkpoint;
- can revert last attempt safely.

#### LF-0604 — Implement worktree cleanup eligibility

Mark safe-to-clean worktrees only after PR or failure state.

Acceptance criteria:

- no automatic deletion of unmerged changes;
- cleanup requires explicit command.

### Phase Completion Gate

- Git worktree tests pass;
- Phase 6 changelog entry added.

---

## Phase 7 — Artifact Store and Audit Log

### Goal

Persist all evidence and events.

### Dependencies

Phase 1.

### Tasks

#### LF-0701 — Implement artifact directory layout

Path:

```text
.localforge/artifacts/runs/<run-id>/tasks/<task-key>/
```

Artifact files:

- plan.md
- diff.patch
- tests.md
- risk.md
- review.md
- repair.md
- pr.md
- blocker.md

Acceptance criteria:

- artifact metadata stored in database;
- artifact file writes are atomic.

#### LF-0702 — Implement audit event append

Audit events are immutable append-only records.

Acceptance criteria:

- events cannot be modified through service API;
- payload is redacted;
- event created for state changes and safety decisions.

#### LF-0703 — Implement replay data export

Export run timeline as JSON.

Acceptance criteria:

- events ordered chronologically;
- includes artifact references;
- secrets redacted.

### Phase Completion Gate

- artifact tests pass;
- audit tests pass;
- Phase 7 changelog entry added.

---

## Phase 8 — Task State Machine and Scheduler

### Goal

Implement task lifecycle and scheduling.

### Dependencies

Phases 1, 3, 5, 6, 7.

### Tasks

#### LF-0801 — Implement task state transition rules

Allowed transitions:

```text
BACKLOG -> READY
READY -> CLAIMED
CLAIMED -> PLANNING
PLANNING -> IMPLEMENTING
IMPLEMENTING -> TESTING
TESTING -> REPAIRING
REPAIRING -> TESTING
TESTING -> REVIEWING
REVIEWING -> PR_READY
ANY_ACTIVE -> BLOCKED
ANY_ACTIVE -> FAILED_SAFE
```

Acceptance criteria:

- invalid transitions rejected;
- all transitions audited.

#### LF-0802 — Implement dependency resolver

Tasks are runnable only when dependencies are done or PR-ready according to policy.

Acceptance criteria:

- blocked dependency blocks task;
- independent tasks continue.

#### LF-0803 — Implement scheduler loop

Scheduler claims tasks respecting:

- dependencies;
- max parallel tasks;
- max active model calls;
- safety mode;
- resource budgets.

Acceptance criteria:

- deterministic in tests;
- no busy loop;
- graceful stop.

#### LF-0804 — Implement run lifecycle

Run states:

- CREATED
- RUNNING
- PAUSED
- STOPPING
- COMPLETED
- FAILED_SAFE

Acceptance criteria:

- pause/resume works;
- stop is graceful;
- final summary generated.

### Phase Completion Gate

- scheduler tests pass;
- Phase 8 changelog entry added.

---

## Phase 9 — PRD Compiler

### Goal

Convert PRD.md into epics, tasks, dependencies, acceptance criteria, and risk levels.

### Dependencies

Phases 1, 4, 7.

### Tasks

#### LF-0901 — Implement Markdown document loader

Load and hash PRD/backlog docs.

Acceptance criteria:

- stores ProductDocument;
- detects changed document hash.

#### LF-0902 — Implement deterministic PRD extraction baseline

Before using LLM, parse headings, bullets, tables, and checkboxes.

Acceptance criteria:

- works without model;
- extracts candidate epics/tasks.

#### LF-0903 — Implement model-assisted task generation

Use local model to refine tasks.

Acceptance criteria:

- structured JSON output;
- validation and repair;
- no state mutation on invalid output.

#### LF-0904 — Implement task sizing rules

Split tasks that are too large.

Heuristics:

- too many files expected;
- ambiguous acceptance;
- multiple unrelated components;
- risk high.

Acceptance criteria:

- generated tasks are small and testable;
- every task has acceptance criteria.

#### LF-0905 — Implement `localforge import-prd`

Acceptance criteria:

- command creates draft epics/tasks;
- supports `--dry-run`;
- supports `--json`.

#### LF-0906 — Implement event-driven scheduler trigger

Optimize the loop polling interval in `Scheduler` with an event-driven mechanism.

Acceptance criteria:

- Scheduler wakes up immediately on task status or run updates without waiting for loop interval.
- Uses `asyncio.Event` or in-memory pub-sub/event dispatching mechanism.
- Polling loop interval is kept only as a fallback watchdog trigger.

#### LF-0907 — Implement execution abstraction and runners pool

Abstract task execution into sandbox runner drivers to decouple scheduler from git worktrees.

Acceptance criteria:

- Implements a `BaseTaskRunner` defining setup, execution, checkpointing, and cleanup.
- Creates a `LocalWorktreeTaskRunner` implementing this interface.
- Scheduler orchestrates a pool of runners rather than git worktrees directly.
- Prepares architecture for docker/container-based runner isolation.

### Phase Completion Gate

- PRD import works on sample docs;
- Phase 9 changelog entry added.

---

## Phase 10 — Basic Agent Runtime

### Goal

Implement the first end-to-end single-task agent loop.

### Dependencies

Phases 4, 5, 6, 7, 8.

### Tasks

#### LF-1001 — Implement task context builder

Build concise context for a task.

Includes:

- task description;
- acceptance criteria;
- relevant project docs;
- relevant files;
- policy summary;
- current worktree path.

Acceptance criteria:

- context is bounded;
- large files summarized or omitted.

#### LF-1002 — Implement Lead Agent loop

Loop:

1. plan;
2. request safe actions;
3. apply edits;
4. request tests;
5. summarize.

Acceptance criteria:

- no direct shell/file bypass;
- all actions audited;
- can complete trivial text/code change.

#### LF-1003 — Implement file editing tool

Provide safe file read/write/edit operations.

Acceptance criteria:

- path-limited;
- produces diff artifact;
- rejects writes outside worktree.

#### LF-1004 — Implement basic handoff records

Create handoff records between logical roles.

Acceptance criteria:

- handoff stored;
- consumed once;
- visible in audit/replay.

### Phase Completion Gate

- one simple task can be run in a temp repo;
- Phase 10 changelog entry added.

---

## Phase 11 — Test Runner and Quality Gates

### Goal

Run focused tests and enforce completion gates.

### Dependencies

Phases 5, 7, 10.

### Tasks

#### LF-1101 — Implement test command discovery

Detect common test commands from project files.

Examples:

- pytest;
- npm test;
- pnpm test;
- npm run test;
- npm run lint;
- ruff;
- mypy;
- tsc.

Acceptance criteria:

- project-specific overrides supported;
- no command runs without Safety Kernel.

#### LF-1102 — Implement focused test runner

Run task-relevant tests.

Acceptance criteria:

- captures stdout/stderr;
- timeout enforced;
- test artifact written.

#### LF-1103 — Implement quality gate evaluator

A task can move to review only if gates pass or are explicitly justified.

Acceptance criteria:

- failed tests block PR_READY;
- missing tests require risk note;
- protected file changes require approval record.

### Phase Completion Gate

- test artifacts generated;
- quality gate tests pass;
- Phase 11 changelog entry added.

---

## Phase 12 — Self-Healing Engine

### Goal

Implement bounded repair after failures.

### Dependencies

Phases 10, 11.

### Tasks

#### LF-1201 — Implement failure classifier

Classes:

- TEST_ASSERTION_FAILURE
- TYPECHECK_FAILURE
- LINT_FAILURE
- BUILD_FAILURE
- DEPENDENCY_MISSING
- IMPORT_ERROR
- RUNTIME_EXCEPTION
- MODEL_BAD_EDIT
- CONFLICTING_REQUIREMENT
- AMBIGUOUS_REQUIREMENT
- COMMAND_BLOCKED_BY_POLICY
- SANDBOX_FAILURE
- MODEL_TIMEOUT
- MODEL_FORMAT_ERROR
- GIT_CONFLICT
- UNKNOWN_FAILURE

Acceptance criteria:

- classifier works from command result/log;
- tests cover representative logs.

#### LF-1202 — Implement repair policy

Default:

- max 3 attempts;
- stop on same failure repeated;
- stop on diff growth limit;
- stop on safety denial.

Acceptance criteria:

- never loops indefinitely;
- records repair artifacts.

#### LF-1203 — Implement minimal repair loop

Acceptance criteria:

- can repair a simple failing test fixture;
- blocks safely when unable;
- writes blocker artifact.

#### LF-1204 — Implement rollback after bad repair

Acceptance criteria:

- checkpoint before repair;
- revert last repair attempt if worse;
- audit rollback.

### Phase Completion Gate

- self-healing scenario test passes;
- Phase 12 changelog entry added.

---

## Phase 13 — PR Factory

### Goal

Create branch summaries and PR-ready artifacts.

### Dependencies

Phases 6, 7, 11, 12.

### Tasks

#### LF-1301 — Generate PR artifact

Create `pr.md` with:

- title;
- summary;
- acceptance criteria;
- changed files;
- tests;
- risk;
- repair attempts;
- checklist.

Acceptance criteria:

- artifact generated for completed task;
- includes links/paths to evidence.

#### LF-1302 — Implement local PR-ready state

Task moves to `PR_READY` even if remote GitHub is not configured.

Acceptance criteria:

- branch exists;
- artifacts exist;
- diff exists.

#### LF-1303 — Optional GitHub PR creation adapter

Use GitHub CLI or API only if configured.

Acceptance criteria:

- disabled by default if credentials missing;
- no merge;
- errors fall back to local PR artifact.

### Phase Completion Gate

- PR artifact created for sample task;
- Phase 13 changelog entry added.

---

## Phase 14 — Local API Server

### Goal

Expose backend state to frontend and CLI integrations.

### Dependencies

Phases 1 through 13 as applicable.

### Tasks

#### LF-1401 — Implement FastAPI app

Endpoints for:

- health;
- projects;
- tasks;
- runs;
- agents;
- artifacts;
- policies;
- models;
- PRs.

Acceptance criteria:

- API starts locally;
- OpenAPI docs available;
- tests use test client.

#### LF-1402 — Implement command bridge

API can start/pause/resume/stop runs.

Acceptance criteria:

- safe operations only;
- all commands audited.

#### LF-1403 — Implement artifact serving

Serve artifact metadata and safe file content.

Acceptance criteria:

- path traversal blocked;
- secrets redacted if detected.

### Phase Completion Gate

- API tests pass;
- Phase 14 changelog entry added.

---

## Phase 15 — Realtime Events

### Goal

Stream task/run/agent events to UI.

### Dependencies

Phase 14.

### Tasks

#### LF-1501 — Implement event bus abstraction

Acceptance criteria:

- supports publish/subscribe;
- persistent event replay from audit log.

#### LF-1502 — Implement WebSocket or SSE endpoint

Acceptance criteria:

- frontend can subscribe;
- reconnect works;
- event payloads are small.

#### LF-1503 — Emit lifecycle events

Events:

- run.started;
- task.status_changed;
- agent.action_requested;
- safety.action_allowed;
- safety.action_blocked;
- test.finished;
- repair.started;
- repair.succeeded;
- repair.failed;
- pr.created;
- artifact.created.

### Phase Completion Gate

- realtime smoke test passes;
- Phase 15 changelog entry added.

---

## Phase 16 — Frontend Foundation

### Goal

Create a real LocalForge web dashboard shell.

### Dependencies

Phase 14.

### Tasks

#### LF-1601 — Implement frontend app shell

Navigation:

- Mission Control
- PRD & Backlog
- Agents
- Runs
- Pull Requests
- Worktrees
- Models
- Skills
- Memory
- Safety
- Settings

Acceptance criteria:

- routes exist;
- layout responsive enough for desktop;
- API client configured.

#### LF-1602 — Implement API client

Acceptance criteria:

- typed client;
- error handling;
- loading states.

#### LF-1603 — Implement design system basics

Components:

- Card
- Table
- Badge
- Button
- Alert
- Timeline
- EmptyState
- CodeBlock
- Diff placeholder

Acceptance criteria:

- components reused across pages.

### Phase Completion Gate

- frontend lint/build passes;
- Phase 16 changelog entry added.

---

## Phase 17 — Mission Control UI

### Goal

Implement overview dashboard.

### Dependencies

Phases 14, 15, 16.

### Tasks

#### LF-1701 — Current run summary

Show:

- run status;
- mode;
- task counts;
- PR-ready count;
- blocked count;
- last event.

#### LF-1702 — Agent fleet cards

Show logical agents and current tasks.

#### LF-1703 — Risk alerts panel

Show blocked actions, pending approvals, high-risk tasks.

#### LF-1704 — Realtime timeline

Show recent events.

### Phase Completion Gate

- Mission Control reflects real backend data;
- Phase 17 changelog entry added.

---

## Phase 18 — PRD & Backlog Studio

### Goal

Allow importing and reviewing PRD-derived tasks.

### Dependencies

Phases 9, 16.

### Tasks

#### LF-1801 — PRD import UI

Upload/select PRD path and trigger import.

#### LF-1802 — Epic and task list UI

Show generated epics/tasks/dependencies.

#### LF-1803 — Task detail editor

Edit title, description, acceptance criteria, risk, dependencies.

#### LF-1804 — Plan approval UI

Mark generated tasks approved for unattended execution.

### Phase Completion Gate

- user can import PRD and approve tasks via UI;
- Phase 18 changelog entry added.

---

## Phase 19 — Safety Center UI

### Goal

Expose safety policies and controls.

### Dependencies

Phases 5, 14, 16.

### Tasks

#### LF-1901 — Safety mode display

Show current mode and policy file.

#### LF-1902 — Allowed/blocked command UI

Display policy rules.

#### LF-1903 — Pending approvals UI

Approve/deny queued actions.

#### LF-1904 — Kill switch UI

Pause/stop/lock project.

### Phase Completion Gate

- user can inspect and control safety state;
- Phase 19 changelog entry added.

---

## Phase 20 — PR Review Center

### Goal

Provide evening review workflow.

### Dependencies

Phases 13, 14, 16.

### Tasks

#### LF-2001 — PR queue

Cards for PR-ready tasks.

#### LF-2002 — PR detail page

Show:

- summary;
- changed files;
- tests;
- risk report;
- repair attempts;
- artifacts.

#### LF-2003 — Diff viewer

Render patch artifact.

#### LF-2004 — User actions

Actions:

- open local path;
- copy PR description;
- rerun tests;
- request adjustment;
- mark accepted/rejected.

### Phase Completion Gate

- user can review PR-ready artifacts from UI;
- Phase 20 changelog entry added.

---

## Phase 21 — Agent Manager UI

### Goal

Show and control local agents.

### Dependencies

Phases 10, 14, 15, 16.

### Tasks

#### LF-2101 — Agent cards

Show:

- role;
- model;
- task;
- state;
- attempt count;
- last action.

#### LF-2102 — Agent detail page

Show:

- current context summary;
- actions;
- logs;
- handoffs;
- artifacts.

#### LF-2103 — Control actions

Allow pause/terminate task/mark blocked where safe.

### Phase Completion Gate

- agent state observable in UI;
- Phase 21 changelog entry added.

---

## Phase 22 — Models, Skills, Memory UI

### Goal

Manage model routing, skills, and project memory.

### Dependencies

Phases 4, 16, 24, 25.

### Tasks

#### LF-2201 — Models page

Show providers, models, role mappings, health.

#### LF-2202 — Skills page placeholder then full list

Show skill name, trigger, status.

#### LF-2203 — Memory page placeholder then full list

Show project facts and allow delete/pin/stale.

### Phase Completion Gate

- model status visible;
- skills/memory pages ready for later capabilities;
- Phase 22 changelog entry added.

---

## Phase 23 — Multi-Agent Engineering Pipeline

### Goal

Upgrade from single task loop to structured engineering roles.

### Dependencies

Phases 10, 11, 12, 13.

### Tasks

#### LF-2301 — Implement role pipeline engine

Pipelines:

- fast: Coder → Tester → Reviewer → PRWriter
- default: Planner → Specifier → Coder → Tester → Fixer → Reviewer → PRWriter
- strict: Planner → Specifier → Coder → Cleaner → Architect → Hardener → QA → PRWriter

#### LF-2302 — Implement role-specific context builders

Each role gets scoped context.

#### LF-2303 — Implement handoff consumption ordering

Handoffs consumed exactly once in priority order.

#### LF-2304 — Implement pipeline artifacts

Each role produces its own artifact.

#### LF-2305 — Visual Routing Editor (From Phase 22 Enhancements)

Implement visual UI form components inside the Models tab to dynamically edit agent model mappings (e.g., mapping coding roles to specific LLM endpoints) and save routing maps permanently in the database.

#### LF-2306 — Memory Persistence Engine & Backup Exports (From Phase 22 Enhancements)

Develop backend services to persist project memory facts, and implement export/import actions (JSON/YAML) to backup and restore project context metadata.

#### LF-2307 — CI/CD Workflow Setup (From Phase 23 Enhancements)

Create a GitHub Actions configuration (.github/workflows/ci.yml) that automatically runs backend unit tests (pytest) and checks frontend build compilation (npm run build) on every push to remote branches.

#### LF-2308 — Branch Protection Rules and PR Factory Integration (From Phase 23 Enhancements)

Set up project branch protection policies requiring pull request review before merging to main, and ensure coordination with the PR Factory (Phase 13) flow.

### Phase Completion Gate

- default pipeline completes sample task;
- model routing visually editable;
- memory persistence and backups operational;
- CI/CD workflow active and validated;
- branch protection guidelines integrated;
- Phase 23 changelog entry added.

---

## Phase 24 — Skills Registry

### Goal

Implement reusable engineering procedures.

### Dependencies

Phases 10, 23.

### Tasks

#### LF-2401 — Define skill file format

Must include:

- name;
- purpose;
- triggers;
- allowed actions;
- expected artifacts;
- failure modes;
- examples.

#### LF-2402 — Implement skill loader

Load local skills from `.localforge/skills/` and built-in skills.

#### LF-2403 — Implement skill selection

Select skills based on task metadata and project stack.

#### LF-2404 — Create initial built-in skills

Recommended:

- python-pytest
- fastapi-endpoint
- react-component
- nextjs-page
- github-pr-writer
- git-worktree-debugging

### Phase Completion Gate

- skills loaded and used in task context;
- Phase 24 changelog entry added.

---

## Phase 25 — Project Memory

### Goal

Implement local project memory.

### Dependencies

Phases 7, 10.

### Tasks

#### LF-2501 — Define memory records

Types:

- stack fact;
- test command;
- user preference;
- known pitfall;
- resolved blocker;
- model performance note.

#### LF-2502 — Implement memory store

SQLite-backed or file-backed.

#### LF-2503 — Implement memory retrieval

Retrieve relevant facts for task context.

#### LF-2504 — Implement memory update from completed runs

Extract safe facts from artifacts.

### Phase Completion Gate

- memory contributes to future task context;
- Phase 25 changelog entry added.

---

## Phase 26 — Sandbox Manager

### Goal

Isolate execution.

### Dependencies

Phases 5, 6.

### Tasks

#### LF-2601 — Define sandbox provider interface

Methods:

- create;
- run command;
- copy in/out;
- destroy;
- status.

#### LF-2602 — Implement restricted local sandbox

Only inside worktree, through Safety Kernel.

#### LF-2603 — Implement Docker sandbox

Run tests/commands in container where configured.

#### LF-2604 — Add sandbox health checks

Detect Docker availability and failures.

### Phase Completion Gate

- test command runs in configured sandbox;
- Phase 26 changelog entry added.

---

## Phase 27 — Unattended Mode Hardening

### Goal

Make long-running autonomous execution safe and useful.

### Dependencies

Phases 8, 12, 14, 15, 19, 26.

### Tasks

#### LF-2701 — Implement resource budgets

Budgets:

- max run time;
- max repair attempts;
- max active model calls;
- max task duration;
- max diff growth;
- max file count.

#### LF-2702 — Implement heartbeat and watchdog

Detect stuck agents/tasks.

#### LF-2703 — Implement safe continuation after failure

Independent tasks continue after one task blocks.

#### LF-2704 — Implement run summary

At run end, summarize:

- PRs ready;
- blocked tasks;
- failed-safe tasks;
- recovered failures;
- safety blocks;
- recommended next steps.

### Phase Completion Gate

- unattended demo run completes without intervention;
- Phase 27 changelog entry added.

---

## Phase 28 — Packaging and Developer Experience

### Goal

Make project usable by another developer.

### Dependencies

Core backend and frontend phases.

### Tasks

#### LF-2801 — Create development scripts

Scripts:

- setup backend;
- setup frontend;
- run backend;
- run frontend;
- run tests;
- lint.

#### LF-2802 — Improve README

Include:

- product explanation;
- setup;
- local model setup;
- sample PRD;
- unattended warning;
- safety model.

#### LF-2803 — Add sample project

Small repo or fixture for e2e tests.

#### LF-2804 — Add troubleshooting docs

Common issues:

- Ollama not running;
- model missing;
- Git dirty state;
- Docker unavailable;
- PR creation credentials missing.

### Phase Completion Gate

- fresh setup works from README;
- Phase 28 changelog entry added.

---

## Phase 29 — End-to-End Demo

### Goal

Demonstrate PRD to PR-ready artifact.

### Dependencies

Phases 0 through 28.

### Tasks

#### LF-2901 — Create sample PRD

Small but realistic project requirement.

#### LF-2902 — Run import-plan-execute workflow

Show:

```bash
localforge init
localforge import-prd docs/examples/PRD_SAMPLE.md
localforge plan
localforge run --unattended
localforge prs
```

#### LF-2903 — Produce demo artifacts

Artifacts:

- generated tasks;
- run summary;
- PR artifact;
- test artifact;
- risk artifact;
- blocker example if useful.

#### LF-2904 — Document demo

Add docs/demo.md.

### Phase Completion Gate

- demo can be reproduced;
- Phase 29 changelog entry added.

---

## Phase 30 — Stabilization and Hardening

### Goal

Prepare LocalForge OS for sustained use.

### Dependencies

All previous phases.

### Tasks

#### LF-3001 — Security review

Check:

- command execution;
- path traversal;
- secrets redaction;
- protected paths;
- Git safety;
- sandbox boundaries.

#### LF-3002 — Reliability review

Check:

- stuck run recovery;
- interrupted process recovery;
- database consistency;
- artifact consistency;
- idempotency.

#### LF-3003 — Test coverage expansion

Add integration tests for:

- PRD import;
- scheduler;
- safety;
- Git worktrees;
- self-healing;
- API;
- UI critical flows.

#### LF-3004 — Documentation review

Ensure docs match actual behavior.

#### LF-3005 — Backlog grooming for v0.2

Create future backlog for:

- IDE extension;
- desktop packaging;
- advanced skills;
- better model benchmark harness;
- multi-repo support.

### Phase Completion Gate

- stabilization checklist complete;
- Phase 30 changelog entry added;
- repository is ready for v0.1 tag.

---

## Appendix A — Required Phase-End Ritual

At the end of each phase, the LLM must perform:

1. Run all relevant backend tests.
2. Run all relevant frontend tests/lint if frontend exists.
3. Run `localforge doctor` if implemented.
4. Update `CHANGELOG.md`.
5. Summarize:
   - what changed;
   - tests run;
   - limitations;
   - next phase.
6. Commit changes if Git workflow is enabled.
7. Do not ask whether to continue unless the next phase is unsafe or requires external credentials.

---

## Appendix B — Data-Driven Autonomy Examples

### Missing framework detail

Bad:

> Should I use FastAPI or Flask?

Good:

> Use FastAPI because the PRD specifies FastAPI and the project needs typed APIs, OpenAPI docs, and realtime endpoints.

### Missing frontend styling detail

Bad:

> What design system do you want?

Good:

> Implement minimal reusable components with neutral styling. Avoid over-design. Prioritize information density and maintainability.

### Missing model choice

Bad:

> Which local model should I use?

Good:

> Use the configured model profile. If absent, create a default profile pointing to Ollama with a placeholder model and make `doctor` report that the model must be configured.

### Ambiguous product behavior

Bad:

> Should failed tasks stop the run?

Good:

> Mark the task BLOCKED or FAILED_SAFE, generate blocker artifact, continue independent tasks, and document the decision.

---

## Appendix C — Non-Negotiable Safety Rules

- Never merge to `main`.
- Never push force.
- Never delete outside project root.
- Never read `.env` by default.
- Never print likely secrets.
- Never execute shell outside Safety Kernel.
- Never allow unbounded repair loops.
- Never silently ignore failing tests.
- Never mark PR_READY without artifacts.
- Never skip `CHANGELOG.md` at phase end.

---

## Appendix D — Changelog Entry Template

```markdown
## [Phase N] - YYYY-MM-DD - Phase Title

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Security
- ...

### Tests
- ...

### Known Limitations
- ...

### Deferred
- ...
```
