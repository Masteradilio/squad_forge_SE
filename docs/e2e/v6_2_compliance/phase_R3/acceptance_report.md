# LocalForge OS V6.2 Phase R3 PR_READY Integrity Report

## Verdict

`EVIDENCE_READY`

Phase R3 introduces a typed server-owned readiness contract and hardens the
`PR_READY` transition so generic status updates and arbitrary dictionaries can
no longer mark a task as ready for pull request review.

This is candidate evidence only. Final acceptance still requires the remaining
R3 inventory of all mutation surfaces, full ActionGateway correlation coverage,
and broader ActionGateway bypass tests.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Typed readiness contract | Added `PRReadyEvidence` with schema version, task run identity, persisted `PR_READY` handoff identity, maker/checker identity, independent maker/checker attempt identity, risk verdict, safety verdict, pre-PR gate result, deterministic checks, artifact paths, branch, worktree, source commit, target commit, and diff hash fields. |
| Generic status bypass closed | `update_task_status(..., PR_READY)` raises and all local regression paths use `mark_pr_ready()`. |
| Cross-task and mismatched evidence rejected | `TaskService` validates that the `task_run_id` exists, belongs to the task, and matches provided branch/worktree context. |
| Real artifact requirement | The transition queries persisted artifacts for the task run and rejects readiness when no artifact exists or when referenced artifact paths are unknown. |
| Independent checker guard | `PRReadyEvidence` rejects identical maker/checker identities and identical maker/checker attempt identities. |
| Mechanical gate guard | `PRReadyEvidence` requires `pre_pr_gate.passed == true`, approved risk and safety verdicts, at least one deterministic check, and non-empty source commit, target commit, and diff hash evidence. |
| Typed handoff guard | `TaskService` rejects missing, unknown, cross-task-run, or non-`PR_READY` handoffs before readiness. |
| Commit binding and stale evidence guard | `TaskService` rejects source/target commit evidence that conflicts with current task metadata and rejects source commits that conflict with a persisted worktree attempt manifest. |
| Atomic persistence | Normalized readiness evidence is persisted in task metadata before the server-owned state transition. |
| Replay handling | The same normalized evidence is idempotent; conflicting replay after `PR_READY` is rejected. |

## Validation Commands

```text
python -m pytest backend/tests/test_services.py backend/tests/test_gitops.py backend/tests/test_scheduler.py backend/tests/test_phase27_unattended.py -q
28 passed in 8.09s

python -m mypy backend/localforge/models/domain.py backend/localforge/services/task.py backend/localforge/pr_factory/local.py backend/localforge/runtime/lead_agent.py backend/localforge/pipeline/engine.py backend/tests/test_services.py backend/tests/test_gitops.py backend/tests/test_scheduler.py backend/tests/test_phase27_unattended.py
Success: no issues found in 9 source files

python -m ruff check backend/localforge/models/domain.py backend/localforge/services/task.py backend/localforge/pr_factory/local.py backend/localforge/runtime/lead_agent.py backend/localforge/pipeline/engine.py backend/tests/test_services.py backend/tests/test_gitops.py backend/tests/test_scheduler.py backend/tests/test_phase27_unattended.py
All checks passed!
```

## Remaining Acceptance Requirements

- R3 does not yet inventory every file, shell, Git, external API, PR, status,
  and artifact mutation path.
- ActionGateway decision correlation IDs are not yet persisted for every
  mutation surface.
- Stale evidence invalidation is now enforced for known source/target commit
  state and persisted worktree attempt source commits, but dependency and test
  content invalidation still require broader graph-level evidence tracking.
