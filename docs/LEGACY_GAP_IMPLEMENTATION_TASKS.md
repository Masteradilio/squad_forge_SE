# Legacy Reference Gap Implementation Tasks

Date: 2026-06-21

Source: `docs/LEGACY_REFERENCE_CONFORMITY_REPORT.md`

Goal: remove every gap between `docs/LocalForge_OS_PRD.md` and the current
implementation, using original LocalForge code and schemas.

## P1 - Product/Architecture Compliance

- [x] Add first-class comments/thread storage for task-scoped discussion and
  context retrieval.
- [x] Add runtime registry and heartbeat records for local daemon/runtime
  registration.
- [x] Add explicit goal ancestry resolution from product document to epic, task,
  run/task-run, artifacts, and PR artifact.
- [x] Add missing PRD-listed CLI commands or command groups:
  `pause`, `resume`, `stop`, `tasks`, `task get`, `logs`, `replay`,
  `models list`, `skills list`, and `safety status`.

## P2 - Dashboard Surface Completion

- [x] Complete Worktrees view with dirty state, last commit, PR link, cleanup
  eligibility, and cleanup/revert actions.
- [x] Complete Settings view with project paths, Git provider, PR provider,
  model endpoint, sandbox mode, resource limits, and UI preferences.
- [x] Add model performance/failure metrics.
- [x] Add skill last-used, success-rate, enable/disable, and edit support.
- [x] Add Safety Center actions for lock project, revert unsafe worktree, and
  export audit log.
- [x] Strengthen secret/PR blocking beyond protected-file gates.

## P3 - Runtime Sophistication

- [x] Add explicit old-tool-output compression and retention policy.
- [x] Add JSON action proposal/tool-call fallback as a first-class runtime
  protocol.
- [x] Add optional squad/org hierarchy if retained as a required PRD concept.

## Exit Criteria

- `docs/LEGACY_REFERENCE_CONFORMITY_REPORT.md` shows no `Parcial` or `Lacuna`
  items for MVP-required PRD functionality.
- Targeted tests cover each implemented gap.
- Backend type checking passes.
- Frontend build passes after UI changes.
