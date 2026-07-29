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
| Path normalization | `normalize_lease_path()` canonicalizes separators and Windows case before overlap checks. |
| Exact active conflict key | `PathLeaseORM` stores `active_conflict_key` under a project-scoped uniqueness constraint and clears it on release. |
| Path lease fencing | `PathLease` now records `fencing_token`, heartbeat, attempt number, and worktree path. |
| Path lease renewal | `renew_lease()` extends an active lease only when owner and fencing token match. |
| Expired lease reclaim | Expired/released active keys can be reclaimed by a new fenced owner. |

## Validation Commands

```text
python -m pytest backend/tests/test_phase_r5_coordination.py backend/tests/test_phase6_runner_pool_governance.py backend/tests/test_phase6_worktrees_path_intents.py -q
10 passed in 0.57s

python -m pytest backend/tests/test_phase_r5_coordination.py backend/tests/test_phase6_runner_pool_governance.py backend/tests/test_phase6_worktrees_path_intents.py backend/tests/test_storage.py backend/tests/test_phase_r1_release_integrity.py -q
17 passed in 12.39s

python -m mypy backend/localforge/models/domain.py backend/localforge/storage/orm.py backend/localforge/storage/bootstrap.py backend/localforge/services/path_lease.py backend/localforge/services/runner_pool.py backend/localforge/services/governed_execution.py backend/localforge/services/scheduler.py backend/tests/test_phase_r5_coordination.py
Success: no issues found in 8 source files

python -m ruff check backend/localforge/storage/orm.py backend/localforge/storage/bootstrap.py backend/localforge/services/path_lease.py backend/localforge/services/runner_pool.py backend/localforge/services/governed_execution.py backend/localforge/services/scheduler.py backend/tests/test_phase_r5_coordination.py
All checks passed!
```

## Remaining Acceptance Requirements

- Parent/child overlap conflicts are still enforced by service-level checks,
  not by an atomic database exclusion constraint.
- Symlink resolution and repository-boundary canonicalization remain open.
- FIFO wait queues, cancellation, persisted wait-for graph, and deterministic
  deadlock victim selection remain open.
- Restart reconciliation still resets runner capacity; it does not yet rebuild
  capacity from persisted task-run truth.
- Real Git worktree creation, branch/base-commit drift validation, and failed
  worktree retention policy remain open.
