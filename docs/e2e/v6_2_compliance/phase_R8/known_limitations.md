# Phase R8 Known Limitations

- This is candidate evidence, not final release acceptance.
- The operational state store is file-backed and restart-durable, but not yet a
  database transaction fence for multiple workers.
- Daily Triage remains report-only, which is correct for L1, but source
  revision invalidation still needs canonical persisted event state.
- CI Sweeper and PR Babysitter still need real repository mutation paths,
  draft-only connector writes, independent verification, and remote state
  inspection.
- Production GitHub connector boundaries and controlled remote fixtures remain
  open.
