# Phase R5 Known Limitations

- This is candidate evidence, not final release acceptance.
- Exact normalized path races are protected by an active conflict key, but
  parent/child overlap conflicts are not yet enforced by a database exclusion
  constraint across concurrent transactions.
- Path normalization covers separators, Windows case behavior, repository-root
  canonicalization, and symlink escape rejection where the host permits symlink
  creation.
- Lease renewal and fencing exist. Bounded FIFO waiting, persisted wait-for
  graph, timeout cancellation, and deterministic two-owner deadlock victim
  selection are now candidate-implemented; repeated contention escalation is
  still open.
- RunnerPool restart reconciliation now rebuilds active capacity from persisted
  successful dispatch logs joined to active TaskRuns. Capacity saturation is
  reported as bounded backpressure with deterministic queue position.
- Worktree attempt manifests still track existing paths and stale paths, but a
  full real-Git worktree lifecycle with base-commit drift checks and diagnostic
  retention policy remains open.
