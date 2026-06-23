# Changelog

All notable changes to LocalForge OS will be documented in this file.

## [Unreleased]

### Changed
- Documented the HP 12C full-human rejection loop status: LocalForge recovered
  the rejected PR set to `31 PR_READY / 0 FAILED_SAFE / 0 Safety Blocks`, the
  integrated product passes `106` tests, and bond price/yield now has real
  deterministic behavior instead of a not-supported stub.
- Added `docs/e2e/HP12C_PRODUCT_VALIDATION_REPORT.md` as the canonical
  syncable product-validation report for the HP 12C full-human rejection loop.
- Clarified that HP 12C Platinum parity remains pending: exact function, key,
  shifted-label, display/rounding, and visual-layout parity must still be
  validated against the real calculator/reference image before the product can
  be accepted as 100% functional.

## [Phase 33-45] - 2026-06-22 - V2 Hybrid Chief Engineer Harness

### Added
- Added contract-first PRD compilation that writes architecture contracts and
  task contract packets with allowed files, public APIs, forbidden dependencies,
  canonical test commands, and risk metadata.
- Added Chief Engineer contract review and final PR review services with
  economy-first prompts, strict JSON schemas, budget checks, and paid-call
  ledger records.
- Added `localforge chief-engineer freeze-contract` to run the paid contract
  review gate from a workspace after PRD import.
- Added local worker capability routing to escalate high-risk architecture,
  cross-module, visual, and repeated semantic failures to the Chief Engineer.
- Added deterministic contract verification for syntax, forbidden dependencies,
  public API mismatches, and file-scope contract drift.
- Added failure classification and targeted repair playbooks for syntax,
  missing imports, forbidden dependencies, timeouts, semantic failures, visual
  mismatches, empty diffs, and contract drift.
- Added contract change request evaluation so new files, public APIs, and
  dependency changes require Chief Engineer approval before contract expansion.
- Added integration validation, visual fidelity evidence gating, and V2
  benchmark reporting with rating, cost, repair, failure-class, integration, and
  visual metrics.
- Added OpenRouter Chief Engineer setup documentation and `.env.example`
  placeholders without secrets.
- Added frontend visibility for Chief Engineer provider, model, key status,
  paid-call count, token totals, estimated cost, and configured budget.

### Changed
- Runtime write actions now enforce task `allowed_files` contracts and block
  out-of-contract writes instead of silently accepting architecture drift.
- Contracted tasks now bypass legacy HP12C compatibility scaffolds so V2 runs
  cannot pass by adding unapproved shim files outside `allowed_files`.
- Role context now renders task contract packets, including allowed files,
  required APIs, forbidden dependencies, canonical test command, risk, and
  implementation notes.
- Python output sanitization now applies to generated production and test files,
  not only tests.
- Chief Engineer semantic repair now handles common model action aliases
  (`write_content`, `edit`, `operation`, `file`, `code`), rejects empty repair
  plans, limits invalid-output echo during JSON self-repair, and can run compact
  paid repair rounds after local Fixer exhaustion.
- Contracted tasks that produce no changed files but leave failing command
  evidence now escalate to Chief Engineer repair instead of ending with only a
  review artifact.
- Python sanitization now preserves valid standalone `}` lines in multiline
  Python literals while removing lone unmatched braces only when the full file
  fails with an unmatched-brace syntax error.
- HP 12C E2E reporting now identifies the next acceptance run as a V2 hybrid
  contract-first rerun rather than another V1 local-only retry.
- HP 12C V2 smoke evidence records Chief Engineer contract approval and the
  final V2 acceptance result of `31 PR_READY / 0 FAILED_SAFE / 0 Safety Blocks`
  in `samples/e2e-hp12c-platinum-v2-smoke-15`.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_prd_compiler.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_blocks_writes_outside_task_contract -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase34_chief_engineer_gate.py -q`
- `$env:PYTHONPATH='E:\\Projetos\\local_forge_os\\backend'; .\\.codex_venv\\Scripts\\python.exe -m localforge.cli.main chief-engineer freeze-contract --help`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase36_41_v2_controls.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase42_45_v2_e2e_controls.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_normalizes_common_model_aliases backend/tests/test_phase23_pipeline.py::test_role_pipeline_python_sanitizer_preserves_dict_closing_braces backend/tests/test_phase23_pipeline.py::test_role_pipeline_python_sanitizer_drops_only_unmatched_lone_braces backend/tests/test_phase34_chief_engineer_gate.py -q`
- HP 12C V2 smoke 15 repeated unattended execution over remaining failed tasks:
  final Run 6 `COMPLETED` with `31 PR_READY / 0 FAILED_SAFE / 0 Safety Blocks`.
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`: 158 passed.
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `npm run build --prefix frontend`

## [Phase 31-32] - 2026-06-22 - OpenRouter Chief Engineer and Paid Call Ledger

### Added
- Added `OpenRouterProvider` for the paid Chief Engineer model tier using the
  OpenRouter OpenAI-compatible API.
- Added Chief Engineer configuration loaded from `.env`/environment variables:
  `OPENROUTER_MODEL` and `OPENROUTER_API_KEY`.
- Added economy-first paid model budgets to runtime configuration:
  `max_paid_calls`, `max_paid_input_tokens`, `max_paid_output_tokens`, and
  `max_paid_usd`.
- Added persistent `model_call_ledger` storage and `ModelCallLedgerService` for
  recording paid model calls and enforcing per-run budgets.
- Added `/projects/{project_id}/chief-engineer/calls` and
  `localforge models paid-calls` for redaction-safe visibility into Chief
  Engineer usage.

### Changed
- Bumped the local schema version to create the paid model call ledger table.
- Added `ChiefEngineer` and Chief Engineer call reason enums for explicit
  economy-first routing/audit.

### Security
- OpenRouter API keys are loaded without logging and are redacted from provider
  error messages and API/CLI usage views.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase31_32_chief_engineer.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`

## [Architecture Backlog V2] - 2026-06-22 - Chief Engineer Hybrid Autonomy

### Added
- Added `docs/MASTER_BACKLOG_V2.md` as the recovery backlog after the HP 12C
  E2E runs showed that local-model-only autonomy did not reach the `Funciona
  bem` rubric.
- Defined the OpenRouter-backed Chief Engineer role, intended for architecture,
  contract freeze, hard failure triage, semantic repair planning, and final PR
  review.
- Added an economy-first paid model policy covering reason codes, token budgets,
  compact evidence bundles, cost ledger requirements, and safe budget exhaustion.
- Defined phases 31-45 for OpenRouter integration, cost tracking, contract-first
  PRD compilation, deterministic contract verification, failure-class repair
  playbooks, integration validation, visual fidelity gates, and the HP 12C V2
  rerun.

### Changed
- Reframed the next architecture from local-model swarm execution to
  Chief-Engineer-supervised, contract-first execution with local models limited
  to bounded worker tasks.

### Tests
- Documentation-only change; no automated tests run.

## [E2E Validation] - 2026-06-21 - HP 12C Acceptance Harness

### Added
- Added `docs/E2E_ACCEPTANCE_PLAN.md` defining the five-scenario acceptance
  plan, model-routing expectations, and rating rubric for unattended LocalForge
  validation.
- Added `samples/e2e-hp12c-platinum/docs/PRD_HP12C_PLATINUM.md` with a
  medium-scope 31-task financial calculator PRD based on the provided Platinum
  visual reference.
- Added `docs/e2e/HP12C_E2E_RUN_REPORT.md` with E2E evidence, current rating,
  and the blocking model-execution gap discovered during validation.

### Changed
- Updated CLI/API model listing to use the configured OpenAI-compatible provider
  instead of the fake provider, while keeping API tests injectable.
- Updated Git default-branch detection to fall back to the current local branch
  when `origin/HEAD` is unavailable.
- Updated scheduler runner setup failures to fail the task safely instead of
  retrying the same setup exception forever.
- Updated PR readiness to reject tasks with missing changed-file evidence and
  mark non-ready pipeline tasks as `FAILED_SAFE`.
- Added Coder-role runtime action execution through safe file and command tools,
  including local-model JSON action proposals outside pytest.
- Recorded changed files when runtime actions write files, so PR artifacts have
  concrete implementation evidence.
- Added Coder-role `pytest -q` validation when generated Python tests are
  present, preventing PR readiness for generated tests that fail.
- Added repair feedback for generated test failures: the pipeline now asks for
  structured repair actions, reapplies safe file writes, and reruns pytest up to
  the configured repair limit before failing safe.
- Normalized absolute Python interpreter paths in command validation so
  `python -m pytest` policies also cover venv-managed Python executables.
- Added a local-model action JSON repair retry when the model returns malformed
  action payloads before failing the task safely.
- Included generated changed-file snippets in repair prompts so the local model
  can fix imports and API mismatches using the current workspace state.
- Persisted command/pytest summaries before terminal generated-test failures so
  failed-safe tasks keep actionable evidence.
- Strengthened runtime prompts to require pytest-importable package/test layouts
  and `__init__.py` exports when generated tests import package APIs.
- Made runtime action parsing tolerate model responses that wrap a valid JSON
  object or array in surrounding text.
- Updated the HP 12C E2E sample to cap repair at one attempt per task, keeping
  the acceptance run practical for local Ollama models.
- Updated the HP 12C E2E report with Run 12 and Run 13 evidence. Run 13 finished
  in approximately 30 minutes with 15 `PR_READY`, 16 `FAILED_SAFE`, and zero
  safety blocks, so the current rating remains `Funciona com ressalvas`.
- Added run-scoped task branch names for unattended worktrees to avoid stale
  branch reuse across repeated E2E attempts.
- Added dependency-branch base selection for task worktrees, allowing tasks with
  ready dependencies to build from the dependency branch instead of the project
  default branch.
- Committed generated changed files before PR artifact generation so dependency
  branches can carry a real base into downstream task worktrees.
- Added a deterministic calculator scaffold fallback for initialization tasks,
  including broader HP 12C compatibility modules for common generated imports.
- Updated the HP 12C sample PRD to document the shared-base execution strategy.
- Updated the HP 12C E2E report with Run 14, Run 15, and Run 16 evidence. Run 16
  finished in approximately 30 minutes with 11 `PR_READY`, 20 `FAILED_SAFE`, and
  zero safety blocks, so the current rating remains `Funciona com ressalvas`.
- Expanded the HP 12C deterministic scaffold with canonical compatibility
  modules for common model-generated imports and raised the sample file budget to
  fit the shared scaffold.
- Filtered pytest repair actions so the Fixer cannot rewrite generated test
  files while attempting to fix a pytest failure; repairs must target production
  code, exports, modules, or package layout.
- Updated the HP 12C E2E report with Run 18 and Run 19 evidence. Run 19 finished
  in approximately 26 minutes 47 seconds with 17 `PR_READY`, 14 `FAILED_SAFE`,
  and zero safety blocks, so the current rating remains `Funciona com ressalvas`.
- Made worktree setup idempotent for deterministic task worktree paths, cleaning
  stale paths under `.localforge/worktrees` before creating a run-scoped branch
  and after failed `git worktree add` attempts.
- Hardened local sandbox subprocess timeout/cancellation handling so timed-out
  commands are killed and awaited before the pipeline continues.
- Drained subprocess pipes after local sandbox timeouts to avoid Windows
  unraisable transport warnings in the backend regression suite.
- Added `budgets.max_parallel_tasks` to workspace configuration and made
  `localforge run` pass that budget into the scheduler. The HP 12C sample now
  runs one task at a time for local Ollama stability.
- Added `append_content` as a safe runtime action and normalized model-proposed
  bare `pytest` commands to the current Python interpreter with `-m pytest`.
- Added calculator base-export preservation before pytest validation so stacked
  HP 12C feature branches cannot drop shared scaffold exports such as
  `Calculator`, `RPNStack`, and arithmetic helpers.
- Added full pytest validation output artifacts in `tests.md` before failed
  worktrees are cleaned up, improving post-run diagnosis of `FAILED_SAFE` tasks.
- Updated the HP 12C E2E report with Run 22, Run 23, Run 24, and Run 25
  evidence. Run 24 was the best clean post-fix run with 15 `PR_READY`, 16
  `FAILED_SAFE`, and zero safety blocks. Run 25 showed that increasing repairs
  to two attempts worsened this model mix, so the sample was restored to one
  repair attempt.
- Updated the HP 12C E2E report with Run 26 evidence. Run 26 finished with 14
  `PR_READY`, 17 `FAILED_SAFE`, and zero safety blocks, so the rating remains
  `Funciona com ressalvas`.
- Added HP 12C common-module compatibility reassertion before pytest validation
  for common generated import shapes such as numeric entry, TVM, memory,
  financial calculator helpers, and package aliases.
- Updated the HP 12C E2E report with Run 27 and Run 28 evidence. Run 28 was the
  final full-Codex acceptance check and finished with 11 `PR_READY`, 20
  `FAILED_SAFE`, and zero safety blocks. The harness is stable and auditable,
  but the local-model coding loop still does not satisfy the `Funciona bem`
  rubric for this medium PRD.
- Recorded fresh 2026-06-22 environment evidence for the E2E plan: backend
  regression passed with 133 tests, `mypy backend` passed, and the Ollama
  OpenAI-compatible endpoint exposed `gemma4:12b`, `granite4.1:8b`, and
  `nemotron-3-nano:4b`. The `ollama` executable itself was not available on PATH
  inside this Codex process.
- Added pre-pytest Python syntax validation for generated `.py` files. Syntax
  failures now feed the existing Fixer repair loop with direct file/line
  diagnostics before pytest collection, targeting a dominant Run 28 failure
  class without weakening the PR readiness gate.
- Filtered obsolete or unsafe `changed_files` entries before committing
  generated task branches, preventing stale metadata from making `git add`
  fail on files that no longer exist in a fresh worktree.
- Expanded deterministic HP 12C compatibility aliases for recurring model
  imports observed in Run 30, including `src.casing`, `components.lcddisplay`,
  `localforge.shift_state`, `localforge.display`, and `statistics.statistics`.
- Broadened HP 12C compatibility APIs for numeric entry decimal state, TVM
  register constructor arguments, amortization schedule lists, SciPy-free IRR,
  and probability helper tests that omit a direct `pytest` import.
- Updated the HP 12C E2E report with Run 29, Run 30, and Run 31 evidence. Run
  29 exposed stale changed-file metadata in the repeat-run path; Run 30 restored
  the previous 11 `PR_READY` / 20 `FAILED_SAFE` distribution; Run 31 fell to 8
  `PR_READY` / 23 `FAILED_SAFE`, showing that alias-shim expansion alone is not
  a reliable path to the `Funciona bem` rubric.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_scheduler.py backend/tests/test_gitops.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_pr_factory.py backend/tests/test_phase23_pipeline.py backend/tests/test_scheduler.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_agent_runtime.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_phase27_unattended.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_generated_pytest_failure -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_phase27_unattended.py backend/tests/test_safety_validator.py backend/tests/test_agent_runtime.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py backend/tests/test_phase23_pipeline.py backend/tests/test_safety_validator.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_gitops.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_gitops.py backend/tests/test_scheduler.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_gitops.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_gitops.py::test_worktree_manager_replaces_stale_task_worktree_path backend/tests/test_scheduler.py::test_scheduler_marks_pipeline_failure_failed_safe_and_recovers_session -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase27_unattended.py::test_budgets_default_config backend/tests/test_gitops.py::test_worktree_manager_replaces_stale_task_worktree_path -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_generated_pytest_failure -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase26_sandbox.py::test_local_sandbox_timeout backend/tests/test_phase26_sandbox.py::test_docker_sandbox_mocked -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_preserves_calculator_base_exports_for_feature_tasks -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_agent_runtime.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `Invoke-RestMethod -Uri http://localhost:11434/v1/models`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_invalid_generated_python_before_pytest -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_filters_missing_changed_files_before_commit backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_invalid_generated_python_before_pytest -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_adds_hp12c_import_alias_modules -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`

## [Warning Cleanup] - 2026-06-21 - UTC Datetime Defaults

### Changed
- Replaced deprecated `datetime.utcnow()` defaults and runtime comparisons with
  UTC-aware `datetime.now(UTC)` usage across backend domain models and scheduler
  timeout checks.
- Normalized scheduler timestamps read back from SQLite before comparing them
  with UTC-aware current time values.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`

## [Legacy Gap Closure] - 2026-06-21 - PRD Reference Compliance Completion

### Added
- Added `docs/LEGACY_GAP_IMPLEMENTATION_TASKS.md` as the implementation
  checklist derived from the legacy reference conformity report.
- Added persistent task comments, runtime registrations, runtime heartbeats,
  squads, and task ancestry resolution for explicit control-plane traceability.
- Added API endpoints for task comments, project runtimes, runtime heartbeat,
  task ancestry, project squads, worktree inventory/actions, project settings,
  model metrics, audit export, project lock, and skill updates.
- Added PRD-listed CLI commands and groups: `pause`, `resume`, `stop`, `tasks`,
  `task get`, `logs`, `replay`, `models list`, `skills list`, and
  `safety status`.
- Added runtime JSON action proposal parsing and explicit tool-output
  compression.

### Changed
- Integrated recent task comments into agent task context construction.
- Completed frontend Worktrees, Settings, Safety Center, Models, and Skills
  surfaces using backend-backed data and actions.
- Strengthened quality gates to block likely secrets in changed files before
  PR readiness.
- Updated `docs/LEGACY_REFERENCE_CONFORMITY_REPORT.md` to show no remaining
  MVP-required gaps against the PRD reference functionality.
- Bumped the local schema version to add new coordination tables.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_api_server.py::test_api_comments_runtimes_and_task_ancestry backend/tests/test_api_server.py::test_api_dashboard_completion_endpoints backend/tests/test_cli.py::test_cli_help -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression backend/tests/test_agent_runtime.py::test_lead_agent_runtime_completes_trivial_file_change_through_safe_tools backend/tests/test_api_server.py::test_api_comments_runtimes_and_task_ancestry -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_quality_gates.py::test_quality_gate_blocks_likely_secret_changes backend/tests/test_api_server.py::test_api_dashboard_completion_endpoints backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `npm.cmd run build --prefix frontend`

## [Legacy Reference Audit] - 2026-06-21 - PRD Reference Conformity Review

### Added
- Added `docs/LEGACY_REFERENCE_CONFORMITY_REPORT.md` mapping PRD-requested
  functionality inspired by SwarmForge, Multica, Paperclip, DeerFlow, and
  Ollama against the current LocalForge implementation.
- Documented LocalForge-specific feature conformity, missing PRD CLI commands,
  partial frontend surfaces, and recommended remediation backlog items.

## [Performance Audit] - 2026-06-21 - Backend and Frontend Optimization

### Added
- Added `.codex_venv/` to `.gitignore` so Codex can keep an isolated Python
  3.12 validation environment inside the workspace without polluting Git status.
- Installed local analysis tooling in `.codex_venv`: `radon`, `bandit`,
  `pip-audit`, and `pipdeptree`.

### Changed
- Added bulk task-run and artifact lookup helpers to avoid repeated database
  queries when listing task artifacts, CLI PR artifacts, scheduler aborts,
  scheduler watchdog checks, and replay exports.
- Optimized `localforge prs` by fetching task runs and PR artifacts in batches
  instead of querying per task.
- Optimized scheduler abort/watchdog paths by preloading runs for active tasks
  instead of issuing one query per task.
- Optimized API task artifact listing with one artifact query across all task
  runs.
- Made the API `open-path` endpoint test-safe by avoiding desktop opener
  process launches under pytest while still validating the target path.
- Optimized frontend dependency cycle checks from repeated linear task scans to
  a `Map` lookup.
- Memoized Mission Control timeline item generation and cleared pending SSE
  reconnect timers on unmount to avoid retained timers.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `npm.cmd run build --prefix frontend`

## [Security Audit] - 2026-06-21 - Dependency and API Hardening

### Added
- Added `.pip-audit-cache/` to `.gitignore` for local dependency-audit cache
  files.
- Added API security headers for content type sniffing, frame embedding,
  referrer policy, and a restrictive default content security policy.
- Added regression coverage proving `DockerSandbox.copy_from()` rejects unsafe
  archive members before writing extracted content.

### Changed
- Upgraded development test dependencies to `pytest>=9.0.3,<10.0` and
  `pytest-asyncio>=1.3,<2.0`, resolving the known `pytest` CVE reported by
  `pip-audit`.
- Hardened Docker archive extraction by validating member paths with
  `os.path.commonpath`, rejecting symlinks/hardlinks, and copying regular files
  explicitly instead of using `tarfile.extractall()`.
- Replaced detailed internal exception strings in API 500 responses for local
  path opening and rerun command execution with generic client-facing messages
  while keeping server-side warnings.
- Replaced hardcoded temp-directory heuristics in the pytest database bootstrap
  guard with runtime temporary directory discovery via `tempfile`.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `.\\.codex_venv\\Scripts\\python.exe -m bandit -r backend/localforge -q -ll -ii`
- `.\\.codex_venv\\Scripts\\python.exe -m pip_audit -r requirements.txt -r requirements-dev.txt --cache-dir .\\.pip-audit-cache`
- `.\\.codex_venv\\Scripts\\python.exe -m pip check`
- `npm.cmd audit --prefix frontend --audit-level=moderate`
- `npm.cmd run build --prefix frontend`

## [Diagnostics] - 2026-06-21 - Pytest Critical Hang Debug Logging

### Added
- Added opt-in pytest debug logging via `LOCALFORGE_TEST_DEBUG_LOG`, writing
  real-time test lifecycle events, heartbeat entries, process/system memory
  metrics, active thread names, database fixture lifecycle events, and periodic
  all-thread stack dumps through `faulthandler`.

### Fixed
- Removed unsafe global `builtins.open` mocking from
  `test_workspace_file_and_diff_limits`; it intercepted `load_config()` YAML
  reads and caused unbounded `MagicMock` growth inside PyYAML.
- Made debug `tracemalloc` opt-in through
  `LOCALFORGE_TEST_DEBUG_TRACEMALLOC`, keeping default debug logging lighter and
  less likely to amplify memory spikes.

### Usage
- Enable with PowerShell:
  `$env:LOCALFORGE_TEST_DEBUG_LOG="debug.log"`

## [Hotfix] - 2026-06-21 - Regression Test Resource Containment

### Changed
- Made scheduler pipeline execution opt-in via `execute_pipeline`, so scheduler
  unit tests keep exercising claim/setup behavior without launching full task
  pipelines unexpectedly.
- Enabled pipeline execution explicitly from `localforge run` and from the
  Phase 27 scheduler-to-pipeline regression test.
- Added a defensive monitor timeout to `localforge run` and bounded
  `Scheduler.stop()` so stalled background scheduler tasks are cancelled instead
  of being awaited indefinitely.
- Fixed the pytest AnyIO backend to `asyncio`, avoiding duplicate async test
  execution on environments where Trio is installed.

### Tests
- Not run by agent; local Python launcher in this session points to a missing
  base interpreter. Operator should run targeted validation locally.

## [Compliance Audit] - 2026-06-21 - Phase 0-30 Conformity Review

### Added
- Added `docs/PHASE_CONFORMITY_REPORT.md` with phase-by-phase conformity results,
  evidence, corrections, and pending operator validation commands.
- Added regression coverage for Docker sandbox sibling-prefix path escapes.
- Added regression coverage proving Scheduler executes the role pipeline after
  runner setup.
- Added regression coverage for `localforge prs` resolving real `PRArtifact`
  paths.

### Changed
- Updated `Scheduler` to invoke `RolePipelineEngine` for ready tasks after task
  runner setup, closing the gap between task scheduling and actual execution.
- Kept unattended run lifecycle ownership in `Scheduler` by allowing scheduled
  pipeline executions to avoid prematurely marking the run completed.
- Updated role pipeline status advancement to reload the current task status
  before applying transition ladders, avoiding stale state transitions.
- Hardened `DockerSandbox` copy path checks with `os.path.commonpath`.
- Updated `localforge prs` to detect `ArtifactType.PR` instead of comparing with
  a stale string literal.

### Tests
- Not run by agent per operator request; operator will run final regression.

## [Phase 30] - 2026-06-21 - Stabilization, Hardening & Backlog Grooming

### Added
- Created comprehensive stabilization test suite `backend/tests/test_phase30_stabilization.py` validating WorktreeManager lock concurrency, ArtifactStore atomic writes, SafetyKernel command injection blocking, and CLI integration.
- Added protective safety check in `bootstrap_database` (in `backend/localforge/storage/bootstrap.py`) to raise `RuntimeError` and block migrations against the primary development database if executed under pytest runner (preventing Windows file-lock deadlocks).
- Created future-proofing backlog document `docs/BACKLOG_V0.2.md` outlining roadmap features (IDE extensions, Electron distribution, advanced skills, benchmarks).

### Changed
- Enhanced `SafetyKernel` path traversal validator (`is_path_safe` and `evaluate` in `backend/localforge/safety/kernel.py`) to normalize path separators (`\`) and drive letters (`C:\`) and enforce case-insensitive checks on Windows.
- Upgraded command validation logic in `backend/localforge/safety/command_validator.py` to support case-insensitive and slash-agnostic protected paths checks.
- Refactored `test_cli_plan_and_run_integration` to execute inside isolated pytest `tmp_path` directories with mocked database manager connections, completely preventing I/O locks and memory bloat on Windows.
- Configured the SQLAlchemy engine in `DatabaseManager` (in `backend/localforge/storage/database.py`) to automatically use `StaticPool` when `sqlite :memory:` is targeted, guaranteeing single-connection physical sharing for all async test sessions.

## [Phase 29] - 2026-06-21 - End-to-End Demo

### Added
- Integrated backlog planning controls under new Typer sub-command `localforge plan` (in `backend/localforge/cli/plan.py`) to list, approve individual tasks, or bulk approve all tasks.
- Integrated runtime execution monitor under new Typer sub-command `localforge run` (in `backend/localforge/cli/run.py`), running Scheduler tasks in foreground and streaming progress details.
- Integrated pull requests visualization under new Typer sub-command `localforge prs` (in `backend/localforge/cli/prs.py`), listing generated local patch artifacts.
- Created realistic sample product requirements document `docs/examples/PRD_SAMPLE.md`.
- Created interactive CLI demo guide `docs/demo.md` walkthrough.

## [Phase 28] - 2026-06-20 - Packaging and Developer Experience

### Added
- Created a central, cross-platform Python developer utility `manage.py` in the root directory to automate workspace configuration and command execution.
- Added native command wrappers for Windows PowerShell (`.ps1`) and Unix/Bash (`.sh`) under the `scripts/` directory for developer convenience.
- Completely restructured and improved `README.md` with product details, installation steps, local LLM setup instructions, sample project guidance, safety kernel details, and troubleshooting references.
- Created `docs/TROUBLESHOOTING.md` detailing quick resolutions for common issues such as Ollama runtime states, missing models, Git dirty files count, Docker daemons, and remote GitHub token bindings.
- Created `samples/demo-project/` workspace containing an initial local Git repository, a skeleton python application, and a sample product requirements document (`PRD.md`) to facilitate e2e testing.

## [Phase 27] - 2026-06-20 - Unattended Mode Hardening

### Added
- Defined `BudgetsConfig` structure and integrated it into `LocalForgeConfig` and `DEFAULT_CONFIG` in `backend/localforge/core/config.py`.
- Created thread-safe, ContextVar-backed active LLM calls tracking in `backend/localforge/llm/context.py`.
- Integrated active LLM call budget enforcement in `OpenAICompatibleProvider.chat_completion` inside `backend/localforge/llm/openai_compatible.py`.
- Wrapped overall task execution inside an `asyncio.wait_for` global timeout in `backend/localforge/pipeline/engine.py`.
- Implemented file modification bounds and diff growth bounds checks post-role execution inside `backend/localforge/pipeline/engine.py`.
- Integrated strict validation checking of file writes in `backend/localforge/runtime/file_tools.py`.
- Added periodic heartbeat/pulse updates during pipeline stage transitions.
- Developed inactivity watchdog checks and global run timeout validation inside `backend/localforge/services/scheduler.py` to abort hung runs and transition them to `FAILED_SAFE`.
- Developed `RunSummary` generation on completion, which outputs a markdown summary report (`run_summary.md`) to the project root and updates the database summary status.
- Added comprehensive unit and integration tests in `backend/tests/test_phase27_unattended.py`.

### Changed
- Refactored git path comparison checks (`_check_workspace_budgets`) to compare the top-level repository path safely, bypassing git stats when executing outside isolated task worktrees.
- Updated `backend/localforge/services/task.py` to allow valid state transitions from active states to `FAILED_SAFE`.

## [Phase 26] - 2026-06-20 - Sandbox Manager

### Added
- Defined abstract `BaseSandbox` interface in `backend/localforge/sandbox/base.py`.
- Implemented restricted `LocalSandbox` in `backend/localforge/sandbox/local.py` for task worktrees.
- Implemented containerized `DockerSandbox` in `backend/localforge/sandbox/docker.py` utilizing the Docker Python SDK and mounting local worktrees directly.
- Developed `SandboxFactory` in `backend/localforge/sandbox/factory.py` to instantiate sandboxes with local fallback capabilities.
- Integrated sandbox command execution inside the Safety Kernel runner (`run_safe_command` in `runner.py`).
- Added Python SDK import check and client ping diagnostic to `check_docker` in the `localforge doctor` CLI tool.
- Developed comprehensive unit and integration tests in `backend/tests/test_phase26_sandbox.py` verifying sandboxing status, timeouts, SDK mocking, fallback resolution, and doctor checks.

### Changed
- Configured default sandbox parameters (`type: "local"`, `image: "python:3.12-slim"`, `network_enabled: False`) in `backend/localforge/core/config.py`.

## [Phase 25] - 2026-06-20 - Project Memory

### Added
- Defined typed memory records for stack facts, test commands, user preferences,
  known pitfalls, resolved blockers, and model performance notes.
- Extended the SQLite-backed memory store with relevant fact retrieval.
- Added memory contribution to task and role contexts.
- Added safe memory learning from completed run summaries and artifact summaries.
- Added typed memory selection in the frontend Memory view.
- Added targeted Phase 25 coverage in `backend/tests/test_phase24_25_skills_memory.py`.

### Changed
- Bumped the local schema version to add the `memory_facts.kind` column with a
  non-destructive SQLite migration for existing databases.

### Tests
- Not run by agent per operator request; operator will run final pytest/mypy.

## [Phase 24] - 2026-06-20 - Skills Registry

### Added
- Defined the LocalForge skill JSON format in `docs/SKILL_FORMAT.md`.
- Implemented built-in and `.localforge/skills/*.json` skill loading.
- Implemented skill selection from task metadata and project stack hints.
- Added built-in skills: `python-pytest`, `fastapi-endpoint`, `react-component`,
  `nextjs-page`, `github-pr-writer`, and `git-worktree-debugging`.
- Added skills to task and role context rendering.
- Exposed project skill list/register and task skill selection API endpoints.
- Connected the frontend Skills view to the backend registry.
- Added targeted Phase 24 coverage in `backend/tests/test_phase24_25_skills_memory.py`.

### Tests
- Not run by agent per operator request; operator will run final pytest/mypy.

## [Phase 23] - 2026-06-20 - Multi-Agent Pipeline, Routing, Memory, and CI

### Added
- Implemented deterministic role pipeline modes: fast, default, and strict.
- Added role-scoped context building, priority handoff consumption, and per-role artifacts.
- Added persistent role-to-model routing tables, services, API endpoints, and visual editor controls.
- Added persistent project memory facts with JSON/YAML backup export and import endpoints.
- Added memory UI integration backed by API persistence instead of local-only state.
- Added CI workflow for backend pytest/mypy and frontend production build.
- Added branch protection guidelines and PR Factory checklist integration.
- Added targeted Phase 23 regression tests in `backend/tests/test_phase23_pipeline.py`.

## [Phase 22] - 2026-06-20 - Models, Skills, Memory UI

### Added
- Developed Configured LLM Models view ('models') showcasing active providers, health status,
  available models, and agent role-routing mappings.
- Developed Workspace Skills Registry view ('skills') displaying skill triggers, current cached
  or active statuses, and forms to register new workspace skills.
- Developed Project Memory facts manager view ('memory') with local interactive states allowing
  user-facing delete, pin/unpin, and stale/activate triggers.
- Implemented real-time re-fetching of selected agent details, logs, artifacts, and handoffs
  upon receiving SSE project events.

## [Phase 21] - 2026-06-20 - Agent Manager UI & Interactive Safety Policy History

### Added
- Developed the Agent Manager split-view tab ('agents') showing active coding agent cards.
- Implemented Agent details panel displaying role, model, status, current task execution context,
  generated artifacts, logged safety approvals, handoffs, and audit trails.
- Added Task Execution Controls directly on the Agent Manager UI, enabling user-facing task
  pause, resume, block, and termination actions.
- Integrated interactive task dependency (DAG) tree editing directly on node trees inside Backlog
  Studio, allowing blockers and children dependencies removal/addition.
- Integrated safety policy version restore buttons and revision history display inside the Safety tab.
- Exposed backend REST API endpoints: GET /agents/{id}/details, POST /tasks/{id}/control/{action},
  and POST /projects/{id}/policies/{name}/restore/{version}.
- Added unit test coverage for new endpoints in backend/tests/test_api_server.py.

## [Phase 20] - 2026-06-20 - PR Review Center & Safety Enhancements

### Added
- Developed the PR Review Center ('prs' tab) showing a queue of PR-ready tasks.
- Created a side-by-side details panel containing summary, changed files, copy button,
  test runner console, unified diff viewer, and action buttons.
- Integrated interactive policy rules editor (allow/block commands, protected paths,
  max repair/files limits) inside the Safety tab.
- Added visual DAG tree representation of task dependencies (blockers/blocked tasks)
  inside the task details view in Backlog Studio.
- Exposed backend REST API endpoints: PUT /projects/{id}/policies/{name},
  GET /tasks/{id}/pr-details, POST /tasks/{id}/open-path, POST /tasks/{id}/rerun-tests,
  and POST /tasks/{id}/pr-review/{action}.
- Added unit test coverage test_api_pr_review_center_and_policy_updates
  in backend/tests/test_api_server.py.

## [Phase 19] - 2026-06-20 - Safety Center UI

### Added
- Developed Safety Center controls in App.tsx showing active policy name, rules, and configuration file.
- Developed Allowed Commands list, Blocked Commands list, and Protected Paths UI panels.
- Integrated interactive pending safety manual approvals queue.
- Implemented Emergency Kill Switch halting all active scheduling runs immediately.

## [Phase 18] - 2026-06-20 - PRD & Backlog Studio

### Added
- Implemented Epic and ImportPRDResult models in client.ts.
- Exposed backend endpoints: GET /epics, POST /import-prd, PUT /tasks/{id}, POST /tasks/{id}/approve.
- Developed PRD Compiler & Importer view in App.tsx (dry-run, spec analyzer).
- Developed Epics Map navigator sidebar and task list component.
- Implemented Task Detail Editor supporting title, description, risk level, and acceptance criteria.
- Implemented plan approval UI with "Approve Plan" action to activate backlog tasks to READY state.
- Created `test_api_prd_and_backlog_studio_endpoints` in `backend/tests/test_api_server.py`.
- Added client-side dependency cycle validation preventing loops in the task editor.
- Added reactive validation warnings and title/description required fields checks.
- Added paginated task lists in PRD & Backlog Studio and Mission Control panels.

## [Phase 17] - 2026-06-20 - Mission Control UI & Backend Enhancements

### Added
- Implemented CORS configuration in app.py allowing local dev environments (port 5173).
- Implemented Gzip compression middleware in app.py for optimized asset payloads.
- Implemented manual safety approvals endpoints (GET pending, POST decide action).
- Created interactive overview dashboard showing Run Summary, Agent Fleet cards, and Risk Alerts.
- Added live subscribing SSE operations timeline feed.
- Created `test_api_cors_and_gzip_middlewares_and_safety_endpoints` in `test_api_server.py`.

## [Phase 16] - 2026-06-20 - Frontend Foundation

### Added
- Created the React + TypeScript frontend structure under `frontend/` using Vite.
- Implemented a typed API client in `frontend/src/api/client.ts` matching backend REST endpoints.
- Implemented `useProjectEvents` hook in `frontend/src/api/events.ts` subscribing to SSE.
- Designed a dark HSL glassmorphic design system in `frontend/src/index.css`.
- Created basic design system components in `frontend/src/components/`: `Card`, `Table`, `Badge`,
  `Button`, `Alert`, `Timeline`, `EmptyState`, and `CodeBlock`.
- Built main dashboard shell in `frontend/src/App.tsx` featuring responsive sidebar, project
  selection, client-side hash router, and real-time operations stream sidebar.

### Changed
- Mounted static file serving from `frontend/dist` on `/` in `backend/localforge/api/app.py`
  to serve the compiled SPA directly when the FastAPI server is running.

### Tests
- Passed TS compilation and production build: `npm run build` in `frontend`.
- Passed full backend test suite: `pytest` (85 passed).
- Passed backend static analysis: `ruff` and `mypy`.

## [Phase 15] - 2026-06-20 - Realtime Events

### Added
- Added `backend/localforge/events/` with `EventBus`, compact lifecycle event payloads, publish/subscribe queues, and audit-log replay.
- Added lifecycle event mapping for `run.started`, `task.status_changed`, `agent.action_requested`, `safety.action_allowed`, `safety.action_blocked`, `test.finished`, `repair.started`, `repair.succeeded`, `repair.failed`, `pr.created`, and `artifact.created`.
- Added SSE endpoint `GET /projects/{project_id}/events` with replay via `last_event_id`, bounded replay `limit`, live in-memory subscription, compact payloads, and keep-alive handling.
- Added realtime publication for local API run command bridge operations.
- Added `backend/tests/test_realtime_events.py` covering LF-1501 through LF-1503.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\events backend\localforge\api\app.py backend\tests\test_realtime_events.py`.
- Passed syntax validation for Phase 15 files using bundled Codex Python: `python -m py_compile ...`.

### Known limitations
- Agent-side pytest/mypy execution is blocked by this shell's broken `.venv` Python launcher; validate Phase 15 with `python -m pytest backend/tests/test_realtime_events.py -q` and `mypy backend` in the activated venv.

## [Phase 14] - 2026-06-20 - Local API Server

### Added
- Added `backend/localforge/api/` with a FastAPI app factory for local API serving.
- Implemented endpoints for health, projects, tasks, runs, agents, artifacts, policies, models, audit events, and local PR-ready tasks.
- Implemented a safe command bridge for run `start`, `pause`, `resume`, and `stop` operations with audit events.
- Implemented artifact content serving with project-root path traversal blocking and secret redaction.
- Added `backend/tests/test_api_server.py` using FastAPI `TestClient`.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\api backend\tests\test_api_server.py`.
- Passed syntax validation for Phase 14 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 14 tests in the activated venv: `python -m pytest backend/tests/test_api_server.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 13] - 2026-06-20 - PR Factory

### Added
- Added `backend/localforge/pr_factory/` with local PR artifact generation and an opt-in GitHub PR adapter.
- Implemented `pr.md` generation with title, summary, acceptance criteria, changed files, tests, risk, repair attempts, evidence paths, and checklist.
- Implemented local PR-ready handling that marks tasks `PR_READY` when branch metadata, diff artifact, test artifact, and risk artifact exist, without requiring GitHub configuration.
- Added GitHub adapter defaulting to disabled unless explicitly configured with `LOCALFORGE_ENABLE_GITHUB_PR` and token environment variables; disabled or unavailable remote creation falls back to local PR artifacts.
- Added `backend/tests/test_pr_factory.py` covering LF-1301 through LF-1303.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\pr_factory backend\tests\test_pr_factory.py`.
- Passed syntax validation for Phase 13 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 13 tests in the activated venv: `python -m pytest backend/tests/test_pr_factory.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 12] - 2026-06-20 - Self-Healing Engine

### Added
- Added `backend/localforge/healing/` with failure classification, bounded repair policy, and a minimal self-healing engine.
- Implemented representative failure classes for test assertions, typecheck, lint, build, dependency/import failures, runtime exceptions, model failures, policy denial, sandbox failures, timeouts, git conflicts, and unknown failures.
- Implemented repair policy limits for max attempts, repeated same failure, diff growth, and safety denial.
- Implemented a deterministic repair loop that checkpoints file contents before repair, applies safe file edits, reruns focused tests, writes `repair.md`, blocks safely with `blocker.md`, and rolls back bad repairs with audit events.
- Added `backend/tests/test_self_healing.py` covering LF-1201 through LF-1204.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\healing backend\tests\test_self_healing.py`.
- Passed syntax validation for Phase 12 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 12 tests in the activated venv: `python -m pytest backend/tests/test_self_healing.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 11] - 2026-06-20 - Test Runner and Quality Gates

### Added
- Added `backend/localforge/quality/` with test command discovery, focused test execution, and quality gate evaluation.
- Implemented project-specific test command overrides through `.localforge/config.yaml` plus detection for Python, npm, pnpm, lint, mypy, ruff, and TypeScript commands.
- Implemented `FocusedTestRunner` to execute task-relevant commands through the Safety Kernel, enforce timeouts, capture stdout/stderr, and write `tests.md` artifacts.
- Implemented `QualityGateEvaluator` to block failed tests, require risk notes for missing tests, require approval records for protected file changes, and emit `risk.md` artifacts.
- Added `backend/tests/test_quality_gates.py` covering LF-1101 through LF-1103.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\quality backend\tests\test_quality_gates.py`.
- Passed syntax validation for Phase 11 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 11 tests in the activated venv: `python -m pytest backend/tests/test_quality_gates.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 10] - 2026-06-20 - Basic Agent Runtime

### Added
- Added `backend/localforge/runtime/` with `TaskContextBuilder`, `SafeFileEditor`, `RuntimeHandoffService`, and `LeadAgentRuntime`.
- Implemented bounded task context rendering with task description, acceptance criteria, policy summary, relevant file snippets, omitted-file markers, and current worktree path.
- Implemented safe runtime file reads/writes constrained to the task worktree, Safety Kernel evaluation for file actions, unified diff generation, and `diff.patch` artifact emission.
- Implemented a basic deterministic lead-agent loop that writes a plan artifact, executes metadata-declared file and command actions through safe tools, records summaries, and advances a trivial task to `PR_READY`.
- Implemented runtime handoff creation and consume-once handling with audit events visible in run replay.
- Added `backend/tests/test_agent_runtime.py` covering LF-1001 through LF-1004.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend`.
- Passed syntax validation for Phase 10 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 10 tests in the activated venv: `python -m pytest backend/tests/test_agent_runtime.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 9] - 2026-06-20 - PRD Compiler

### Added
- Added `backend/localforge/prd/` with a Markdown document loader, deterministic PRD extractor, model-assisted plan generation through the existing validated LLM adapter, task sizing heuristics, and transactional PRD import flow.
- Added `localforge import-prd` with `--dry-run` and `--json` output.
- Added `BaseTaskRunner`, `LocalWorktreeTaskRunner`, `RunnerContext`, and `TaskRunnerPool` to decouple scheduler task preparation from direct worktree orchestration.
- Added Phase 9 tests for Markdown loading/hash change detection, deterministic extraction, fake-LLM assisted generation, invalid JSON rollback behavior, sizing heuristics, CLI dry-run JSON output, event-driven scheduler wakeups, and runner pool integration.

### Changed
- Updated `Scheduler` to expose an event wait helper and use the runner pool when preparing task execution.
- Extended `ProjectService` with latest-document lookup by project path for PRD change detection.

### Tests
- Passed full test suite in the activated venv: `python -m pytest backend/tests -q` (59 passed).
- Passed static typing in the activated venv: `mypy backend` (Success: no issues found in 62 source files).
- Passed linting: `.\.venv\Scripts\ruff.exe check backend`.

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
