# ForgeOS V8 - LoopX-like Durable Work Control Plane

> Version: 0.1
>
> Status: implementation in progress
>
> Continues: `MASTER_BACKLOG_V7.md`

## Purpose

V8 turns ForgeOS into a LoopX-like long-running work system without replacing
its domain engine, PRD compiler, OmniRoute routing, sandbox, safety kernel, or
Pull Request factory. The goal is to make unattended work restartable,
reviewable, bounded, and explicit about the next safe action.

This is a clean-room design. ForgeOS keeps the domain database as the source of
truth for projects, tasks, runs, artifacts, costs, and PRs. The control plane is
the durable operational projection for goals, claims, gates, evidence, quota,
signals, and handoffs. No chat session, browser tab, or model context is a
source of truth.

## V8 release contract

V8 is not accepted because unit tests pass. A real small-PRD run must prove:

1. The objective, non-negotiables, authority, and current frontier survive a
   process restart without manual reconstruction.
2. Every executor action is one bounded, leased, idempotent turn owned by a
   registered worker.
3. Every state transition has a typed receipt and validated evidence.
4. The controller emits one explicit next action: `READY`, `WAIT`, `REPAIR`,
   `REPLAN`, `ASK`, `BLOCKED`, or `COMPLETE`.
5. Provider, CI, review, timeout, and host-interruption signals are persisted
   and can wake or stop the run without polling storms.
6. A blocker is diagnosed once, handed to the correct authority, repaired under
   contract, and either reopened with evidence or escalated honestly.
7. Quota, cost, retries, and human-attention budget are enforced before work.
8. A review packet can reconstruct what changed, why it changed, which checks
   passed, what remains gated, and which PRs are safe for human review.
9. A restart/interruption benchmark demonstrates no duplicate writeback,
   orphaned lease, silent success, or infinite retry loop.
10. The product benchmark reaches `COMPLETED` with all tasks `PR_READY`, or is
    classified `BLOCKED` with a reproducible external cause.

`PR_READY` remains an engineering-evidence status. It never means auto-merge,
production deployment, or human acceptance.

## Ten priority workstreams

### Phase 83 - Durable objective and authority

- [ ] Persist goal vision, scope, non-negotiables, authority, source revision,
  acceptance target, and human gates as a versioned control-plane record.
- [ ] Give every registered agent an identity, capabilities, allowed actions,
  and lease ownership; keep human approval as an explicit authority boundary.
- [ ] Add a compact `status` and `review-packet` projection that is safe to show
  without exposing prompts, credentials, or raw model transcripts.

**Gate:** a fresh process and a new host can recover the same goal and authority
without reading chat history.

### Phase 84 - Server-owned executable frontier

- [ ] Derive the next executable todo exclusively from the persisted task DAG,
  dependencies, gates, blockers, and accepted receipts.
- [ ] Reject client-provided task order, synthetic todos, stale task status, and
  writeback that does not match the current frontier revision.
- [ ] Expose `next` as a pure decision operation with `wait_until` and a reason
  suitable for a scheduler heartbeat.

**Gate:** two workers observing the same state receive deterministic compatible
decisions and cannot claim the same todo.

### Phase 85 - Bounded turns, leases, and idempotency

- [ ] Make every model, sandbox, test, and GitHub operation a bounded turn with
  owner, lease, timeout, attempt number, and idempotency key.
- [ ] Reconcile expired leases on startup, cancel orphaned work, and preserve
  the exact interruption reason.
- [ ] Prevent duplicate receipts, duplicate costs, duplicate PR writes, and
  stale revisions from mutating the domain.

**Gate:** kill/restart during a turn leaves one recoverable state and no second
  charge or duplicate delivery.

### Phase 86 - Typed evidence and event journal

- [ ] Append a tamper-evident control-plane event for each claim, decision,
  provider observation, validation, handoff, writeback, gate change, and stop.
- [ ] Keep a materialized snapshot for fast status while retaining the event
  sequence for replay and forensic recovery.
- [ ] Validate changed-file, check, source-revision, and actor receipts before
  accepting progress.

**Gate:** rebuilding the snapshot from the event journal produces the same
frontier, receipts, quota, and final decision.

### Phase 87 - Decision engine and human gates

- [ ] Make `READY`, `WAIT`, `REPAIR`, `REPLAN`, `ASK`, `BLOCKED`, and `COMPLETE`
  mutually explicit, typed decisions rather than log messages.
- [ ] Persist user gates with the question, decision authority, safe default,
  affected lane, expiry, and answer receipt.
- [ ] Allow safe independent work to continue while a separate lane waits for a
  human decision, without bypassing the gate.

**Gate:** an unanswered gate pauses only its affected route and is visible in the
first-screen status projection.

### Phase 88 - Quota, cost, and attention governance

- [ ] Reserve and commit model, sandbox, wall-time, retry, and human-attention
  budgets transactionally with accepted writeback.
- [ ] Add provider/model availability as a bounded capability signal, not an
  unbounded retry trigger.
- [ ] Produce per-run and per-PR cost/economy receipts with the active pricing
  snapshot and route identity.

**Gate:** quota exhaustion yields `WAIT` or `BLOCKED` with an operator action;
it cannot keep spending or polling.

### Phase 89 - Recovery, handoff, and self-evolution lane

- [ ] Separate Scrum Master diagnosis, Chief Engineer repair, and executor
  implementation into typed handoffs with authority and allowed scope.
- [ ] Persist provider, CI, review, conflict, and host-interruption signals as
  repairable observations with deduplication keys.
- [ ] Allow capability improvements only in an isolated, reviewable lane; the
  active product goal may resume only after the new capability passes its own
  checks and is written back.

**Gate:** the same blocker cannot trigger an identical retry storm; a changed
repair route or honest escalation is required.

### Phase 90 - External work and PR lifecycle

- [ ] Add durable cursors/adapters for GitHub PR checks, review comments,
  conflicts, upstream commits, and provider availability.
- [ ] Treat PR head SHA, check-run state, review state, and merge authority as
  domain evidence, never as model claims.
- [ ] Generate one review packet per PR and one consolidated packet per goal.

**Gate:** a new CI or review signal wakes the correct todo without losing the
existing objective or duplicating work.

### Phase 91 - Runtime adapters and operator surfaces

- [ ] Expose the same control-plane contract through CLI, API, dashboard, and a
  generic worker bridge; no surface may become a second source of truth.
- [ ] Support bounded heartbeat scheduling with `should-run`, `next action`,
  pause, resume, diagnose, and recovery commands.
- [ ] Keep runtime state, transcripts, secrets, and caches outside Git.

**Gate:** an operator can stop, inspect, resume, and hand off a run using only
the CLI after the original process is gone.

### Phase 92 - Long-running acceptance and product benchmark

- [ ] Add a restart/interruption fixture and a real small-PRD benchmark with a
  deliberately injected provider/validation blocker.
- [ ] Measure accepted PR rate, bounded turns, recovery count, duplicate work,
  elapsed wall time, model calls, cost, quota use, and human interventions.
- [ ] Run HP12C only after the small benchmark reaches its V8 gate; classify any
  remaining HP12C failure by evidence instead of extending an opaque loop.

**Gate:** `ACCEPTED` requires all ten controls, a completed small product run,
and a review packet. `BLOCKED` requires a reproducible external dependency.

## Evidence layout

Each accepted phase writes:

- `docs/e2e/v8/phase_<NN>/manifest.json`
- `docs/e2e/v8/phase_<NN>/control_plane.json`
- `docs/e2e/v8/phase_<NN>/events.jsonl`
- `docs/e2e/v8/phase_<NN>/acceptance_report.md`

Runtime worktrees, databases, logs, model transcripts, credentials, and caches
remain outside Git. `CHANGELOG.md` is updated after every completed phase.
