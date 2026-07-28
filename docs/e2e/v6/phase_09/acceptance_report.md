# Phase 9 Acceptance Report — Server-Owned Dynamic Task DAG and Deep Swarm

> **Phase ID**: Phase 9 (`V6-900` through `V6-904`)
> **Backlog**: `docs/MASTER_BACKLOG_V6.md`
> **Status**: `EVIDENCE_READY`
> **Date**: 2026-07-27

## Executive Summary

Phase 9 now provides a server-owned, versioned task graph for bounded dynamic
expansion. Agents can propose one of the registered mutation operations, but
they cannot directly change canonical status or dependencies. Agent proposals
require an enabled Deep Swarm run and are rejected when stale, unowned, unsafe,
cyclic, over budget, over capacity, or outside registered artifact and decision
contracts.

The interrupted implementation initially had 19 green tests but did not satisfy
several claimed contracts: replay returned the latest snapshot without replaying
the journal; ownership and most policy bounds were not enforced; Deep Swarm
budgets were not connected to mutation execution; and restart handling could
repeat an external action under a new identity. Those gaps are closed in the
current evidence.

## Verified Capabilities

- **V6-900**: Version 0 snapshots, explicit mutation sequences, complete
  mutation hashes, append-only uniqueness constraints, contiguous replay, and
  divergence detection.
- **V6-901**: Seven public mutation operations with ownership, stale-version,
  acyclicity, node, depth, fan-out, typed-artifact, registered-decision,
  resource, cost, paid-call, justification, and server-owned-field validation.
- **V6-902**: Atomic/composite behavior, explicit critique and verification
  gates, deterministic failure propagation, and preservation of completed
  partial results.
- **V6-903**: Experimental opt-in execution with Light Swarm and single-worker
  fallback, ready-queue advancement, and mutation, worker, duration, cost,
  paid-call, and stall limits.
- **V6-904**: Replay-verified restart reconciliation, ready-queue restoration,
  persisted worktree-attempt/path-lease/typed-artifact reporting, corruption
  escalation, and stable external-action idempotency keys.

## Validation

- Phase 9 tests: **25 passed**.
- Related Light Swarm, storage, bootstrap, API, and CLI tests: **25 passed**.
- Full backend regression: **260 passed**.
- Mypy: **191 source files checked, 0 errors**.
- Phase 9 ruff scope: **0 errors**.
- Frontend Vitest: **5 passed**.

The repository-wide ruff command still reports **528 pre-existing findings**
outside the Phase 9 cleanup scope. This debt is recorded rather than hidden; the
new Phase 9 service, routes, CLI, and tests pass targeted ruff.

## Verdict and Remaining Gate

Technical verdict: `EVIDENCE_READY`.

`PHASE_ACCEPTED` is intentionally not claimed yet. The mandatory synchronization
gate still requires the feature branch pull request, successful remote checks,
human review, and reviewed merge. Deep Swarm remains disabled by default until
Phase 11 supplies comparative evidence.
