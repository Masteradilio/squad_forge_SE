# LocalForge OS V6.2 Phase R4 Durable Loop Runtime Report

## Verdict

`EVIDENCE_READY`

Phase R4 adds a schedule runtime for interval and cron loops, a verified
external-event adapter, and persisted triage/recovery state for loop runs. It
validates schedules, defines timezone behavior, persists schedule state in
`LoopTrigger.metadata`, claims due schedules once, and lets the coordinator
execute claimed schedules through the durable `trigger_loop()` path. External
events now enter through `LoopCoordinator.trigger_external_event()` or the
dedicated webhook route.

This is candidate evidence only. Final R4 acceptance still requires provider
complete kill cascade over worker subprocesses/resources and restart
reconciliation of the entire ownership tree.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Interval validation | Schedules must use `<positive-int><s|m|h|d>`. |
| Cron validation | Cron schedules must contain five fields; wildcard, exact numeric fields, and minute steps are supported. |
| Timezone behavior | Schedule calculations use explicit `trigger.metadata.timezone`, defaulting to UTC, and persist UTC timestamps. |
| Misfire policy | `skip` advances past missed runs; `bounded_catchup` advances one occurrence at a time. |
| Durable schedule state | `next_run_at`, `last_trigger_at`, `trigger_revision`, `last_idempotency_key`, `timezone`, and `misfire_policy` are persisted in `LoopTrigger.metadata`. |
| Due schedule claim | `LoopService.claim_due_schedules()` advances schedule state and returns stable idempotency keys for due interval/cron loops. |
| Atomic multi-coordinator claim | Schedule advancement uses a database compare-and-swap fence on the loop definition `updated_at`; stale coordinators receive no claim after another coordinator advances the trigger. |
| Coordinator execution | `LoopCoordinator.trigger_due_schedules()` claims due schedules and executes them through `trigger_loop()`. |
| Pause guard | Paused or disabled loop definitions are not claimable. |
| Provider-neutral external adapter | `LoopCoordinator.trigger_external_event()` validates provider identity, timestamp, signature or bearer credentials, payload size, replay window, and provider rate limits before calling `trigger_loop()`. |
| External replay idempotency | Stable idempotency keys use `external:{loop_id}:{provider}:{event_id}` and replay returns the persisted `LoopRun` without duplicate tasks. |
| Untrusted payload sanitization | External payload text is recursively control-character stripped, prompt-injection phrases are removed, HTML is escaped, and field/string lengths are bounded before triage/task creation. |
| EVENT bypass guard | Direct `TriggerKind.EVENT` calls to `trigger_loop()` are rejected unless they carry the internal verified-envelope marker produced by the adapter. |
| Persisted triage evidence | `LoopRun` now stores triage input, classification, decision text, and resulting scheduler task IDs through schema version 17. |
| No fake actionable default | `force_actionable` without concrete items is persisted as `NO_OP` and creates no scheduler run or synthetic task. |
| Restart/retry identity | Recovery reuses `LoopRun.triage_input`, stable item idempotency keys, existing scheduler task IDs, and does not duplicate work after task creation. |
| Kill persisted ownership cascade | `LoopCoordinator.kill_loop_run()` cancels the associated scheduler run, cancels pending/running task runs, releases PathLeases, releases RunnerPool reservations, marks worktree attempt manifests `CANCELLED`, and is idempotent for repeated kill calls over those persisted owners. |

## Validation Commands

```text
python -m pytest backend\tests\test_phase6_circuit_breakers.py::test_kill_loop_run -q
1 passed in 0.33s

python -m pytest backend\tests\test_phase6_circuit_breakers.py backend\tests\test_phase6_loop_control_plane.py backend\tests\test_phase_r4_loop_runtime.py -q
24 passed in 1.39s

python -m mypy backend/localforge/models/enums.py backend/localforge/services/runner_pool.py backend/localforge/services/worktree.py backend/localforge/services/loop_coordinator.py backend/tests/test_phase6_circuit_breakers.py
Success: no issues found in 5 source files

python -m ruff check backend/localforge/models/enums.py backend/localforge/services/runner_pool.py backend/localforge/services/worktree.py backend/localforge/services/loop_coordinator.py backend/tests/test_phase6_circuit_breakers.py
All checks passed!
```

## Remaining Acceptance Requirements

- Kill now reconciles persisted scheduler, task-run, RunnerPool, PathLease, and
  worktree-manifest owners, but does not yet terminate actual controlled worker
  subprocesses, release external action reservations, or capture incomplete
  artifacts for interrupted subprocesses.
- Restart reconciliation still needs to recover or safely fail every orphaned
  owner in the full lifecycle tree.
