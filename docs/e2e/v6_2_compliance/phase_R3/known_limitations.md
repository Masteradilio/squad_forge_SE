# Phase R3 Known Limitations

- This is candidate evidence, not final release acceptance.
- `PRReadyEvidence` validates task-run ownership, branch/worktree consistency,
  independent identities, pre-PR gate success, deterministic checks, and real
  persisted artifacts, but source/target commit binding is still incomplete.
- Full ActionGateway bypass inventory and correlation coverage remain open.
- Stale evidence invalidation after branch, dependency, test, or source changes
  remains open.
- Direct `run.verdict = "PR_READY"` behavior in Light Swarm is not a task-status
  readiness transition, but it remains a separate R6 cleanup item.
