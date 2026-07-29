# Phase R3 Known Limitations

- This is candidate evidence, not final release acceptance.
- `PRReadyEvidence` validates task-run ownership, branch/worktree consistency,
  typed `PR_READY` handoff ownership, independent identities and attempt IDs,
  risk/safety verdicts, pre-PR gate success, deterministic checks, non-empty
  source/target commit and diff hash fields, current task commit metadata,
  persisted worktree attempt source commit, and real persisted artifacts.
- Full ActionGateway bypass inventory and correlation coverage remain open.
- Stale evidence invalidation after dependency or test content changes remains
  open for broader graph-level tracking.
- Direct `run.verdict = "PR_READY"` behavior in Light Swarm is not a task-status
  readiness transition, but it remains a separate R6 cleanup item.
