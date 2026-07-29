# LocalForge OS V6.2 Phase R5 Coordination Hardening Report

## Verdict

`EVIDENCE_READY`

Phase R5 adds candidate hardening for RunnerPool and PathLease coordination.
It introduces persisted fencing tokens, lease heartbeat/expiry metadata,
task-run/worktree attempt attribution for path leases, exact-path active
conflict protection, transaction-scoped project namespace locking, and
service-level path normalization for separators and case handling plus
repository-boundary canonicalization. It also persists
PathLease wait-for edges with bounded timeouts, cancellation, FIFO queue
position, repeated-contention escalation, and deterministic two-owner deadlock
victim selection. Governed task startup now binds the runner worktree, branch,
and immutable source commit into a persisted `WorktreeAttemptManifest`; worktree
validation now rejects dirty or target-drifted manifests.

This is candidate evidence only. Final R5 acceptance still requires restart
resource reconciliation coverage across all owned resources.

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
| Transactional namespace mutex | `PathLeaseProjectLockORM` serializes PathLease acquisition for each project before overlap checks, preventing concurrent parent/child acquisitions from passing identical pre-check windows. |
| Path lease fencing | `PathLease` now records `fencing_token`, heartbeat, attempt number, and worktree path. |
| Path lease renewal | `renew_lease()` extends an active lease only when owner and fencing token match. |
| Expired lease reclaim | Expired/released active keys can be reclaimed by a new fenced owner. |
| Path lease wait graph | `PathLeaseWaitORM` persists bounded wait-for edges with queue position, expiry, cancellation, and status. |
| Repeated contention escalation | Duplicate waits for the same owner/path increment `contention_count` and transition to `ESCALATED` after a deterministic threshold instead of busy-waiting. |
| Deadlock victim selection | `enqueue_wait()` detects two-owner wait cycles and marks the lexicographically deterministic victim as `DEADLOCK_VICTIM`. |
| Governed worktree manifest | `GovernedExecutionService.start_task()` persists a `WorktreeAttemptManifest` with worktree path, branch, source commit, runner owner, task run, and attempt number when runner setup returns a source commit. |
| Real worktree inspection | `WorktreeManager.setup_worktree_attempt()` resolves the base ref to an immutable source commit before creating the Git worktree; real temp-Git lifecycle coverage inspects the worktree on disk. |
| Cleanliness and target drift validation | `WorktreeService.validate_repository_state()` checks `git status --porcelain`, current `HEAD`, project default branch commit, and persisted source commit, rejecting dirty or drifted manifests. |
| Manifest-led orphan cleanup | `WorktreeManager.cleanup_orphan_worktrees()` removes only non-active worktree directories that are registered in `WorktreeAttemptManifest`; unregistered physical directories under `.localforge/worktrees` are preserved as user-owned/diagnostic paths. |
| Failed-worktree diagnostic retention | `WorktreeManager.cleanup_worktree()` retains `FAILED_SAFE` worktrees for post-failure diagnosis and marks their manifests `REJECTED`; successful/cancelled cleanup removes the directory and marks manifests `CLEANED`. |

## Validation Commands

```text
python -m pytest backend\tests\test_phase_r5_coordination.py backend\tests\test_phase6_runner_pool_governance.py backend\tests\test_phase6_worktrees_path_intents.py -q
19 passed, 1 skipped in 2.38s

python -m pytest backend\tests\test_phase_r5_coordination.py::test_r5_parent_child_path_race_is_serialized_by_database -q
1 passed in 0.28s

python -m pytest backend\tests\test_phase_r5_coordination.py backend\tests\test_phase6_worktrees_path_intents.py backend\tests\test_phase6_runner_pool_governance.py -q
20 passed, 1 skipped in 2.40s

python -m mypy backend\localforge\services\path_lease.py backend\localforge\storage\orm.py backend\localforge\storage\bootstrap.py backend\tests\test_phase_r5_coordination.py
Success: no issues found in 4 source files

python -m ruff check backend\localforge\services\path_lease.py backend\localforge\storage\orm.py backend\localforge\storage\bootstrap.py backend\tests\test_phase_r5_coordination.py
All checks passed!

python -m pytest backend\tests\test_storage.py -q
2 passed in 0.08s

python -m pytest backend/tests/test_phase_r5_coordination.py backend/tests/test_phase6_runner_pool_governance.py backend/tests/test_phase6_worktrees_path_intents.py backend/tests/test_storage.py backend/tests/test_phase_r1_release_integrity.py -q
17 passed in 12.39s

python -m mypy backend\localforge\services\path_lease.py backend\tests\test_phase_r5_coordination.py
Success: no issues found in 2 source files

python -m ruff check backend\localforge\services\path_lease.py backend\tests\test_phase_r5_coordination.py
All checks passed!

python -m pytest backend\tests\test_phase_r5_coordination.py -q
12 passed, 1 skipped in 1.03s

python -m pytest backend\tests\test_scheduler.py::test_scheduler_uses_runner_pool_to_prepare_task_execution -q
1 passed in 0.36s

python -m pytest backend\tests\test_scheduler.py -q
9 passed in 2.00s

python -m pytest backend\tests\test_gitops.py::test_worktree_manager_setup_and_isolation -q
1 passed in 1.14s

python -m pytest backend\tests\test_phase6_worktrees_path_intents.py -q
4 passed in 1.33s

python -m pytest backend\tests\test_audit_store.py::test_orphan_worktrees_cleanup -q
1 passed in 0.28s

python -m pytest backend\tests\test_audit_store.py backend\tests\test_phase6_worktrees_path_intents.py backend\tests\test_phase_r5_coordination.py -q
20 passed, 1 skipped in 2.21s

python -m mypy backend\localforge\gitops\manager.py backend\tests\test_audit_store.py
Success: no issues found in 2 source files

python -m ruff check backend\localforge\gitops\manager.py backend\tests\test_audit_store.py
All checks passed!

python -m pytest backend\tests\test_audit_store.py::test_failed_safe_worktree_is_retained_for_diagnostics -q
1 passed in 0.27s

python -m pytest backend\tests\test_audit_store.py backend\tests\test_gitops.py backend\tests\test_scheduler.py::test_scheduler_uses_runner_pool_to_prepare_task_execution -q
11 passed in 3.76s
```

## Remaining Acceptance Requirements

- Parent/child overlap conflicts are serialized at the database transaction
  layer with a project namespace mutex before service-level overlap checks.
- Repository-boundary canonicalization and symlink escape rejection are covered
  where the host permits symlink creation.
- FIFO wait queues, timeout/cancellation, persisted wait-for graph, and
  deterministic two-owner deadlock victim selection are covered by R5
  regression tests. Repeated contention now transitions to `ESCALATED` instead
  of silently busy-waiting.
- RunnerPool backpressure is bounded and reported separately from permanent
  incompatibility.
- Real Git worktree creation and branch/base-commit binding are covered.
  Repository cleanliness, target-branch drift validation, and manifest-led
  orphan cleanup that preserves unregistered user-owned paths are covered.
  Failed worktrees are retained for diagnostics while successful/cancelled
  terminal cleanup removes directories and records `CLEANED`.
- Full kill/restart release and reconciliation across every owned resource
  remains open.
