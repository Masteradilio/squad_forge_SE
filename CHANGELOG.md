# Changelog

All notable changes to LocalForge OS will be documented in this file.

## [Unreleased]

## [Phase 8] - 2026-06-20 - Task State Machine and Scheduler & Improvements

### Added
- Implemented `Scheduler` in `backend/localforge/services/scheduler.py` executing a background loop to claim `READY` tasks, respect `max_parallel_tasks` limit, and manage run statuses lifecycle (`PENDING` -> `RUNNING` -> `COMPLETED`/`FAILED`).
- Added periodic background worktree cleanup calling `WorktreeManager.cleanup_orphan_worktrees` every 10 iterations of the scheduler loop.
- Added transitions auditing in `TaskService.update_task_status` to append an `AuditEvent` of type `state_change` on every status transition.
- Implemented dependency checks (`is_task_runnable` in `TaskService`) blocking tasks (transitioning them to `BLOCKED`) if their dependencies transition to `FAILED_SAFE`, `CANCELLED`, or `BLOCKED`.
- Added pagination (`limit` and `offset` parameters) to `AuditService.export_run_replay` for memory optimization during large replay timeline generation.
- Created `backend/tests/test_scheduler.py` testing scheduler lifecycle, limits, dependency resolution, pagination, and transitions auditing.

### Changed
- Allowed task status transitions to `BLOCKED` from `BACKLOG`, `READY`, and `CLAIMED` in the valid status transitions mapping.

### Fixed
- Resolved all mypy type errors in `task.py`, `scheduler.py`, and `test_scheduler.py` using explicit type guards and non-None assertions.

### Tests
- Passed full test suite: `pytest backend/tests` (50 passed).
- Passed linting and formatting: `ruff check backend`.
- Passed static typing: `mypy backend`.

## [Phase 7] - 2026-06-20 - Artifact Store and Audit Log & Phase 6 Enhancements

### Added
- Implemented `ArtifactStore` in `backend/localforge/storage/artifacts.py` managing directory layout, atomic writes via temp file swap, and SHA-256 hash validation.
- Implemented `export_run_replay` in `backend/localforge/services/audit.py` to compile chronological timeline replay sequences of run events linking their generated task-run artifacts.
- Created `test_audit_store.py` testing atomic writes, filename restrictions, concurrency locks, worktree orphan cleanup scanner, and replay exports.

### Changed
- Added `asyncio.Lock` concurrency locking in `WorktreeManager` keyed by normalized absolute worktree paths to protect setup, checkpoint, rollback, and cleanup operations.
- Implemented `cleanup_orphan_worktrees` in `WorktreeManager` to scan, remove, and clean up physical worktree directories that do not belong to active tasks.
- Integrated automated recursive payload redaction in `AuditService.append_audit_event` to filter environment secrets out of event payloads before DB persistence.
- Exported `ArtifactStore` and `ArtifactStoreError` from `localforge/storage/__init__.py`.

### Security
- Applied automated payload redaction for database logs to ensure credentials and tokens (e.g. `LOCALFORGE_GITHUB_TOKEN`) never persist in plain-text audit tables.
- Guaranteed immutable audit history by only exposing append-only event logs in the service layer API.

### Tests
- Passed full test suite: `pytest backend/tests` (46 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- The replay JSON timeline compiles memory-intensive queries synchronously; optimization for large projects (e.g. paginated replay timelines) is deferred.

## [Phase 6] - 2026-06-20 - Git Worktree Manager & Filesystem Isolation

### Added
- Implemented `GitAdapter` in `backend/localforge/gitops/adapter.py` providing safe Git subprocess execution (status, current branch, branch creation, worktree add/remove, commits, hard resets, and cleanup) routed via the Safety Kernel.
- Developed `WorktreeManager` in `backend/localforge/gitops/manager.py` to automate task-isolated branch creation (`localforge/<task-key>-<slug>`), checkpoint commits, hard resets (rollbacks), and cleanups.
- Implemented portable argument-escaping in `GitAdapter` to handle double quotes, backslashes, and Windows path formats, preventing command injection and shell syntax errors.
- Created `test_gitops.py` containing comprehensive tests for branch naming, checkpoints, rollback recovery, and active boundary checks.

### Changed
- Integrated filesystem isolation boundary checks in `localforge/safety/runner.py` to fetch active task runs from `uow.tasks` and override `project_root` with the active worktree path.
- Updated `DEFAULT_POLICY_TEMPLATE` in `backend/localforge/core/templates.py` to include safe Git subcommands (`git rev-parse`, `git branch`, `git worktree`, `git add`, `git commit`, `git reset`, `git clean`) by default.

### Fixed
- Fixed command validation failure for `git worktree` by adding necessary Git subcommands to the allowed commands list.
- Fixed `AssertionError` in `test_gitops.py` by correctly initializing `uow.safety` in the unit tests.

### Security
- Enforced strict filesystem boundaries: when a task is active, all write operations outside the task's worktree path are blocked by the Safety Kernel, completely isolating the main repository.

### Tests
- Passed full test suite: `pytest backend/tests` (42 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- GitAdapter command routing is synchronous and blocks the thread; asynchronous git command runners are deferred.

## [Phase 5] - 2026-06-20 - Safety Kernel & Path Canonicalization

### Added
- Implemented Pydantic validation `ActionRequest` and `SafetyDecision` enums in `backend/localforge/safety/kernel.py`.
- Developed `SafetyKernel` policy evaluator enforcing traversal write locks, blocked command lists, protected path segments checks, and risk-level escalations.
- Implemented `is_path_safe` path canonicalizer resolving symlinks and absolute paths to prevent traversal breaks.
- Created `ActionApproval` domain models and SQLAlchemy ORM `ActionApprovalORM` mappings.
- Created `SafetyService` in `backend/localforge/services/safety.py` to persist pending approvals.
- Implemented safe shell subprocess runner `run_safe_command` in `backend/localforge/safety/runner.py` enforcing timeouts, audit logging, database-backed polling approval states, and secret redaction.
- Added comprehensive unit tests in `backend/tests/test_safety_kernel.py` checking traversal blocks, interactive approval polling task, and secret redaction.

### Changed
- Exposed `SafetyService` inside `UnitOfWork` repository bindings.

### Fixed
- Restored audit logging commit sequences in blocked execution paths inside `runner.py`.

### Security
- Enforced strict canonicalization checking for file write bounds and automated secret redaction for stdout/stderr logs.

### Tests
- Passed full test suite: `pytest backend/tests -v` (39 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- The safe command runner polls database approvals with a sleep interval; real-time push events via WebSockets are deferred to Phase 15.

### Deferred
- Real-time SSE/WebSocket notification pushes for safety approvals queue.

## [Phase 4] - 2026-06-20 - Local Model Adapter & AST Command Validator

### Added
- Implemented `BaseLLMProvider` abstract interface and custom LLM exceptions (`LLMError`, `LLMConnectionError`, `LLMTimeoutError`) in `backend/localforge/llm/base.py`.
- Developed `OpenAICompatibleProvider` in `backend/localforge/llm/openai_compatible.py` to route API completions and streaming chunk parsing via HTTPX.
- Implemented `FakeLLMProvider` in `backend/localforge/llm/fake.py` to facilitate offline testing.
- Implemented structured output validation and self-healing JSON repair utility in `backend/localforge/llm/validator.py`.
- Created shell command token state-machine `split_shell_commands` and AST-based policy evaluator `validate_command` in `backend/localforge/safety/command_validator.py`.
- Added suite of 13 unit tests verifying safety operators splitting, protected path blocking, mock provider streaming, and JSON repair flows.

### Changed
- Refactored `localforge doctor` diagnostics in `backend/localforge/cli/doctor.py` to query active configuration model settings and check target model existence at the endpoint instead of hardcoded Ollama URL checks.

### Fixed
- Fixed mock assertions in `test_llm_provider.py` to cleanly resolve async client calls to synchronous responses.

### Security
- Enforced AST shell subcommand decomposition which blocks command chaining (e.g. `&&`, `||`, `;`, `|`) bypass attempts of restricted command names or protected paths.

### Tests
- Passed full test suite: `pytest backend/tests -v` (32 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- OpenAICompatibleProvider requires a running Ollama or compatible server containing the target default model to pass full CLI doctor diagnostics.

### Deferred
- Planner/Coder/Tester/Reviewer specific role configurations binding checks in doctor command deferred to runtime initialization.

## [Phase 3] - 2026-06-20 - Configuration and Policies

### Added
- Implemented robust `LocalForgeConfig` Pydantic v2 schemas for project, git, and models sections.
- Created `load_config` implementation in `backend/localforge/core/config.py` enforcing multi-source configuration precedence (CLI > Env > File > Defaults) with type safety and sensitive data protection.
- Created `PolicyRules` and `PolicyConfig` Pydantic schemas in `backend/localforge/core/policy.py` validating safety boundaries (allowed/blocked commands, protected paths, and execution thresholds).
- Created a new templates module `backend/localforge/core/templates.py` housing standard dict templates (`DEFAULT_CONFIG_TEMPLATE` and `DEFAULT_POLICY_TEMPLATE`).
- Added unit tests for schema validation and precedence loading in `backend/tests/test_core_config.py`.

### Changed
- Refactored `backend/localforge/cli/init.py` to import templates from `localforge.core.templates` instead of maintaining hardcoded dictionaries.

### Fixed
- Fixed Ruff B904 warning by ensuring all exceptions in `policy.py` chain correctly with `from e` syntax.

### Security
- Provided safe, unattended conservative policy constraints as default on workspace initialization.

### Tests
- Passed full test suite: `pytest backend/tests -v` (19 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- Configuration values do not auto-reload dynamically on file change; must be reloaded per command execution.

### Deferred
- Dynamic file watchers for configuration changes deferred to subsequent phases.

## [Phase 2] - 2026-06-20 - CLI Skeleton and Doctor & Unit of Work

### Added
- Implemented transactional `UnitOfWork` context manager in `backend/localforge/storage/transactions.py` to aggregate service layers and manage ACID transactions atomically.
- Developed `localforge` CLI application using `typer` library in `backend/localforge/cli/main.py`.
- Implemented `localforge init` command to create the workspace layout (`.localforge/` with subfolders for config, policies, memory, artifacts, runs, and logs), write default configuration, default conservative safety policy, and register the project in the database.
- Implemented `localforge doctor` diagnostics command checking Git, Python (>=3.11), write permissions, database connectivity, Docker, and Ollama. Added support for machine-readable `--json` output.
- Implemented `localforge status` workspace statistics command, pulling tasks counts, runs, active agents, and displaying them in rich CLI tables or structured JSON output.
- Created `backend/tests/test_transactions.py` validating UOW atomic commit and rollback behavior.
- Created `backend/tests/test_cli.py` providing end-to-end integration tests for init, status, and doctor command suites in an isolated temporary directory.

### Changed
- Refactored `get_status_data` inside `status.py` to inspect `.localforge` folder existence prior to establishing database connections, preventing `OperationalError` when executing status on uninitialized directories.

### Fixed
- Fixed SQLite connection parsing on Windows to support absolute path URLs with drive letters (e.g. `sqlite+aiosqlite:///C:/...` and `sqlite+aiosqlite:////C:/...`), adjusting `ensure_db_directory` in `bootstrap.py`.
- Resolved mypy type annotations and import order in `init.py`, `status.py`, and test files.

### Security
- Default conservative policy template configured on `init` preventing command execution of `rm -rf`, `git push --force`, and `git merge main`, and protecting `.env` file paths.

### Tests
- Passed full test suite: `pytest backend/tests -v` (15 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- Docker daemon and Ollama endpoint connectivity checks display warnings (non-blocking) if they are offline or unreachable.

### Deferred
- None.

## [Phase 1] - 2026-06-20 - Core Domain and Storage

### Added
- Core Pydantic validation domain schemas in `backend/localforge/models/domain.py` and enums in `backend/localforge/models/enums.py`.
- SQLAlchemy 2.0 ORM mappings in `backend/localforge/storage/orm.py`.
- Async database pool/session creation using SQLAlchemy and aiosqlite in `backend/localforge/storage/database.py`.
- Automatic database folder creation and schema versioning/bootstrap in `backend/localforge/storage/bootstrap.py`.
- Service Layer/Repositories (`ProjectService`, `TaskService`, `ExecutionService`, and `AuditService`) in `backend/localforge/services/`.
- Enforced strict task status state transitions inside the `TaskService` layer.
- Comprehensive integration tests in `backend/tests/test_domain_models.py`, `backend/tests/test_storage.py`, and `backend/tests/test_services.py`.

### Changed
- Refactored `backend/tests/conftest.py` to use asynchronous transaction fixtures yielding sessions.

### Fixed
- Fixed Python type annotations in models, ORM, and tests to comply with mypy static analysis.

### Security
- Created append-only constraints for AuditEvents to ensure audit trail immutability.

### Tests
- Passed full test suite: `pytest backend/tests -v`.
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- SQLite database backend only (PostgreSQL adapter is currently deferred).
- Programmatic bootstrap version 1 initialization only (incremental migrations deferred).

### Deferred
- PostgreSQL adapter integration.
- Incremental migrations framework.

## [Phase 0] - 2026-06-20 - Repository Foundation

### Added
- Backend Python 3.12 project structure, using `pyproject.toml`, `requirements.txt`, and `requirements-dev.txt`.
- Frontend Next.js skeleton structure.
- Initial project documentation, including `LocalForge_OS_PRD.md` and `MASTER_BACKLOG.md`.
- Basic import test `test_bootstrap_import` confirming `localforge` versioning.
- Lint and format checkers with `ruff`, typecheck with `mypy`, and test runner with `pytest`.

### Changed
- None (Initial setup bootstrap).

### Fixed
- None (Initial setup bootstrap).

### Security
- Isolated backend environment config setup with `.env.example` placeholder and default `.gitignore` definitions.

### Tests
- Passed initial suite: `pytest backend/tests -q`.
- Passed linting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- No active domain logic or storage persistence.

### Deferred
- CLI setup deferred to Phase 2.
- Local model routing deferred to Phase 4.