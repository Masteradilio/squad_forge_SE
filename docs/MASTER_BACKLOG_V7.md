# ForgeOS V7 - Durable Agent Control Plane Backlog

> Version: 0.7
>
> Status: Implementation started
>
> Date: 2026-08-04
>
> Continues: `MASTER_BACKLOG_V6.md` and `compliance_backlog_V6-1.md`

## Purpose

V7 makes the ForgeOS execution contract explicit and durable. The system keeps
the existing PRD compiler, task DAG, sandbox, safety kernel, provider routing,
Scrum Master, Chief Engineer, typed evidence, and PR factory. This backlog adds
one control-plane boundary around them so a long-lived objective can resume
without relying on a chat session or a model's transient context.

This is a clean-room design inspired by public long-running-agent control-plane
ideas. It does not copy source code, schemas, prompts, or implementation from
any reference project. ForgeOS remains the source of truth for its own domain
and keeps human approval before merge or deployment.

## V7 release contract

V7 is accepted only when all ten controls below are exercised by a real run and
the evidence records the source revision, bounded turns, task receipts, quota,
handoffs, recovery decisions, and final PR status:

1. A durable goal and non-negotiable constraints exist for every unattended run.
2. The executable todo frontier is derived from the server-owned task DAG.
3. Every model/sandbox invocation is one bounded turn with a lease and an owner.
4. Progress is a typed receipt; observation alone never changes task state.
5. The kernel emits explicit `READY`, `WAIT`, `REPAIR`, `REPLAN`, `ASK`,
   `BLOCKED`, or `COMPLETE` decisions.
6. Quota and spend are checked before work and committed only with writeback.
7. Revisions, idempotency keys, leases, and atomic writeback make resume safe.
8. Handoffs carry the blocker, evidence, authority, and exact next action.
9. The Scrum Master diagnoses; the Chief Engineer repairs; neither can bypass
   the safety kernel or PR_READY evidence gate.
10. Restart/recovery resumes the same run or closes it honestly; no infinite
    polling, retry storm, or silent success is possible.

`PR_READY` still means “reviewable engineering evidence exists”. It does not
mean product acceptance, merge permission, or production deployment.

## Architecture rules

- The database remains the domain source of truth for projects, tasks, runs,
  artifacts, leases, and cost. The control-plane journal is a versioned,
  atomic per-run projection used for bounded scheduling and recovery.
- The scheduler remains the only executor. The control plane may approve a
  turn and record its result, but it never executes model or shell actions.
- The model may propose actions, plans, repairs, or graph mutations. Services
  validate and apply them through the Safety Kernel and task contracts.
- A verifier separate from the implementer must accept PR_READY evidence.
- All retries have a finite budget. Exhaustion becomes `BLOCKED_NEEDS_HUMAN_REVIEW`.
- API calls are attributed to run, task, attempt, provider, model, and cost.
- No auto-merge, force-push, or runtime dependency on Codex, Antigravity,
  Claude, or another external coding agent.

## Phases and tasks

### Phase 78 - Goal and frontier (LF-V7-7801 to LF-V7-7802)

- [x] Persist one schema-versioned goal per run with vision, constraints,
  current frontier, status, revision, and last accepted receipt.
- [x] Project the existing task DAG into a deterministic todo frontier with
  dependency and blocker information; do not create synthetic work.

**Gate:** a fresh run and a restarted process produce the same frontier.

### Phase 79 - Bounded turns and leases (LF-V7-7901 to LF-V7-7902)

- [x] Claim at most one bounded turn per task attempt with owner, lease token,
  expiry, attempt count, allowed action scope, and an idempotency key.
- [x] Reconcile expired leases and enforce max turns, max attempts, time, and
  spend without leaving the scheduler in an unbounded loop.

**Gate:** duplicate claims and stale writebacks are rejected without corrupting
the state.

### Phase 80 - Receipts and decisions (LF-V7-8001 to LF-V7-8002)

- [x] Require a hashed, typed receipt containing summary, evidence, changed
  files, checks, and validation actor before accepting progress.
- [x] Make the next action explicit: ready, wait, repair, replan, user action,
  blocked, or complete.

**Gate:** an observation or model response without validated receipt cannot make
a task PR_READY.

### Phase 81 - Quota and recovery handoff (LF-V7-8101 to LF-V7-8102)

- [x] Reserve bounded work before execution and commit cost only during an
  accepted result writeback; duplicate result keys do not spend twice.
- [x] Emit a Scrum Master blocker diagnosis and a Chief Engineer repair handoff
  with exact evidence and allowed scope; escalate after finite recovery.

**Gate:** a provider timeout, malformed action, or failed test yields an
auditable repair route instead of another identical retry.

### Phase 82 - Resume, evidence, and benchmark (LF-V7-8201 to LF-V7-8203)

- [x] Add operator CLI/API projections for status, next decision, pause, resume,
  and recovery without exposing secrets or making the dashboard authoritative.
- [x] Add a deterministic control-plane regression fixture covering restart,
  duplicate receipt, quota wait, blocked repair, and completion.
- [ ] Run a small real PRD benchmark before HP12C. Record accepted PR rate,
  bounded turns, recovery count, elapsed wall time, model calls, API cost, and
  human interventions. Do not claim success from documentation alone.

**Gate:** the benchmark is `PR_READY` for every task or explicitly `BLOCKED`
with a reproducible external cause. Only then reattempt HP12C.

## Evidence format

Each accepted phase writes a compact report under `docs/e2e/v7/phase_<NN>/`:

- `manifest.json`: source commit, environment, commands, exit codes, limits;
- `control_plane.json`: final redacted state projection;
- `acceptance_report.md`: task receipts, routes, blockers, cost, and verdict.

Runtime databases, worktrees, logs, model transcripts, secrets, and caches stay
outside Git. The root `CHANGELOG.md` is updated at every completed phase.
