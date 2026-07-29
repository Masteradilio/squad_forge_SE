# Phase R1 Known Limitations

- The candidate branch verifies wheel build/install, but a separate sdist build
  artifact still needs to be generated and validated before R1 can be accepted.
- The legacy database fixture currently proves schema-version migration,
  project-row preservation, backup, restore, and future-schema fail-safe
  behavior. Full preservation across runs, tasks, audit events, memory, graphs,
  leases, and artifacts still requires a broader fixture.
- Windows validation was run locally. Linux clean-install validation remains
  dependent on remote CI for the exact PR head.
- Phase R1 evidence remains `EVIDENCE_READY` until the PR is reviewed, merged,
  and final evidence is generated from GitHub state.
