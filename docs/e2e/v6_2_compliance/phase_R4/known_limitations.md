# Phase R4 Known Limitations

- This is candidate evidence, not final release acceptance.
- Interval and cron schedule execution now works through durable trigger
  metadata, idempotency keys, and database compare-and-swap claim fencing.
- Authenticated provider-neutral external events now require signed or bearer
  credentials, bounded payloads, replay windows, provider rate limits, stable
  provider event IDs, and persisted idempotency keys.
- LoopRun triage input, classification, decision, and scheduler task IDs are
  persisted through schema version 17; restart recovery reuses that identity
  instead of inventing default actionable work.
- Restart recovery now reconciles the LoopRun/Scheduler Run relationship:
  missing scheduler owners safely fail, terminal scheduler states propagate back
  to the LoopRun, and active scheduler owners remain running.
- Pause prevents new due-schedule claims; kill now cancels the persisted
  scheduler run and pending/running task runs, releases PathLeases and
  RunnerPool reservations, marks worktree attempt manifests `CANCELLED`, and is
  idempotent for repeated kill calls over those persisted owners.
- The remaining kill/restart lifecycle cascade is still incomplete for actual
  controlled worker subprocess termination, external action reservations,
  incomplete artifact capture, and full orphan-owner restart reconciliation.
