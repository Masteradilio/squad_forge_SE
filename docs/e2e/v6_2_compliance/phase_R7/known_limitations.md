# Phase R7 Known Limitations

- This is candidate evidence, not final release acceptance.
- Graph mutation now requires registered decision evidence, but dynamic nodes
  still do not execute as real governed workers.
- Per-node resource ownership for RunnerPool, worktrees, PathLeases, budgets,
  and ActionGateway remains open.
- Recovery and cancellation still need a single durable reconciliation path for
  graph versions, queues, attempts, leases, artifacts, and external actions.
- Deep Swarm remains experimental and disabled/fallback-gated until later
  benchmark evidence is accepted.
