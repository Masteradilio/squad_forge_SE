# ADR: Release promotion modes after PR_READY

Status: Accepted  
Date: 2026-08-08

## Decision

ForgeOS separates engineering evidence from release promotion with two
explicit modes:

- `human_approval` is the default. The scheduler pauses after all tasks reach
  `PR_READY`, persists an approval request, and waits for `localforge release
  approve`.
- `full_access` is opt-in. The server-owned release lane merges the `PR_READY`
  task branches into a clean configured target branch and invokes the
  post-merge `Tester` and `SafetyAuditor` lanes.

The Safety Kernel remains authoritative. Full access is not a bypass for path,
command, secret, conflict, budget, or audit controls. External GitHub/GitLab
merge and production deployment are outside this local promotion contract.

## State contract

The run keeps an immutable-enough release snapshot in its persisted
`resource_limits.release` object. Promotion state is recorded under
`release_promotion`, including the target branch, branch list, approval ID,
merge commit, post-merge results, and failure reason. This makes retries
idempotent: an already merged branch is skipped and an already decided
approval is reused by its idempotency key.

## Human boundary

`COMPLETED` after full-access promotion means that the configured technical
Tester and SafetyAuditor checks passed. It does not mean that a human accepted
the product, that UX was reviewed, or that production deployment occurred.

## Rationale

The default preserves ForgeOS's local-first safety posture while allowing
portfolio/SaaS demonstrations to exercise the entire path from PR_READY to a
tested local target branch. The two modes are explicit in configuration and
auditable rather than inferred from a generic unattended execution flag.
