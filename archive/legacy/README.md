# ForgeOS legacy archive

This directory contains recoverable code and fixtures removed from the active
ForgeOS pipeline on 2026-08-09. Nothing here is imported by the default
runtime or test suite. Historical benchmark reports and immutable run evidence
remain under `docs/` and `.localforge/artifacts/`.

## Archived because the active architecture supersedes it

- `backend/localforge/chief_engineer/contracts_service.py`: direct contract
  writer superseded by `ArchitectureContract`, `ContractVerifier`, and
  `SafeFileEditor`.
- `backend/localforge/healing/`: the former classifier/policy/repair engine;
  recovery is now owned by `Scheduler`, `RolePipelineEngine`, and the Chief
  Engineer control plane.
- `backend/localforge/integration/` and
  `backend/localforge/repair/classifier.py`: duplicate integration/failure
  taxonomy paths superseded by contract verification and the current repair
  playbooks. `repair/compiler_feedback.py` remains active.
- `backend/localforge/prd/tracer_compiler.py`: hard-coded single-ticket
  compiler with no active consumers.
- `backend/localforge/quality/scope_validator.py`: duplicate scope validator
  superseded by task contracts and the mechanical pre-PR gate.
- `backend/localforge/sandbox/container_runner.py`: preview URL/configuration
  helper, not an actual sandbox executor; active sandbox policy lives in the
  local/Docker sandbox adapters.
- `backend/localforge/services/deep_swarm_dispatcher.py` and
  `deep_swarm_governor.py`: orphaned Deep Swarm helpers superseded by the
  server-owned `TaskGraphService`.

## Archived historical/demo automation

The old demo mutator, benchmark evidence collector, V7 control runner, V8/V9
benchmark runners and their fixtures, the old V8 recovery fixture, and the
legacy self-healing/evidence tests are retained only for archaeology. The
current reference, full-coverage, readme-trace and V7 mini benchmark paths are
kept active because they are still used by current acceptance tooling.

Archive policy: restore a path only through a reviewed migration that adds a
current consumer and focused tests; do not import archived modules directly.
