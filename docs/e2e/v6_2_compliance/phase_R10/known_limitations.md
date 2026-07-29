# Phase R10 Known Limitations

This is candidate evidence, not final production acceptance.

Open limitations:

- Full threat-model documentation and hosted authorization model are still
  incomplete.
- Dependency, secret, and static-security scans are not yet blocking release CI.
- Failure-injection coverage for coordinator/scheduler/worker crashes,
  database locks, disk-full behavior, provider failure, stale branches, and
  lost leases remains open.
- Capacity and backpressure measurements on representative CPU-only hardware
  remain open.
- CPU-only deployment/runbook coverage is not yet complete.

