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
  selection are now candidate-implemented. Repeated contention now escalates
  deterministically instead of busy-waiting.
- RunnerPool restart reconciliation now rebuilds active capacity from persisted
  successful dispatch logs joined to active TaskRuns. Capacity saturation is
  reported as bounded backpressure with deterministic queue position.
- Governed task startup now persists worktree path, branch, immutable source
  commit, runner owner, task run, and attempt number. Repository cleanliness,
  target-branch drift validation, and manifest-led orphan cleanup that preserves
  unregistered user-owned directories are candidate-implemented. Failed
  worktrees are retained for diagnostics and marked `REJECTED`; successful or
  cancelled terminal cleanup removes the directory and marks manifests
  `CLEANED`.
