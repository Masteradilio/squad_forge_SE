# LocalForge OS V6.2 Phase R3 PR_READY Integrity Report

## Verdict

`EVIDENCE_READY`

Phase R3 introduces a typed server-owned readiness contract and hardens the
`PR_READY` transition so generic status updates and arbitrary dictionaries can
no longer mark a task as ready for pull request review.

This is candidate evidence only. Final acceptance still requires the remaining
R3 inventory of all mutation surfaces, full ActionGateway correlation coverage,
and commit-bound stale evidence checks.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Typed readiness contract | Added `PRReadyEvidence` with schema version, task run identity, maker/checker identity, pre-PR gate result, deterministic checks, artifact paths, branch, and worktree fields. |
| Generic status bypass closed | `update_task_status(..., PR_READY)` raises and all local regression paths use `mark_pr_ready()`. |
| Cross-task and mismatched evidence rejected | `TaskService` validates that the `task_run_id` exists, belongs to the task, and matches provided branch/worktree context. |
| Real artifact requirement | The transition queries persisted artifacts for the task run and rejects readiness when no artifact exists or when referenced artifact paths are unknown. |
| Independent checker guard | `PRReadyEvidence` rejects identical maker and checker identities. |
| Mechanical gate guard | `PRReadyEvidence` requires `pre_pr_gate.passed == true` and at least one deterministic check. |
| Atomic persistence | Normalized readiness evidence is persisted in task metadata before the server-owned state transition. |
| Replay handling | The same normalized evidence is idempotent; conflicting replay after `PR_READY` is rejected. |

## Validation Commands

```text
python -m pytest backend/tests/test_services.py backend/tests/test_gitops.py backend/tests/test_scheduler.py backend/tests/test_phase27_unattended.py -q
27 passed in 7.18s

python -m mypy backend/localforge/models/domain.py backend/localforge/services/task.py backend/localforge/pr_factory/local.py backend/localforge/runtime/lead_agent.py backend/localforge/pipeline/engine.py backend/tests/test_services.py backend/tests/test_gitops.py backend/tests/test_scheduler.py backend/tests/test_phase27_unattended.py
Success: no issues found in 9 source files

python -m ruff check backend/localforge/models/domain.py backend/localforge/services/task.py backend/localforge/pr_factory/local.py backend/localforge/runtime/lead_agent.py backend/localforge/pipeline/engine.py backend/tests/test_services.py backend/tests/test_gitops.py backend/tests/test_scheduler.py backend/tests/test_phase27_unattended.py
All checks passed!
```

## Remaining Acceptance Requirements

- Evidence is not yet cryptographically bound to exact source and target Git
  commits.
- R3 does not yet inventory every file, shell, Git, external API, PR, status,
  and artifact mutation path.
- ActionGateway decision correlation IDs are not yet persisted for every
  mutation surface.
- Stale evidence invalidation after branch, dependency, test, or source changes
  remains required.
