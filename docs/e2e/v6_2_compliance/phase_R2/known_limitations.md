# Phase R2 Known Limitations

- The validator consumes trusted GitHub metadata supplied in the final manifest;
  live GitHub API querying and release-asset re-download validation remain
  future release-workflow work.
- Repository branch protection/ruleset enforcement remains an operational
  configuration task and cannot be claimed accepted from local code changes
  alone.
- R2 evidence remains `EVIDENCE_READY` until a reviewed PR is merged and final
  evidence is generated from immutable GitHub state.
