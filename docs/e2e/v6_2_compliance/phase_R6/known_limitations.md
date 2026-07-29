# Phase R6 Known Limitations

- This is candidate evidence, not final release acceptance.
- Light Swarm no longer manufactures `PR_READY`, but it also does not yet
  submit a complete typed evidence bundle to `TaskService.mark_pr_ready()`.
- The current service still advances nodes through `complete_node()` and
  `fail_node()` rather than real governed worker callbacks with ownership
  tokens.
- Executable nodes do not yet acquire RunnerPool reservations, worktrees, and
  PathLeases as first-class per-node resources.
- Retry, pause, kill, and restart reconstruction remain modeled at swarm state
  level rather than through persisted real worker attempts.
