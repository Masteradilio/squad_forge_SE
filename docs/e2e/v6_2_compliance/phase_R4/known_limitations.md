# Phase R4 Known Limitations

- This is candidate evidence, not final release acceptance.
- Interval and cron schedule execution now works through durable trigger
  metadata, idempotency keys, and database compare-and-swap claim fencing.
- Authenticated provider-neutral external events now require signed or bearer
  credentials, bounded payloads, replay windows, provider rate limits, stable
  provider event IDs, and persisted idempotency keys.
- Pause prevents new due-schedule claims; kill/restart cascade over scheduler
  runs, task runs, subprocesses, RunnerPool leases, PathLeases, worktrees, and
  external reservations remains incomplete.
