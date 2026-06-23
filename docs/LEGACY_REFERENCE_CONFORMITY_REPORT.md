# LocalForge OS Legacy Reference Conformity Report

Date: 2026-06-21

Scope: static audit of `docs/LocalForge_OS_PRD.md`, `docs/MASTER_BACKLOG.md`,
`CHANGELOG.md`, backend source, frontend source, and tests after the legacy-gap
remediation pass.

Status legend:

- Conforme: implemented with direct source and/or test evidence.
- Pos-MVP: explicitly outside the MVP scope in the PRD.

## Executive Summary

LocalForge OS now covers the MVP functionality requested from the four
orchestrator reference repositories in the PRD, using original LocalForge
schemas, services, APIs, CLI commands, frontend panels, and tests.

The previous gaps were remediated as follows:

- First-class task comments and thread retrieval were added through
  `TaskComment`, `TaskCommentORM`, `CoordinationService`, task comment API
  endpoints, and `TaskContextBuilder` integration.
- Runtime registration and heartbeat were added through
  `RuntimeRegistration`, persistent runtime records, runtime API endpoints, and
  heartbeat updates.
- Explicit ancestry was added through `/tasks/{task_id}/ancestry`, resolving
  product document, epic, task, task runs, artifacts, and PR artifacts.
- Squads were added as first-class control-plane records through `Squad`,
  `SquadORM`, `CoordinationService`, and project squad API endpoints.
- PRD-listed CLI commands were registered: `pause`, `resume`, `stop`, `tasks`,
  `task get`, `logs`, `replay`, `models list`, `skills list`, and
  `safety status`.
- Worktrees, Settings, model metrics, skill enablement/metadata, audit export,
  project lock, and unsafe-worktree revert actions were wired into backend API
  and frontend surfaces.
- Explicit old-tool-output compression and JSON action proposal parsing were
  added to the runtime.

## Reference Repository Conformity

### SwarmForge - Engineering Protocol

| Capability | Status | Evidence |
| --- | --- | --- |
| Original engineering pipeline abstraction | Conforme | `backend/localforge/pipeline/engine.py`, `backend/localforge/pipeline/roles.py`, `backend/tests/test_phase23_pipeline.py` |
| Role-based engineering workflow | Conforme | `AgentRole`, `RolePipelineEngine`, Phase 23 changelog |
| Durable handoffs in database | Conforme | `Handoff`, `HandoffORM`, `runtime/handoffs.py`, `test_agent_runtime.py` |
| Worktree isolation | Conforme | `gitops/manager.py`, `gitops/adapter.py`, `services/runners.py`, `test_gitops.py` |
| Scheduler consumes runnable tasks | Conforme | `services/scheduler.py`, `test_scheduler.py`, `test_phase27_unattended.py` |
| QA/test gates | Conforme | `quality/discovery.py`, `quality/runner.py`, `quality/gates.py`, `test_quality_gates.py` |
| Batch/task receive modes | Conforme | `cli/plan.py`, scheduler dependency selection, pipeline modes, CLI task commands |

### Multica - Engineering Control Plane

| Capability | Status | Evidence |
| --- | --- | --- |
| Project/task/issue control plane | Conforme | `Project`, `Epic`, `Task`, `Run`, `TaskRun`, services, state API |
| Agents as teammates | Conforme | `Agent`, `/agents`, `/agents/{id}/details`, Agent Manager UI |
| Workspaces | Conforme | project roots, `.localforge/`, Git worktrees, sample project |
| Task lifecycle | Conforme | `TaskStatus`, scheduler, API task controls, PR review actions |
| Metadata | Conforme | `Task.metadata`, `Run.resource_limits`, artifact summaries, audit payloads |
| Realtime control plane | Conforme | `events/bus.py`, SSE endpoint, frontend event hook |
| Local daemon/runtime registration | Conforme | `RuntimeRegistration`, `RuntimeRegistrationORM`, `/projects/{id}/runtimes`, `/runtimes/{id}/heartbeat` |
| Runtime heartbeats | Conforme | runtime heartbeat API, `Agent.heartbeat_at`, `ExecutionService.heartbeat_run`, scheduler watchdog |
| Issue comments/thread retrieval | Conforme | `TaskComment`, task comments API, `CoordinationService.recent_comments_for_context`, `TaskContextBuilder` |

### Paperclip - Governance Layer

| Capability | Status | Evidence |
| --- | --- | --- |
| Safety/governance policies | Conforme | `core/policy.py`, policy templates, Safety Center API/UI |
| Approval gates | Conforme | `ActionApproval`, `SafetyService`, `/safety/approvals`, `run_safe_command` |
| Pause/resume/stop/terminate controls | Conforme | run/task API controls, frontend controls, CLI `pause/resume/stop` |
| Heartbeats/watchdogs | Conforme | runtime heartbeat, run heartbeat, scheduler watchdog |
| Resource budgets | Conforme | `BudgetsConfig`, `Run.resource_limits`, scheduler/pipeline/file-tool checks |
| Immutable audit/replay | Conforme | `AuditEvent`, append-only audit service, export/replay APIs |
| Goal ancestry | Conforme | `/tasks/{task_id}/ancestry`, `ProductDocument -> Epic -> Task -> TaskRun -> Artifact/PRArtifact` |
| Org chart/squads | Conforme | `Squad`, `SquadORM`, `/projects/{id}/squads` |

### DeerFlow - Runtime Kernel

| Capability | Status | Evidence |
| --- | --- | --- |
| Lead-agent pattern | Conforme | `runtime/lead_agent.py`, `test_agent_runtime.py` |
| Role-specialized subagents | Conforme | `pipeline/roles.py`, `RolePipelineEngine`, role artifacts |
| Sandbox providers | Conforme | `sandbox/base.py`, `sandbox/local.py`, `sandbox/docker.py`, sandbox tests |
| Skills | Conforme | `skills/registry.py`, `docs/SKILL_FORMAT.md`, skills API/UI/tests |
| Project-local memory | Conforme | `services/memory.py`, `MemoryFact`, memory API/UI/tests |
| Context engineering | Conforme | `runtime/context.py`, bounded file snippets, skills, memory, comments |
| Long-running sessions | Conforme | scheduler loop, unattended budgets/watchdogs, run summaries |
| Context compression | Conforme | `runtime/compression.py`, compressed command summaries in `LeadAgentRuntime` |
| Tool-call recovery/fallback | Conforme | `runtime/actions.py`, strict JSON action proposals, safe execution through Safety Kernel |
| Recent comment retrieval | Conforme | task comments service and context integration |

## Ollama / Local Model Gateway Conformity

| Capability | Status | Evidence |
| --- | --- | --- |
| OpenAI-compatible base URL | Conforme | `core/config.py`, `OpenAICompatibleProvider` |
| Model listing | Conforme | `OpenAICompatibleProvider.list_models`, `/models`, frontend Models tab |
| Chat completions | Conforme | `OpenAICompatibleProvider.chat_completion` |
| Structured JSON output | Conforme | `response_format`, `llm/validator.py`, PRD compiler tests |
| Streaming | Conforme | `_stream_chat_completion`, `test_openai_compatible_provider_stream` |
| Tool/action fallback | Conforme | `runtime/actions.py`, metadata action parser, safe command/file tools |

## LocalForge-Unique Product Capability Conformity

| LocalForge capability | Status | Evidence |
| --- | --- | --- |
| Clean-room implementation discipline | Conforme | `docs/clean-room-notes.md`, original LocalForge code/modules |
| Local-first autonomous engineering OS | Conforme | SQLite, local CLI/API/frontend, local model adapter, sandbox/worktree execution |
| PRD compiler | Conforme | `prd/*`, `cli/import_prd.py`, PRD Studio UI/tests |
| Mission-control dashboard | Conforme | `frontend/src/App.tsx`, API client, SSE hook |
| PRD and Backlog Studio | Conforme | PRD import UI, task editor, approval controls |
| Safety Center | Conforme | approvals queue, policy editor, kill switch, lock project, audit export, unsafe-worktree revert |
| PR Review Center | Conforme | PR queue/detail UI, `pr_factory`, API PR details/review actions |
| Agent Manager | Conforme | agent details endpoint, controls, context/logs/handoffs tabs |
| Runs page | Conforme | frontend Runs tab, run command API |
| Worktrees page | Conforme | frontend Worktrees tab, dirty state, last commit, PR artifact path, cleanup/revert actions |
| Models page | Conforme | model list, role routing, model metrics endpoint/UI |
| Skills page | Conforme | skill list/register/edit, enabled state, last-used/success-rate fields |
| Memory page | Conforme | memory facts CRUD, pin/stale/delete, export/import |
| Settings page | Conforme | project paths, Git/PR provider, model endpoint, sandbox mode, resource limits, UI prefs |
| Self-healing engine | Conforme | `healing/*`, tests, pipeline integration |
| PR Factory | Conforme | local PR artifacts, optional GitHub adapter, PR tests |
| Audit/replay | Conforme | audit service, SSE replay, API audit events/export |
| Security/privacy | Conforme | secret redaction, protected paths, sandbox, quality gates, dependency audits |
| Packaging/developer experience | Conforme | `manage.py`, scripts, sample project, troubleshooting docs |

## PRD CLI Command Coverage

| PRD command | Status | Evidence |
| --- | --- | --- |
| `localforge init` | Conforme | `cli/main.py`, `cli/init.py` |
| `localforge doctor` | Conforme | `cli/main.py`, `cli/doctor.py` |
| `localforge import-prd PRD.md` | Conforme | `cli/main.py`, `cli/import_prd.py` |
| `localforge plan` | Conforme | `cli/main.py`, `cli/plan.py` |
| `localforge run` | Conforme | `cli/main.py`, `cli/run.py` |
| `localforge run --unattended` | Conforme | `cli/run.py` |
| `localforge status` | Conforme | `cli/main.py`, `cli/status.py` |
| `localforge prs` | Conforme | `cli/main.py`, `cli/prs.py` |
| `localforge pause` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge resume` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge stop` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge tasks list` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge task get LF-123` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge logs` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge replay <run-id>` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge models list` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge skills list` | Conforme | `cli/control.py`, `cli/main.py` |
| `localforge safety status` | Conforme | `cli/control.py`, `cli/main.py` |

## Validation Evidence

Targeted validation executed during remediation:

```powershell
.\.codex_venv\Scripts\python.exe -m pytest backend/tests -q
.\.codex_venv\Scripts\python.exe -m pytest backend/tests/test_api_server.py::test_api_comments_runtimes_and_task_ancestry backend/tests/test_api_server.py::test_api_dashboard_completion_endpoints backend/tests/test_cli.py::test_cli_help -q
.\.codex_venv\Scripts\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression backend/tests/test_agent_runtime.py::test_lead_agent_runtime_completes_trivial_file_change_through_safe_tools backend/tests/test_api_server.py::test_api_comments_runtimes_and_task_ancestry -q
.\.codex_venv\Scripts\python.exe -m mypy backend
npm.cmd run build --prefix frontend
```

## Final Assessment

No MVP-required gap from `docs/LocalForge_OS_PRD.md` remains open in this
legacy-reference conformity audit. Items explicitly named by the PRD as later
work, such as IDE extension and desktop packaging, remain post-MVP scope and are
not counted as implementation gaps for this report.
