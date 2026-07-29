# Phase R5 Known Limitations

- This is candidate evidence, not final release acceptance.
- Exact normalized path races are protected by an active conflict key, but
  parent/child overlap conflicts are not yet enforced by a database exclusion
  constraint across concurrent transactions.
- Path normalization covers separators and Windows case behavior; symlink
  resolution and repository-boundary canonicalization remain open.
- Lease renewal and fencing exist, but bounded FIFO waiting, persisted wait-for
  graph, timeout cancellation, and deterministic deadlock victim selection
  remain open.
- Worktree attempt manifests still track existing paths and stale paths, but a
  full real-Git worktree lifecycle with base-commit drift checks and diagnostic
  retention policy remains open.
