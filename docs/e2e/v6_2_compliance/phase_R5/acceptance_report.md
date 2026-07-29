# LocalForge OS V6.2 Phase R5 Coordination Hardening Report

## Verdict

`EVIDENCE_READY`

Phase R5 adds candidate hardening for RunnerPool and PathLease coordination.
It introduces persisted fencing tokens, lease heartbeat/expiry metadata,
task-run/worktree attempt attribution for path leases, exact-path active
conflict protection, and service-level path normalization for separators and
case handling.

This is candidate evidence only. Final R5 acceptance still requires
database-level parent/child overlap fencing across concurrent transactions,
bounded FIFO waiting, persisted wait-for graph deadlock detection, and full
worktree lifecycle reconciliation.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Runner lease identity | `RunnerDispatchLog` now records `lease_token`, `lease_owner_id`, `lease_expires_at`, and `heartbeat_at`. |
| Runner owner fencing | `release_runner_lease()` rejects stale tokens when a newer successful reservation exists for the task run and runner. |
| Runner heartbeat | `heartbeat_runner_lease()` refreshes the persisted heartbeat and expiry only for the current fenced owner. |
| Runner bounded backpressure | Capacity saturation now records `BACKPRESSURE_LIMITED` with deterministic queue position and bounded queue limit metadata, while full queues produce `BACKPRESSURE_QUEUE_FULL` instead of masquerading as incompatible runners. |
| Runner restart reconciliation | `reconcile_leaked_leases()` rebuilds `active_tasks_count` from successful dispatch logs joined to active `TaskRun` rows instead of resetting capacity blindly. |
| Path normalization | `normalize_lease_path()` canonicalizes separators and Windows case before overlap checks. |
| Exact active conflict key | `PathLeaseORM` stores `active_conflict_key` under a project-scoped uniqueness constraint and clears it on release. |
| Path lease fencing | `PathLease` now records `fencing_token`, heartbeat, attempt number, and worktree path. |
| Path lease renewal | `renew_lease()` extends an active lease only when owner and fencing token match. |
| Expired lease reclaim | Expired/released active keys can be reclaimed by a new fenced owner. |

## Validation Commands

```text
python -m pytest backend\tests\test_phase_r5_coordination.py backend\tests\test_phase6_runner_pool_governance.py backend\tests\test_phase6_worktrees_path_intents.py -q
12 passed in 1.01s

python -m pytest backend/tests/test_phase_r5_coordination.py backend/tests/test_phase6_runner_pool_governance.py backend/tests/test_phase6_worktrees_path_intents.py backend/tests/test_storage.py backend/tests/test_phase_r1_release_integrity.py -q
17 passed in 12.39s

python -m mypy backend\localforge\services\runner_pool.py backend\tests\test_phase_r5_coordination.py backend\tests\test_phase6_runner_pool_governance.py
Success: no issues found in 3 source files

python -m ruff check backend\localforge\services\runner_pool.py backend\tests\test_phase_r5_coordination.py backend\tests\test_phase6_runner_pool_governance.py
All checks passed!
```

## Remaining Acceptance Requirements

- Parent/child overlap conflicts are still enforced by service-level checks,
  not by an atomic database exclusion constraint.
- Symlink resolution and repository-boundary canonicalization remain open.
- FIFO wait queues, cancellation, persisted wait-for graph, and deterministic
  deadlock victim selection remain open.
- RunnerPool backpressure is bounded and reported separately from permanent
  incompatibility; persisted FIFO wait queues remain part of V61C-502.
- Real Git worktree creation, branch/base-commit drift validation, and failed
  worktree retention policy remain open.
