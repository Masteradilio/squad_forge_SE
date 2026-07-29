# Phase R4 Known Limitations

- This is candidate evidence, not final release acceptance.
- Interval and cron schedule execution now works through durable trigger
  metadata, idempotency keys, and database compare-and-swap claim fencing.
- External event authentication, payload rate limits, replay windows, and
  provider-neutral webhook adapters remain open.
- Pause prevents new due-schedule claims; kill/restart cascade over scheduler
  runs, task runs, subprocesses, RunnerPool leases, PathLeases, worktrees, and
  external reservations remains incomplete.
