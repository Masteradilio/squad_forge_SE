# ForgeOS V9 - LoopX-like Long-Running Work Control Plane

> Version: 0.1
>
> Status: implementation in progress
>
> Date: 2026-08-05
>
> Continues: `MASTER_BACKLOG_V8.md`

## Purpose

V9 makes the ForgeOS control plane a durable operational product instead of a
set of run-local helpers. It adopts the strongest ideas of LoopX through a
clean-room implementation: lifetime goals, an executable frontier, bounded
turns, typed evidence, leases, quota, human gates, external signals, recovery,
worker bridges, and review packets.

ForgeOS keeps ownership of the domain engine, PRD compiler, task contracts,
OmniRoute routing, sandbox, safety kernel, validation, cost ledger, and PR
factory. The control plane does not execute model or shell actions and never
becomes a second domain database. Human approval remains required before merge,
deployment, or irreversible publication.

## V9 release contract

V9 is accepted only when a real small PRD proves all ten workstreams below:

1. A stable project goal survives process, session, worker, and host restart.
2. The server-owned DAG is the only source of executable todo order.
3. One worker can claim one bounded, leased, idempotent turn at a time.
4. Every observation becomes progress only through a typed receipt and evidence.
5. The kernel emits an explicit next action: `READY`, `WAIT`, `REPAIR`,
   `REPLAN`, `ASK`, `BLOCKED`, or `COMPLETE`.
6. Provider, CI, review, quota, and host signals are durable, deduplicated, and
   able to wake the affected lane without a polling storm.
7. A Scrum Master diagnosis and Chief Engineer repair handoff are explicit,
   bounded, and recoverable.
8. A worker bridge can stop, resume, and hand off work without chat history.
9. Self-evolution is isolated, reviewable, and cannot mutate the active goal
   before its own validation gate passes.
10. A real benchmark records cost, turns, recovery, duplicate prevention,
    human attention, and final PR evidence; it is `ACCEPTED` only when all
    tasks are `PR_READY` and the goal is `COMPLETED`, or honestly `BLOCKED` by
    a reproducible external dependency.

`PR_READY` is reviewable engineering evidence. It is not merge permission,
production acceptance, or a claim that an LLM is infallible.

## Architecture invariants

- The ForgeOS domain database owns projects, tasks, runs, artifacts, costs, and
  PRs.
- The V9 control plane owns durable goal identity, operational decisions,
  claims, leases, receipts, signals, gates, quota, and handoffs.
- A registry is only an index of goal locations and authority; it is not a
  second task state store.
- The scheduler remains the only executor. Worker bridges request a bounded
  decision and invoke the configured executor adapter; they do not write task
  status directly.
- Model output is an observation or proposal until deterministic validators and
  the safety kernel accept it.
- Retry budgets are finite. Repeated identical failures route to `WAIT`,
  `REPAIR`, `ASK`, or `BLOCKED`, never to an unbounded loop.
- Runtime state, transcripts, credentials, caches, and benchmark workspaces
  remain outside Git.

## Ten priority workstreams

### Phase 93 - Lifetime goal registry (LF-V9-9301 to LF-V9-9303)

- [x] Register one stable goal per project with vision, source revision,
  authority, state location, and active/inactive status.
- [x] Reconnect an existing goal without reconstructing it from chat or a new
  run identifier.
- [x] Add `connect`, `status`, and `review-packet` projections that redact
  secrets and raw model transcripts.

**Gate:** kill the CLI process, start a new process from the project root, and
recover the same objective, frontier, authority, and next action.

### Phase 94 - Server-owned frontier (LF-V9-9401 to LF-V9-9403)

- [ ] Make the persisted DAG, accepted receipts, gates, and blocker decisions
  the only inputs to the next todo.
- [ ] Reject synthetic todo order, stale source revision, stale frontier, and
  client-supplied success status.
- [ ] Return deterministic `next` decisions with reason and `wait_until`.

**Gate:** two workers cannot claim the same todo and a stale writeback cannot
change the frontier.

### Phase 95 - Bounded worker bridge (LF-V9-9501 to LF-V9-9503)

- [x] Expose a small `should-run`/`claim`/`writeback` worker protocol with one
  bounded turn per invocation.
- [x] Add a heartbeat runner with a minimum interval, maximum ticks, stop file,
  pause/resume, and no busy retry loop.
- [x] Provide CLI and API surfaces that remain usable after the original
  executor process exits.

**Gate:** terminate a worker during a lease and resume it later without a
duplicate receipt, duplicate cost, or orphaned claim.

### Phase 96 - Typed receipts and replay (LF-V9-9601 to LF-V9-9603)

- [ ] Require actor, source revision, changed files, checks, content hash, and
  idempotency key for accepted progress.
- [ ] Journal claim, observation, validation, handoff, gate, quota, writeback,
  and stop transitions with a verifiable hash chain.
- [ ] Prove snapshot rebuild and live state are equivalent.

**Gate:** tampering or incomplete writeback fails closed and replay reproduces
the same final decision.

### Phase 97 - Signals and attention queue (LF-V9-9701 to LF-V9-9703)

- [x] Persist provider, CI, review, conflict, host, and quota signals with
  source cursors and deduplication fingerprints.
- [x] Map a signal to its affected todo or gate and expose an attention queue.
- [x] Ensure unrelated work can continue without bypassing an affected gate.

**Gate:** one new CI/review signal wakes only the correct lane and duplicate
delivery is a no-op.

### Phase 98 - Scrum Master and Chief Engineer handoff (LF-V9-9801 to LF-V9-9803)

- [ ] Make diagnosis, authority, evidence, allowed scope, repair attempt, and
  repair validation separate typed records.
- [ ] Route repeated or high-risk failures to Chief Engineer or human review;
  never let the local worker self-approve its own repair.
- [ ] Preserve the original todo and objective while a repair lane runs.

**Gate:** an injected blocker produces a changed repair route or honest stop,
not an identical retry storm.

### Phase 99 - Quota, cost, and attention governance (LF-V9-9901 to LF-V9-9903)

- [ ] Reserve turns, wall time, model calls, API cost, sandbox time, and human
  attention before execution.
- [ ] Commit spend only with validated writeback and make quota exhaustion an
  explicit `WAIT` or `BLOCKED` decision.
- [ ] Include provider, model, pricing snapshot, recovery count, and attention
  cost in each PR and consolidated review packet.

**Gate:** an exhausted quota cannot continue polling or spending.

### Phase 100 - External lifecycle adapters (LF-V9-10001 to LF-V9-10003)

- [ ] Add bounded adapters for GitHub PR checks, review comments, conflicts,
  upstream revisions, and provider availability.
- [ ] Treat PR head SHA, checks, reviews, and merge authority as evidence from
  the external system, never as model claims.
- [ ] Generate one review packet per PR and one per goal.

**Gate:** a new external signal resumes the correct lane without duplicate PR
  mutation or lost objective context.

### Phase 101 - Isolated capability evolution (LF-V9-10101 to LF-V9-10103)

- [ ] Store capability proposals separately from active runtime configuration.
- [ ] Test a proposed capability in an isolated worktree/sandbox with its own
  receipt, reviewer, and promotion gate.
- [ ] Resume the active goal only after promotion or record a human gate.

**Gate:** a failed self-improvement proposal cannot corrupt the active goal or
  bypass the safety kernel.

### Phase 102 - Long-running product acceptance (LF-V9-10201 to LF-V9-10204)

- [ ] Create a small real PRD with at least one deterministic blocker and one
  repairable blocker.
- [ ] Run it through OmniRoute/ForgeOS with a kill/restart, provider wait,
  repair handoff, and bounded heartbeat.
- [ ] Export SQLite, control-plane, event, cost, PR, and review-packet evidence.
- [ ] Repeat the run and record accepted PR rate, turns, retries, recovery,
  duplicates, wall time, API cost, quota, and human interventions.

**Gate:** accept only `COMPLETED` plus all tasks `PR_READY`; otherwise report
`BLOCKED` with a reproducible external dependency. Run HP12C only after this
gate passes.

## Evidence layout

Each accepted phase writes:

- `docs/e2e/v9/phase_<NN>/manifest.json`
- `docs/e2e/v9/phase_<NN>/control_plane.json`
- `docs/e2e/v9/phase_<NN>/events.jsonl`
- `docs/e2e/v9/phase_<NN>/acceptance_report.md`

No document may claim V9 or HP12C success without current runtime evidence.
