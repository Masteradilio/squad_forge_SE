# LocalForge OS V6.2 Phase R5 Coordination Hardening Report

## Verdict

`EVIDENCE_READY`

Phase R5 adds candidate hardening for RunnerPool and PathLease coordination.
It introduces persisted fencing tokens, lease heartbeat/expiry metadata,
task-run/worktree attempt attribution for path leases, exact-path active
conflict protection, and service-level path normalization for separators and
case handling plus repository-boundary canonicalization. It also persists
PathLease wait-for edges with bounded timeouts, cancellation, FIFO queue
position, repeated-contention escalation, and deterministic two-owner deadlock
victim selection.

This is candidate evidence only. Final R5 acceptance still requires
database-level parent/child overlap fencing across concurrent transactions,
and full worktree lifecycle reconciliation.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Runner lease identity | `RunnerDispatchLog` now records `lease_token`, `lease_owner_id`, `lease_expires_at`, and `heartbeat_at`. |
| Runner owner fencing | `release_runner_lease()` rejects stale tokens when a newer successful reservation exists for the task run and runner. |
| Runner heartbeat | `heartbeat_runner_lease()` refreshes the persisted heartbeat and expiry only for the current fenced owner. |
| Runner bounded backpressure | Capacity saturation now records `BACKPRESSURE_LIMITED` with deterministic queue position and bounded queue limit metadata, while full queues produce `BACKPRESSURE_QUEUE_FULL` instead of masquerading as incompatible runners. |
| Runner restart reconciliation | `reconcile_leaked_leases()` rebuilds `active_tasks_count` from successful dispatch logs joined to active `TaskRun` rows instead of resetting capacity blindly. |
| Path normalization | `normalize_lease_path()` canonicalizes separators and Windows case before overlap checks. |
| Repository-boundary canonicalization | `canonicalize_repository_relative_path()` resolves targets through the repository root, follows available symlinks, rejects paths that escape the root, and is enforced by `PathLeaseService.acquire_lease(repository_root=...)`. |
| Exact active conflict key | `PathLeaseORM` stores `active_conflict_key` under a project-scoped uniqueness constraint and clears it on release. |
| Path lease fencing | `PathLease` now records `fencing_token`, heartbeat, attempt number, and worktree path. |
| Path lease renewal | `renew_lease()` extends an active lease only when owner and fencing token match. |
| Expired lease reclaim | Expired/released active keys can be reclaimed by a new fenced owner. |
| Path lease wait graph | `PathLeaseWaitORM` persists bounded wait-for edges with queue position, expiry, cancellation, and status. |
| Repeated contention escalation | Duplicate waits for the same owner/path increment `contention_count` and transition to `ESCALATED` after a deterministic threshold instead of busy-waiting. |
| Deadlock victim selection | `enqueue_wait()` detects two-owner wait cycles and marks the lexicographically deterministic victim as `DEADLOCK_VICTIM`. |

## Validation Commands

```text
python -m pytest backend\tests\test_phase_r5_coordination.py backend\tests\test_phase6_runner_pool_governance.py backend\tests\test_phase6_worktrees_path_intents.py -q
18 passed, 1 skipped in 1.47s

python -m pytest backend/tests/test_phase_r5_coordination.py backend/tests/test_phase6_runner_pool_governance.py backend/tests/test_phase6_worktrees_path_intents.py backend/tests/test_storage.py backend/tests/test_phase_r1_release_integrity.py -q
17 passed in 12.39s

python -m mypy backend\localforge\services\path_lease.py backend\tests\test_phase_r5_coordination.py
Success: no issues found in 2 source files

python -m ruff check backend\localforge\services\path_lease.py backend\tests\test_phase_r5_coordination.py
All checks passed!

python -m pytest backend\tests\test_phase_r5_coordination.py -q
12 passed, 1 skipped in 1.03s
```

## Remaining Acceptance Requirements

- Parent/child overlap conflicts are still enforced by service-level checks,
  not by an atomic database exclusion constraint.
- Repository-boundary canonicalization and symlink escape rejection are covered
  where the host permits symlink creation.
- FIFO wait queues, timeout/cancellation, persisted wait-for graph, and
  deterministic two-owner deadlock victim selection are covered by R5
  regression tests. Repeated contention now transitions to `ESCALATED` instead
  of silently busy-waiting.
- RunnerPool backpressure is bounded and reported separately from permanent
  incompatibility.
- Real Git worktree creation, branch/base-commit drift validation, and failed
  worktree retention policy remain open.
