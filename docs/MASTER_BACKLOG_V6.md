# LocalForge OS — Loop and Swarm Engineering Master Backlog

> Version: 0.6
>
> Status: Planned
>
> Date: 2026-07-27
>
> Continues: `MASTER_BACKLOG_V5.md`
>
> Target: LocalForge V6 — governed operational loops and evidence-driven swarms

## 1. Objective

Close the V5 open-source-readiness work, then evolve LocalForge into a
software-engineering control plane with two clearly separated capabilities:

1. **Loop Control Plane** — durable, scheduled or event-driven operations with
   explicit state, budgets, circuit breakers, autonomy levels, and human
   escalation.
2. **Swarm Execution Engine** — bounded multi-agent execution driven by a
   server-owned task DAG, isolated worktrees, typed evidence, and independent
   verification.

The implementation should adopt the operational discipline described by
[loop-engineering](https://github.com/cobusgreyling/loop-engineering) and the
task-graph ideas documented by
[jcode](https://github.com/1jehuang/jcode), without copying unrelated terminal,
provider, self-development, or extreme-agent-count features.

## 2. Release Contract

V6 is complete only when:

- all 74 paths present in the initial V5 working-tree snapshot have been
  classified and resolved without discarding user work;
- V5 has a clean, reproducible, synchronized release boundary;
- loops are persisted, idempotent, budgeted, observable, pausable, and
  recoverable;
- L0–L3 autonomy is mechanically enforced by the server;
- L3 can work unattended only up to `PR_READY`; merge remains human-controlled;
- repeated failure and no-progress conditions open a deterministic circuit
  breaker;
- concurrent agents use bounded resources and isolated attempts;
- task dependencies transport typed, validated artifacts;
- Light Swarm and Deep Swarm have distinct limits and measured use cases;
- the implementer cannot be the sole verifier of its own work;
- safety enforcement cannot be bypassed by a prompt, skill, runner, or loop;
- Daily Project Triage, CI Sweeper, and PR Babysitter pass their evaluation
  contracts;
- comparative evidence demonstrates whether Loop and Swarm improved outcomes;
- final backend, frontend, integration, safety, recovery, and benchmark
  regressions pass;
- `README.md` and `CHANGELOG.md` describe only verified behavior;
- local `main` and `origin/main` end at the same reviewed commit with a clean
  working tree.

`PR_READY` remains a strict engineering evidence gate. It does not mean product
acceptance, permission to merge, or permission to deploy.

## 3. Non-Negotiable Invariants

- Deterministic services own state transitions, permissions, budgets, Git
  isolation, validation, and audit.
- Models may propose graph mutations and actions but cannot apply them directly.
- The server owns the canonical Loop, Run, Task DAG, lease, and circuit-breaker
  state.
- One actor may implement; a separate verifier must accept the evidence.
- No loop or swarm may auto-merge.
- Paid calls are attributed to a run, task, attempt, provider, and budget.
- Provider fallback occurs only for classified availability failures.
- Every retry is bounded and recorded.
- Every external side effect has an idempotency key.
- Every concurrent write has an owning attempt and workspace.
- State stored for restart must be schema-versioned.
- Generated artifacts, disposable worktrees, secrets, and runtime databases are
  not committed.
- A phase cannot be marked accepted because its token or time budget is nearly
  exhausted.

## 4. Execution and Evidence Policy

### 4.1 Task status

Use the following statuses in phase evidence:

- `PLANNED`
- `IN_PROGRESS`
- `BLOCKED`
- `EVIDENCE_READY`
- `PHASE_ACCEPTED`
- `PHASE_REJECTED`

### 4.2 Validation ladder

For every implementation task:

1. add or update the smallest relevant test;
2. run that test first;
3. run the nearest related test module;
4. run static checks for changed modules;
5. run the phase regression set;
6. run broad suites only at an explicit phase gate or in Phase 12.

Default static checks:

```text
ruff check backend
mypy backend
```

Frontend phases must also run the nearest Vitest module and the configured
frontend type/build checks.

### 4.3 Phase evidence

Store compact, committable evidence under:

```text
docs/e2e/v6/phase_<NN>/
  manifest.json
  test_summary.json
  acceptance_report.md
```

The manifest must include:

- phase and task IDs;
- source commit;
- environment summary;
- commands executed;
- exit codes;
- changed-module summary;
- test counts and failures;
- budget and provider attribution when applicable;
- known limitations;
- final phase verdict.

Large logs, worktrees, databases, model transcripts, caches, and generated
repositories must remain outside version control.

### 4.4 Mandatory phase synchronization gate

Every phase ends with the following reviewed synchronization workflow:

- [ ] Confirm the phase acceptance criteria and evidence are complete.
- [ ] Run `git diff --check` and inspect the scoped diff.
- [ ] Confirm no secret, runtime database, disposable worktree, cache, or large
      generated artifact is staged.
- [ ] Fetch `origin` and inspect ahead/behind/divergence before publishing.
- [ ] Commit only the accepted phase scope on its feature branch.
- [ ] Push the feature branch to the online repository.
- [ ] Open or update a pull request containing the phase evidence and known
      limitations.
- [ ] Require successful remote checks and human review.
- [ ] Merge without force-push or automatic merge.
- [ ] Fetch the merged result and fast-forward local `main`.
- [ ] Verify local `HEAD` equals `origin/main`.
- [ ] Verify the post-merge working tree contains only explicitly preserved work
      for later phases.

If local and remote history diverge, stop the synchronization gate and resolve
the divergence through a reviewed branch. Never reset, clean, rebase, or
force-push merely to satisfy the gate.

---

## Phase 0 — Consolidate V5 and Establish a Clean Release Boundary

### Goal

Resolve the 74 modified or untracked paths found on `main`, close the work
defined by `MASTER_BACKLOG_V5.md`, preserve all intentional user changes, and
create a clean synchronized baseline before Loop or Swarm development starts.

### V6-000 — Capture an immutable V5 working-tree inventory

- [x] Save the starting branch, commit, `git status --short`, diff statistics,
      staged state, untracked paths, and remote tracking status.
- [x] Record the initial count of 74 paths in the Phase 0 manifest.
- [x] Hash or otherwise identify the starting diff without committing generated
      artifacts.
- [x] Confirm whether every path belongs to V5 Phase 70–77, unrelated user work,
      generated output, or an accidental artifact.
- [x] Do not modify, move, delete, or ignore a path until it is classified.

**Acceptance**

- Every starting path has an inventory entry and a disposition owner.
- The original state can be reconstructed from Git objects, patches, or an
  explicitly preserved local backup.

### V6-001 — Compare local V5 work with the online repository

- [x] Fetch `origin` without merging.
- [x] Record the local and remote commit IDs and ahead/behind counts.
- [x] Inspect remote changes that overlap the 74 local paths.
- [x] Mark overlapping files as requiring manual reconciliation.
- [x] Stop if the branch has unexpected divergence or the remote repository is
      not the intended LocalForge repository.

**Acceptance**

- The Phase 0 report states whether local `main` is ahead, behind, equal, or
  diverged.
- No remote change is silently overwritten.

### V6-002 — Reconcile the inventory with V5 Phases 70–77

- [x] Map every intentional path to Runtime Integrity, Provider Reliability,
      Product Contract, Packaging, Governance, Maintainability, Comparative
      Evaluation, or Release Candidate work.
- [x] Identify incomplete V5 acceptance criteria.
- [x] Separate source changes from documentation, tests, evidence, caches,
      runtime databases, and disposable benchmark output.
- [x] Identify benchmark-specific logic that must not remain in
      `backend/localforge/`.
- [x] Identify unrelated user work and preserve it on a separate reviewed branch
      or patch before V5 closure.

**Acceptance**

- The inventory has no `unknown` disposition.
- Unrelated work is preserved without contaminating the V5 release.

### V6-003 — Complete V5 runtime and provider integrity

- [x] Finish removal of benchmark-domain behavior from the product runtime.
- [x] Finish real preflight diagnostics for Docker, Ollama, providers, and other
      required local services.
- [x] Verify routing-contract persistence and provider attribution.
- [x] Verify fallback is restricted to timeout, connection, rate-limit, and
      provider-server availability failures.
- [x] Verify authentication, billing, validation, and configuration failures
      surface directly.
- [x] Confirm paid calls remain visible in the cost ledger.

**Targeted regression**

- [x] Run provider routing and fallback tests.
- [x] Run benchmark-evidence tests.
- [x] Run pipeline tests nearest to every changed runtime module.
- [x] Test `stdout=None` and undecodable Git subprocess output on Windows.

**Acceptance**

- Runtime behavior contains no benchmark-specific shortcut.
- Routing evidence is persisted and auditable.

### V6-004 — Complete V5 packaging and first-run work

- [x] Verify standards-based package metadata and the `localforge` entry point.
- [x] Verify clean installation in the supported Python environment.
- [x] Verify the non-destructive smoke command without paid credentials.
- [x] Verify frontend installation and build instructions.
- [x] Confirm `.gitignore` covers local databases, worktrees, caches, artifacts,
      credentials, and generated benchmark repositories.

**Targeted regression**

- [x] Run package build/install smoke validation.
- [x] Run CLI smoke tests.
- [x] Run the nearest frontend build and unit tests.

**Acceptance**

- A clean environment can install and start the supported smoke path.

### V6-005 — Complete V5 modular-maintainability work

- [x] Finish provider construction and routing-policy extraction.
- [x] Finish API route modularization without changing public endpoints.
- [x] Finish frontend shell separation into navigation, project state, and
      feature views.
- [x] Add or complete unit tests for extracted behavior.
- [x] Remove dead compatibility paths only after callers and tests are migrated.

**Targeted regression**

- [x] Run API contract tests for affected endpoints.
- [x] Run scheduler/pipeline tests affected by provider extraction.
- [x] Run frontend component and utility tests for extracted behavior.

**Acceptance**

- Extraction does not change public behavior.
- The pipeline, API app, and frontend shell no longer own unrelated concerns.

### V6-006 — Complete V5 comparative evidence

- [x] Validate frontier-only, economy-API-only, local-only, and hybrid manifests.
- [x] Use identical task contracts and acceptance tests.
- [x] Record cost, duration, retry, human-intervention, and routing evidence.
- [x] Require every planned task to reach `PR_READY` before an `ACCEPTED`
      benchmark verdict.
- [x] Mark incomplete evidence `PARTIAL` or `REJECTED`; do not lower the gate.

**Targeted regression**

- [x] Run `backend/tests/test_benchmark_evidence.py`.
- [x] Run the V4 benchmark acceptance tests nearest the changed code.
- [x] Validate evidence hashes and source commit references.

**Acceptance**

- Published V5 claims do not exceed reproducible evidence.

### V6-007 — Produce the V5 release-candidate report

- [x] Update `MASTER_BACKLOG_V5.md` with actual completion status.
- [x] Create a V5 release-candidate acceptance report.
- [x] Record deferred work explicitly as V6 scope.
- [x] Reconcile architecture, roadmap, policies, and benchmark methodology.
- [x] Confirm open-source governance files are present and consistent.

**Acceptance**

- V5 has one authoritative release contract and one final verdict.

### V6-008 — Run the V5 closeout regression

- [x] Run targeted tests for all 74 affected paths.
- [x] Run the nearest backend integration set.
- [x] Run frontend tests and build validation.
- [x] Run Ruff and mypy.
- [x] Run clean package installation and smoke validation.
- [x] Record failures without truncating the acceptance gate.

**Acceptance**

- V5 is accepted only if required tests pass and every unresolved failure has a
  documented blocking disposition.

### V6-009 — Clean and synchronize the V5 boundary

- [x] Remove only generated or accidental files identified by the inventory.
- [x] Preserve unrelated user work before cleanup.
- [x] Confirm every one of the original 74 paths is committed, intentionally
      ignored, or preserved outside the V5 release branch.
- [x] Complete the mandatory phase synchronization gate.
- [x] Verify local `main` and `origin/main` point to the accepted V5 commit.
- [x] Verify a clean working tree before Phase 1 begins.

**Phase 0 exit gate**

- [x] V5 verdict is `PHASE_ACCEPTED`.
- [x] All 74 starting paths have resolved dispositions.
- [x] Local and online `main` are synchronized.
- [x] The working tree is clean.
- [x] V6 development starts from a new branch created from the accepted V5
      commit.

---

## Phase 1 — Loop Coordinator and Durable Loop State

### Goal

Add a Loop Control Plane above the existing scheduler. The coordinator decides
when work should run; the scheduler remains the execution engine for actionable
work.

### V6-100 — Define the Loop domain

- [x] Add `LoopDefinition`, `LoopTrigger`, `LoopRun`, `LoopItem`, and
      `LoopStateSnapshot` domain models.
- [x] Include project, repository, enabled state, trigger, detector,
      execution strategy, autonomy, budget, safety policy, and escalation policy.
- [x] Add schema versions to persisted configuration and state.
- [x] Define stable statuses and legal state transitions.
- [x] Define idempotency keys for triggers and external items.

**Acceptance**

- Illegal transitions and duplicate trigger/item keys are rejected
  deterministically.

### V6-101 — Add persistence and upgrade compatibility

- [x] Add ORM/repository support for Loop entities.
- [x] Define a versioned database upgrade path before creating new tables.
- [x] Add uniqueness constraints for trigger and external-item idempotency.
- [x] Preserve compatibility with existing Project, Run, Task, TaskRun, Audit,
      and Artifact records.
- [x] Add export/import support for human-readable Loop definitions.

**Targeted regression**

- [x] Add persistence round-trip tests.
- [x] Test upgrade from a V5 database fixture.
- [x] Test duplicate trigger and item insertion.

### V6-102 — Implement Loop Coordinator

- [x] Implement manual, interval, cron-like, and event-trigger interfaces.
- [x] Run a cheap detector/triage stage before creating an execution Run.
- [x] Persist no-op outcomes without spawning workers.
- [x] Create a scheduler Run only for actionable items.
- [x] Resume pending Loop Runs after process restart.
- [x] Prevent overlapping execution unless the Loop policy explicitly allows it.

**Targeted regression**

- [x] Trigger deduplication.
- [x] No-op triage creates no TaskRun.
- [x] Actionable triage creates exactly one Run.
- [x] Restart resumes without duplicate external actions.
- [x] Disabled or paused loops do not execute.

### V6-103 — Add Loop API and CLI surfaces

- [x] Add create, inspect, list, enable, disable, pause, resume, run-now, and
      history operations.
- [x] Validate definitions before persistence.
- [x] Display last run, next eligible run, verdict, cost, and circuit status.
- [x] Keep destructive or externally acting operations approval-aware.

**Targeted regression**

- [x] API schema and authorization tests.
- [x] CLI parsing and exit-code tests.
- [x] Invalid schedule, budget, and policy tests.

### V6-104 — Add Loop audit events

- [x] Record trigger receipt, deduplication, triage, no-op, Run creation, pause,
      resume, escalation, and completion.
- [x] Correlate Loop Run, scheduler Run, Tasks, attempts, artifacts, and costs.
- [x] Redact untrusted external payloads.

**Phase 1 regression**

- [x] New Loop domain/repository tests.
- [x] Scheduler regression.
- [x] Audit-store regression.
- [x] V5 project/run/task compatibility regression.

**Phase 1 exit gate**

- [x] A persisted report-only loop survives restart and executes idempotently.
- [x] No duplicate Run is created for the same trigger/item.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 2 — Circuit Breakers, Progress Detection, and Kill Controls

### Goal

Extend existing time, cost, attempt, and recovery limits with deterministic
failure fingerprints and no-progress detection.

### V6-200 — Define failure and progress signals

- [x] Normalize errors into stable fingerprints.
- [x] Record test-result signature, diff signature, artifact signature, and
      progress counters per attempt.
- [x] Define `progress`, `stagnation`, `regression`, and `repeated_failure`.
- [x] Exclude timestamps, random IDs, and irrelevant paths from fingerprints.

### V6-201 — Implement persistent circuit-breaker state

- [x] Add closed, open, cooldown, half-open, and escalated states.
- [x] Add thresholds for identical errors, no progress, regression, time, cost,
      attempts, and aggregate daily consumption.
- [x] Scope breakers to Loop, Run, external item, task, and provider as needed.
- [x] Persist the exact reason and evidence that opened the breaker.

### V6-202 — Integrate breaker decisions with scheduler and healing

- [x] Check the breaker before retries, recovery cycles, and paid calls.
- [x] Stop retries when the same normalized failure repeats.
- [x] Prevent healing from reverting and reapplying the same ineffective patch.
- [x] Escalate with a compact summary, last relevant error, attempted remedies,
      and requested human decision.
- [x] Never translate an open breaker into `PR_READY`.

### V6-203 — Add pause, resume, and kill

- [x] Add project, Loop, Loop Run, scheduler Run, and task pause controls.
- [x] Add a kill operation that stops future actions and releases resources.
- [x] Preserve evidence and state after kill.
- [x] Require an auditable actor and reason for manual resume.

**Targeted regression**

- [x] Repeated identical error opens the breaker.
- [x] Semantically different errors do not share a fingerprint accidentally.
- [x] Progress resets the stagnation counter.
- [x] Token, cost, time, and daily aggregate budgets stop execution.
- [x] Restart preserves open/cooldown state.
- [x] Kill cancels pending work and releases leases.
- [x] No breaker state produces an unearned success verdict.

**Phase 2 exit gate**

- [x] Infinite retry and repeated-patch fixtures terminate deterministically.
- [x] Escalation evidence explains why automation stopped.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 3 — Progressive Autonomy and Independent Maker/Checker

### Goal

Implement L0–L3 autonomy as enforced server policy and make independent
verification mandatory for code-changing work.

### V6-300 — Define autonomy levels

- [x] L0: definition, plan, and simulation only.
- [x] L1: report-only inspection with no repository mutation.
- [x] L2: isolated implementation, validation, and draft PR with human review.
- [x] L3: unattended execution up to `PR_READY`, still without merge.
- [x] Define permitted actions, required approvals, maximum budgets, and
      escalation behavior for each level.

### V6-301 — Enforce autonomy in the action path

- [x] Evaluate autonomy before file, command, network, provider, Git, PR, and
      external-system actions.
- [x] Reject attempts to elevate autonomy through prompts, skills, task metadata,
      or graph mutations.
- [x] Require explicit persisted approval for level changes.
- [x] Record effective level and policy source in every action audit.

### V6-302 — Separate maker and checker identities

- [x] Add explicit implementer and verifier assignments.
- [x] Prevent the same TaskRun/agent context from being the sole checker.
- [x] Give the checker fresh task contracts and evidence rather than hidden
      implementer reasoning.
- [x] Allow deterministic checks to reject work before model-based review.
- [x] Require the checker to report tests executed and `not_checked`.

### V6-303 — Define acceptance and human handoff

- [x] Separate task implementation, technical verification, `PR_READY`, human
      acceptance, merge, and deployment statuses.
- [x] Require human review for every merge.
- [x] Add clear handoff payloads for blocked, rejected, and ready work.
- [x] Prevent role spoofing through free-form payload fields.

**Targeted regression**

- [x] L0 and L1 cannot write.
- [x] L2 can write only in an approved worktree and cannot merge.
- [x] L3 can reach `PR_READY` but cannot merge.
- [x] Same-context self-verification is rejected.
- [x] Missing checker evidence prevents `PR_READY`.
- [x] Autonomy escalation without approval is rejected and audited.

**Phase 3 exit gate**

- [x] All autonomy levels pass positive and negative permission tests.
- [x] A maker cannot approve its own code-changing task.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 4 — Safety Invariants and Non-Bypassable Policy Gates

### Goal

Turn Loop safety guidance into SafetyKernel invariants that every execution path
must obey.

### V6-400 — Add Loop and Swarm policy contracts

- [x] Add allowed actions, denied actions, allowed commands, blocked commands,
      protected paths, network scope, provider scope, file-count limits,
      diff-growth limits, and approval patterns.
- [x] Add stricter defaults for `.env`, credentials, authentication, payments,
      infrastructure, workflows, and schema migrations.
- [x] Define policy composition between global, project, Loop, Run, and task
      scopes.
- [x] Resolve conflicts using the most restrictive applicable rule.

### V6-401 — Centralize enforcement

- [x] Route file, command, network, Git, PR, provider, and external connector
      actions through the SafetyKernel.
- [x] Prevent runners and extensions from invoking lower-level mutation APIs
      directly.
- [x] Validate policy both before action and before committing results.
- [x] Fail closed when policy or actor identity is missing.

### V6-402 — Add mechanical pre-PR gates

- [x] Recheck file count, protected paths, diff growth, secret scan, generated
      artifacts, approvals, verifier evidence, and merge policy.
- [x] Treat auto-merge as permanently disabled for V6.
- [x] Attach gate results as a versioned artifact.
- [x] Reject stale approvals after material diff changes.

### V6-403 — Add adversarial policy tests

- [x] Prompt-requested path escape.
- [x] Symlink and path-normalization escape.
- [x] Nested worktree escape.
- [x] Command alias/shell wrapping bypass.
- [x] Skill or runner bypass.
- [x] Stale approval reuse.
- [x] Secret and credential access.
- [x] Unauthorized PR approval or merge.

**Phase 4 regression**

- [x] `backend/tests/test_safety_kernel.py`.
- [x] `backend/tests/test_safety_validator.py`.
- [x] Action approval and audit regressions.
- [x] Scheduler and runner negative-path regressions.

**Phase 4 exit gate**

- [x] All mutations are proven to pass through the SafetyKernel.
- [x] Bypass fixtures fail closed.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 5 — Worktree Attempt Lifecycle and Path Intents

### Goal

Provide isolated, recoverable attempts and coordinate concurrent writes without
claiming automatic conflict resolution.

### V6-500 — Add an attempt manifest

- [x] Persist worktree path, branch, source commit, owner, task, attempt,
      expected paths, leases, timestamps, and lifecycle status.
- [x] Support active, verified, rejected, escalated, merged, stale, and cleaned
      states.
- [x] Reconcile manifests with actual Git/worktree state after restart.
- [x] Never infer success solely from a branch or directory existing.

### V6-501 — Add PathIntent and leases

- [x] Allow tasks to declare file, directory, and subsystem write intent.
- [x] Add owner, TTL, renewal, wait policy, and release reason.
- [x] Detect exact and hierarchical overlap.
- [x] Notify affected workers before overlapping writes.
- [x] Require escalation or serialized execution for protected overlaps.

### V6-502 — Add wait and deadlock handling

- [x] Track wait-for relationships.
- [x] Detect lease cycles and excessive wait.
- [x] Apply deterministic victim/escalation policy.
- [x] Respect Loop and Run budgets while waiting.
- [x] Release leases after cancellation, breaker open, or terminal failure.

### V6-503 — Add safe reconciliation and cleanup

- [x] Report orphan worktrees and manifests before deleting anything.
- [x] Verify target paths are under the configured workspace root.
- [x] Preserve uncommitted work from stale attempts.
- [x] Require explicit policy for automatic cleanup.
- [x] Keep cleanup auditable and recoverable where practical.

**Targeted regression**

- [x] Manifest round trip and restart reconciliation.
- [x] Exact, parent/child, and non-overlapping PathIntent cases.
- [x] TTL expiration and renewal race.
- [x] Deadlock detection and deterministic escalation.
- [x] Cancellation and breaker lease release.
- [x] Orphan cleanup report-only behavior.
- [x] Windows path case and separator behavior.

**Phase 5 exit gate**

- [x] Concurrent conflicting attempts cannot write silently.
- [x] Restart and cleanup preserve uncommitted work.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 6 — Capability-Aware RunnerPool and Resource Governance

### Goal

Replace simple runner acquisition with capability, health, resource, budget, and
outcome-aware dispatch.

### V6-600 — Define runner capabilities

- [x] Add lane, tools, platform, workspace type, model/provider access, network
      policy, concurrency, memory/CPU expectations, and supported task types.
- [x] Add task capability requirements and hard constraints.
- [x] Reject dispatch when no runner satisfies required capabilities.

### V6-601 — Add health and resource leases

- [x] Track ready, busy, degraded, unavailable, draining, and quarantined states.
- [x] Reserve concurrency, provider, workspace, and paid-call capacity before
      dispatch.
- [x] Release capacity on completion, cancellation, timeout, and crash.
- [x] Reconcile leaked leases after restart.

### V6-602 — Implement deterministic dispatch

- [x] Filter by hard capability and safety requirements.
- [x] Rank eligible runners by health, locality, cost, load, and verified
      outcomes.
- [x] Add stable tie-breaking.
- [x] Persist why the selected runner won and why others were rejected.
- [x] Keep provider routing attribution separate from runner selection.

### V6-603 — Add backpressure and fairness

- [x] Bound project, Loop, lane, provider, and global concurrency.
- [x] Prevent one Loop from starving others.
- [x] Add queue aging without bypassing priority or safety.
- [x] Include queued time in budget and observability.

**Targeted regression**

- [x] Capability match and no-compatible-runner behavior.
- [x] Stable selection and attribution.
- [x] Degraded/quarantined runner exclusion.
- [x] Lease release on crash and cancellation.
- [x] Global and per-Loop backpressure.
- [x] Fairness under competing queues.
- [x] Existing local worktree runner compatibility.

**Phase 6 exit gate**

- [x] Dispatch is deterministic, explainable, bounded, and restart-safe.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 7 — Typed Handoffs and Evidence-Carrying Dependencies

### Goal

Replace arbitrary handoff dictionaries as the main coordination contract with
versioned artifacts validated at task boundaries.

### V6-700 — Define typed handoff artifacts

- [x] Define schema version, producer, consumer, artifact type, summary,
      evidence, changed files, tests, validation results, open questions, risks,
      `not_checked`, and content hash.
- [x] Define artifact types for plan, research, patch, test result, critique,
      verification, failure, and escalation.
- [x] Keep extensibility through registered schemas rather than arbitrary
      unvalidated keys.

### V6-701 — Validate production and consumption

- [x] Validate artifacts before persistence.
- [x] Verify content hashes and producer ownership.
- [x] Validate consumer compatibility.
- [x] Enforce consume-once only where the artifact semantics require it.
- [x] Preserve immutable historical versions.

### V6-702 — Carry artifacts through dependency edges

- [x] Declare required input and output artifact types on Task edges.
- [x] Prevent a dependent task from becoming ready with missing or rejected
      evidence.
- [x] Allow multiple upstream artifacts with explicit aggregation rules.
- [x] Expose provenance from final evidence back to every producer.

### V6-703 — Add human-readable handoff rendering

- [x] Render compact summaries without losing machine-readable payloads.
- [x] Highlight missing checks, risks, and unresolved questions.
- [x] Redact secrets and untrusted large content.

**Targeted regression**

- [x] Schema validation and version compatibility.
- [x] Tampered hash and wrong-owner rejection.
- [x] Missing dependency artifact blocks readiness.
- [x] Multi-producer aggregation.
- [x] Audit and replay preserve artifact lineage.
- [x] Existing V5 handoff compatibility or explicit migration.

**Phase 7 exit gate**

- [x] Task readiness depends on validated evidence, not status alone.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 8 — Light Swarm

### Goal

Deliver the first bounded multi-agent strategy with a fixed small fan-out and no
recursive sub-swarms.

### V6-800 — Define Light Swarm policy

- [x] Allow two to four workers.
- [x] Permit only one decomposition level.
- [x] Require one task owner and one isolated attempt per code-changing node.
- [x] Require an independent checker.
- [x] Bound aggregate time, cost, tokens, files, and retries.
- [x] Disable worker-created sub-swarms.

### V6-801 — Add bounded decomposition

- [x] Convert an actionable task into a fixed DAG of research, implementation,
      test, critique, and verification nodes as applicable.
- [x] Validate acyclicity and required artifact contracts before execution.
- [x] Reject decomposition that exceeds policy or budget.
- [x] Keep a single-worker strategy available as baseline and fallback.

### V6-802 — Coordinate Light Swarm execution

- [x] Dispatch ready nodes through the capability-aware RunnerPool.
- [x] Use worktree manifests and PathIntents for code-changing nodes.
- [x] Transport only typed handoff artifacts across edges.
- [x] Stop downstream work when upstream evidence fails.
- [x] Open the circuit breaker on repeated non-progress.

### V6-803 — Aggregate and verify the result

- [x] Assemble candidate changes only after node-level checks pass.
- [x] Run deterministic integration checks in a dedicated verification context.
- [x] Require checker evidence before `PR_READY`.
- [x] Escalate conflicts that cannot be reconciled deterministically.

### V6-804 — Add Light Swarm controls and observability

- [x] Add strategy selection to CLI/API.
- [x] Show DAG, workers, leases, wait time, cost, attempts, and verifier result.
- [x] Allow pause and kill at Swarm and node scope.
- [x] Export a replayable execution summary.

**Targeted regression**

- [x] Maximum worker and depth limits.
- [x] Bounded decomposition and acyclicity.
- [x] Parallel non-overlapping work.
- [x] Overlapping path serialization/escalation.
- [x] Upstream failure propagation.
- [x] Checker rejection and repair cycle.
- [x] Pause, kill, restart, and lease recovery.
- [x] Single-worker fallback.

**Phase 8 exit gate**

- [x] Light Swarm completes a controlled multi-file fixture without collision,
      unbounded retries, or self-verification.
- [x] Complete the mandatory phase synchronization gate.


---

## Phase 9 — Server-Owned Dynamic Task DAG and Deep Swarm

### Goal

Add validated dynamic graph expansion for tasks that cannot be fully decomposed
before execution.

### V6-900 — Version the task graph

- [x] Make the server-owned graph the canonical execution structure.
- [x] Add graph version, mutation sequence, actor, reason, parent version, and
      content hash.
- [x] Preserve an append-only mutation journal.
- [x] Support deterministic replay from the initial graph and mutation journal.

### V6-901 — Define validated graph mutations

- [x] Add split task, append child, add dependency, add critique, add verifier,
      supersede node, and cancel subtree operations.
- [x] Validate ownership, acyclicity, depth, fan-out, budget, artifacts, safety,
      and resource availability.
- [x] Prevent agents from directly changing status or dependencies.
- [x] Reject stale mutations against an outdated graph version.

### V6-902 — Add atomic and composite nodes

- [x] Define composite completion from child evidence.
- [x] Add explicit critique and verification gates.
- [x] Allow conditional branches only through registered decision contracts.
- [x] Define failure propagation and partial-result behavior.

### V6-903 — Implement Deep Swarm policy

- [x] Make Deep Swarm opt-in and experimental.
- [x] Bound maximum depth, nodes, concurrent workers, mutations, paid calls,
      duration, and cost.
- [x] Require a justification for each dynamic expansion.
- [x] Prefer Light Swarm when the task fits fixed decomposition.
- [x] Stop expansion when marginal progress is absent.

### V6-904 — Add crash recovery and graph reconciliation

- [x] Restore graph version, ready queue, leases, attempts, and artifacts after
      restart.
- [x] Reconcile nodes that were running during interruption.
- [x] Prevent completed side effects from repeating.
- [x] Escalate irreconcilable graph/worker state.

**Targeted regression**

- [x] Mutation replay determinism.
- [x] Cycle, stale-version, ownership, depth, and budget rejection.
- [x] Composite completion and gate behavior.
- [x] Dynamic child creation and typed artifact flow.
- [x] Crash during mutation, dispatch, and verification.
- [x] Duplicate external action prevention.
- [x] Deep-to-Light or single-worker fallback.

**Phase 9 exit gate**

- [x] Dynamic expansion is bounded, auditable, replayable, and server-validated.
- [x] Deep Swarm remains disabled by default until Phase 11 evidence supports it.
- [ ] Complete the mandatory phase synchronization gate.

Phase status: `EVIDENCE_READY`. The technical acceptance criteria and local
regressions are complete. Final `PHASE_ACCEPTED` remains gated on the feature
branch pull request, successful remote checks, human review, and reviewed merge.


---

## Phase 10 — Provenance-Aware Operational Memory

### Goal

Improve memory for execution continuity and verified engineering outcomes before
considering a semantic graph or embeddings.

### V6-1000 — Extend memory provenance

- [ ] Record project, repository, source Run, task, attempt, artifact, verifier,
      timestamp, validity, confidence, and policy scope.
- [ ] Distinguish observed fact, decision, constraint, failure pattern, outcome,
      and human instruction.
- [ ] Link learned facts only to validated evidence.
- [ ] Prevent failed or rejected attempts from becoming authoritative memory.

### V6-1001 — Add memory relationships

- [ ] Add `relates_to`, `supersedes`, `contradicts`, `derived_from`, and
      `validated_by`.
- [ ] Preserve relationship provenance and timestamps.
- [ ] Prevent cycles where relationship semantics require a partial order.
- [ ] Render conflicting and superseded facts explicitly.

### V6-1002 — Add consolidation and staleness

- [ ] Detect exact duplicates, semantic candidates, contradictions, and expired
      facts.
- [ ] Require deterministic or human resolution before replacing authoritative
      memory.
- [ ] Add project-configurable retention and staleness policy.
- [ ] Run consolidation in a bounded background job.

### V6-1003 — Improve retrieval and evaluation

- [ ] Establish a versioned lexical/structured retrieval baseline.
- [ ] Add task, file, error fingerprint, provider, and outcome filters.
- [ ] Measure Recall@k, MRR, latency, zero-result rate, stale-hit rate, and
      contradictory-hit rate.
- [ ] Add embeddings only behind an optional interface and only if measured
      retrieval improves.
- [ ] Keep paid embedding services out of default tests.

### V6-1004 — Integrate memory safely with Loop and Swarm

- [ ] Inject only scoped, current, provenance-bearing facts.
- [ ] Give the checker access to evidence provenance, not hidden maker reasoning.
- [ ] Record which memories influenced a task.
- [ ] Allow humans to pin, correct, supersede, or invalidate memory.
- [ ] Prevent retrieved memory from changing policy or autonomy.

**Targeted regression**

- [ ] Provenance persistence and scope isolation.
- [ ] Supersession and contradiction behavior.
- [ ] Stale fact exclusion.
- [ ] Failed-attempt learning rejection.
- [ ] Retrieval benchmark reproducibility.
- [ ] Prompt-injected memory cannot elevate permissions.
- [ ] Existing V5 memory backup compatibility.

**Phase 10 exit gate**

- [ ] Operational memory is provenance-aware and evaluated.
- [ ] Semantic embeddings are enabled only if evidence justifies them.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase 11 — First Operational Loops and Comparative Evaluation

### Goal

Implement the three initial loops, test them in controlled repositories, and
measure whether Loop and Swarm improve outcomes over the V5/single-worker
baseline.

### V6-1100 — Build the evaluation corpus and baselines

- [ ] Create versioned fixture repositories and event streams.
- [ ] Include actionable and non-actionable issues, CI failures, review
      comments, merge conflicts, flaky tests, environment failures, and malicious
      inputs.
- [ ] Label expected classification, allowed action, required approval, and
      success evidence.
- [ ] Capture V5 or single-worker baselines using the same tasks, models,
      providers, budgets, machines, and acceptance tests.
- [ ] Hash fixtures, manifests, commands, and source commits.

### V6-1101 — Daily Project Triage Loop, L1

- [ ] Inspect issues, pull requests, CI state, blocked work, and stale items.
- [ ] Use cheap deterministic/API triage before any model call.
- [ ] Produce prioritized findings with evidence and recommended next action.
- [ ] Persist `acting_on` and item idempotency state.
- [ ] Make no repository or external mutation at L1.
- [ ] Add a post-run critique of false positives, missed items, and cost.

**Targeted regression**

- [ ] No-op run uses no worker.
- [ ] Duplicate events do not duplicate findings.
- [ ] Malicious issue text cannot change policy.
- [ ] L1 cannot write, comment, close, or modify external items.
- [ ] Restart preserves triage state.

### V6-1102 — CI Sweeper Loop, L2

- [ ] Monitor failed CI events.
- [ ] Classify flake, code regression, environment, configuration, dependency,
      and unknown failures.
- [ ] Act automatically only on allowlisted code-regression classes.
- [ ] Use a maximum of three repair attempts and the circuit breaker.
- [ ] Use maker/checker separation, worktrees, typed evidence, and draft PRs.
- [ ] Never weaken or delete a failing test to manufacture success.
- [ ] Require human merge.

**Targeted regression**

- [ ] Correct failure classification on labeled fixtures.
- [ ] Flake and environment failures do not trigger unsafe code edits.
- [ ] Same failure fingerprint opens the breaker.
- [ ] Fixed regression reruns the original failing test and adjacent regression.
- [ ] Draft PR contains complete evidence and no auto-merge.

### V6-1103 — PR Babysitter Loop, L2

- [ ] Monitor CI, review comments, requested changes, mergeability, and stale
      approvals.
- [ ] Deduplicate events and preserve thread/comment identity.
- [ ] Apply only allowlisted small fixes in an isolated worktree.
- [ ] Revalidate after upstream branch changes.
- [ ] Notify or escalate conflicts and policy-sensitive requests.
- [ ] Never approve or merge its own pull request.

**Targeted regression**

- [ ] Comment/event deduplication.
- [ ] Review request maps to the correct file and line.
- [ ] Upstream change invalidates stale evidence and approval.
- [ ] Conflict produces notification/escalation, not silent overwrite.
- [ ] No approval or merge permission is exercised.

### V6-1104 — Compare execution strategies

Run the same labeled tasks through:

- [ ] V5 or single-worker baseline.
- [ ] Loop with single-worker execution.
- [ ] Loop with Light Swarm.
- [ ] Loop with Deep Swarm where justified.
- [ ] Maker/checker with independent context.
- [ ] Operational memory enabled and disabled.

Measure:

- time to actionable finding;
- classification precision and recall;
- false-positive rate;
- `PR_READY` rate;
- human acceptance rate;
- regressions introduced;
- attempts and repeated failures;
- human interventions;
- token and monetary cost;
- queue and execution duration;
- file collisions and waits;
- restart/resume success;
- duplicate external actions;
- safety-policy violations.

### V6-1105 — Apply strict strategy gates

- [ ] Require zero auto-merges and zero unauthorized mutations.
- [ ] Require zero duplicate external actions in the controlled corpus.
- [ ] Require all safety, breaker, lease, and restart invariants to pass.
- [ ] Require Light Swarm to improve `PR_READY` rate, or preserve it while
      materially improving time/cost, before making it generally available.
- [ ] Keep Deep Swarm experimental unless it produces a measurable advantage over
      Light Swarm on tasks that require dynamic decomposition.
- [ ] Report statistical uncertainty and sample size.
- [ ] Mark results `ACCEPTED`, `PARTIAL`, or `REJECTED`; do not select the best
      anecdotal run.

### V6-1106 — Publish reproducible phase evidence

- [ ] Publish task corpus description, manifests, hashes, commands, environment,
      results, and limitations.
- [ ] Do not publish credentials, model transcripts containing secrets,
      disposable worktrees, or private repository content.
- [ ] Separate proof-run completion from performance-target achievement.
- [ ] Record the recommended default strategy for each loop.

**Phase 11 exit gate**

- [ ] Daily Project Triage passes as L1 report-only.
- [ ] CI Sweeper and PR Babysitter pass as L2 draft-PR workflows.
- [ ] Loop/Swarm benefit or lack of benefit is supported by comparative evidence.
- [ ] Deep Swarm remains experimental if its gate is not met.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase 12 — Final Documentation, Regression, Cleanup, and GitHub Sync

### Goal

Document only verified V6 behavior, run the final regression contract, remove
unnecessary local artifacts safely, and synchronize the reviewed release with
GitHub.

No new Loop or Swarm feature should be introduced in this phase.

### V6-1200 — Update README

- [ ] Explain Loop Control Plane and Swarm Execution Engine as separate layers.
- [ ] Document L0–L3 behavior and the permanent human-merge requirement.
- [ ] Add architecture and execution-flow diagrams.
- [ ] Document the three supported initial loops.
- [ ] Add safe quickstarts for report-only Loop and controlled Light Swarm.
- [ ] Document pause, kill, circuit breaker, budgets, worktrees, PathIntents,
      typed handoffs, and verifier gates.
- [ ] Publish measured Phase 11 results and limitations.
- [ ] Mark Deep Swarm and semantic embeddings experimental when their gates are
      not accepted.
- [ ] Remove obsolete V5-only or contradictory claims.

### V6-1201 — Update CHANGELOG

- [ ] Add a V6 release section grouped by Added, Changed, Fixed, Security,
      Evaluation, and Known Limitations.
- [ ] Document database/schema upgrade requirements.
- [ ] Document API/CLI compatibility changes.
- [ ] Record safety and autonomy changes prominently.
- [ ] Link phase evidence and comparative reports.
- [ ] Do not convert historical `PARTIAL` evidence into an accepted claim.

### V6-1202 — Run final regression

- [ ] Run the complete backend test suite.
- [ ] Run Ruff and mypy.
- [ ] Run the complete frontend unit-test suite.
- [ ] Run frontend type/build validation.
- [ ] Run clean package build/install and CLI smoke validation.
- [ ] Run database-upgrade compatibility tests from V5.
- [ ] Run all three operational Loop end-to-end suites.
- [ ] Run Light Swarm restart, collision, checker, and circuit-breaker suites.
- [ ] Run Deep Swarm gates if Deep Swarm is included in the release.
- [ ] Run safety/adversarial and secret-leak regressions.
- [ ] Re-run the accepted comparative benchmark contract.
- [ ] Record every command, exit code, failure, rerun, and final verdict.

**Acceptance**

- Final verdict is `ACCEPTED` only when all mandatory tests and release gates
  pass.
- A failed mandatory test cannot be waived by documentation.

### V6-1203 — Clean the repository safely

- [ ] Capture a final inventory before deleting or moving anything.
- [ ] Classify caches, logs, databases, artifacts, build output, temporary
      repositories, worktrees, coverage output, and credentials.
- [ ] Remove only paths proven unnecessary and inside the repository scope.
- [ ] Preserve user-authored or ambiguous files for review.
- [ ] Verify `.gitignore` prevents regenerated noise.
- [ ] Run secret, large-file, and generated-artifact scans.
- [ ] Verify the release can be built from a clean clone without ignored local
      dependencies.

### V6-1204 — Final review and synchronization

- [ ] Inspect the complete V5-to-V6 diff and release evidence.
- [ ] Run `git diff --check`.
- [ ] Confirm the working tree contains only final release changes.
- [ ] Fetch `origin` and resolve any divergence through a reviewed branch.
- [ ] Commit the final documentation, test evidence, and cleanup.
- [ ] Push the final release branch.
- [ ] Open the final pull request and require remote CI plus human review.
- [ ] Merge without auto-merge or force-push.
- [ ] Fetch and fast-forward local `main`.
- [ ] Verify local `HEAD` equals `origin/main`.
- [ ] Verify `git status --short` is empty.
- [ ] Create and push a version tag only after explicit human approval.
- [ ] Verify the GitHub release points to the accepted commit and evidence.

**Phase 12 exit gate**

- [ ] README and CHANGELOG describe verified V6 behavior.
- [ ] Final regression verdict is `ACCEPTED`.
- [ ] Repository cleanup is evidenced and did not discard user work.
- [ ] Local and online `main` are synchronized and clean.
- [ ] V6 is reproducible from its reviewed GitHub commit.

---

## 5. Phase Dependency Map

```text
Phase 0  V5 clean boundary
   |
Phase 1  Loop Coordinator and durable state
   |
Phase 2  Circuit breakers and kill controls
   |
Phase 3  Autonomy and maker/checker
   |
Phase 4  Non-bypassable safety gates
   |
Phase 5  Worktree lifecycle and PathIntents
   |
Phase 6  Capability-aware RunnerPool
   |
Phase 7  Typed handoffs and evidence edges
   |
Phase 8  Light Swarm
   |
Phase 9  Dynamic DAG and Deep Swarm
   |
Phase 10 Provenance-aware memory
   |
Phase 11 Three operational loops and comparative evaluation
   |
Phase 12 Documentation, final regression, cleanup, and GitHub sync
```

## 6. Recommended Branch Sequence

```text
release/v5-closeout
feat/v6-phase-01-loop-coordinator
feat/v6-phase-02-circuit-breakers
feat/v6-phase-03-autonomy-checker
feat/v6-phase-04-safety-gates
feat/v6-phase-05-worktree-intents
feat/v6-phase-06-runner-pool
feat/v6-phase-07-typed-handoffs
feat/v6-phase-08-light-swarm
feat/v6-phase-09-dynamic-dag
feat/v6-phase-10-memory
feat/v6-phase-11-operational-loops
release/v6-final
```

Each branch begins from the synchronized `origin/main` produced by the previous
phase. Do not keep all phases in one long-lived branch.

## 7. Explicit V6 Non-Goals

- Automatic merge or deployment.
- Unlimited recursive worker creation.
- A terminal emulator or custom rendering engine.
- Supporting providers solely to increase provider count.
- Self-modifying LocalForge with live binary reload.
- Claims of automatic conflict resolution.
- Free-form agent mutation of task status or DAG structure.
- File-based Loop state as the canonical source of truth.
- Semantic embeddings without retrieval evaluation.
- Using model self-judgment as the only acceptance gate.
- Weakening tests to increase `PR_READY` counts.
- Publishing private prompts, credentials, or disposable workspaces as evidence.
