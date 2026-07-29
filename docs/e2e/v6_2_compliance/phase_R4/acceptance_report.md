# LocalForge OS V6.2 Phase R4 Durable Loop Runtime Report

## Verdict

`EVIDENCE_READY`

Phase R4 adds a schedule runtime for interval and cron loops. It validates
schedules, defines timezone behavior, persists schedule state in
`LoopTrigger.metadata`, claims due schedules once, and lets the coordinator
execute claimed schedules through the existing durable `trigger_loop()` path.

This is candidate evidence only. Final R4 acceptance still requires provider
webhook authentication, full external-event replay windows, complete kill
cascade over worker subprocesses/resources, and restart reconciliation of the
entire ownership tree.

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

## Validation Commands

```text
python -m pytest backend/tests/test_phase_r4_loop_runtime.py backend/tests/test_phase6_loop_control_plane.py -q
14 passed in 0.92s

python -m mypy backend/localforge/models/loop.py backend/localforge/services/loop_runtime.py backend/localforge/services/loop_service.py backend/localforge/services/loop_coordinator.py backend/tests/test_phase_r4_loop_runtime.py
Success: no issues found in 5 source files

python -m ruff check backend/localforge/services/loop_runtime.py backend/localforge/services/loop_service.py backend/localforge/services/loop_coordinator.py backend/tests/test_phase_r4_loop_runtime.py
All checks passed!
```

## Remaining Acceptance Requirements

- Authenticated provider-neutral webhook adapters, signature verification,
  rate limits, bounded payloads, and replay windows remain open.
- Restart before/after triage is idempotent for existing run/item identity, but
  full ownership-tree reconciliation remains open.
- Kill does not yet terminate actual controlled worker subprocesses or release
  every RunnerPool, PathLease, worktree, and external action reservation.
