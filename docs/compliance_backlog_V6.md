# LocalForge OS V6 — Integration and Compliance Closure Backlog

> Document version: 1.0
>
> Target release: V6.1
>
> Status: Historical/disputed; superseded by `docs/compliance_backlog_V6-1.md`
>
> Created: 2026-07-28
>
> Baseline commit: `d031f3e2f69c5ba8ac858344f2fc95807170cbc2`
>
> Continues: `MASTER_BACKLOG_V6.md`

## 1. Objective

Bring LocalForge V6 from an architectural alpha to the operational,
evidence-backed control plane originally intended by the V6 backlog.

The existing V6 implementation contains useful domain models, persistence,
APIs, CLIs, safety primitives, graph state machines, and tests. This backlog
does not replace them or add a new product direction. It closes the gaps between
those components and the real execution path.

The target operating flow is:

```text
Real trigger
  -> LoopCoordinator
  -> persistent triage and idempotency
  -> Scheduler
  -> capability-aware RunnerPool
  -> SafetyKernel and Autonomy gate
  -> Worktree and PathLease
  -> real worker execution
  -> TypedHandoff evidence
  -> independent Checker
  -> MechanicalPrePRGate
  -> draft pull request
  -> human review and merge
```

V6.1 must prove that this flow works. Models, endpoints, return objects, fixture
classifiers, and manually advanced state machines are not sufficient evidence
by themselves.

## 1.1 Current Remediation Pass and Release Candidate Evidence

The first V6.1 compliance remediation pass has been applied locally on
2026-07-28. It addresses the highest-impact implementation gaps in the runtime
spine and verifies them with local gates:

- Scheduler task starts now pass through a governed execution service and the
  persisted capability-aware runner pool.
- Loop coordinator actionable events now create persisted scheduler tasks
  instead of report-only state.
- File and command mutation paths use a shared ActionGateway that evaluates
  autonomy before safety.
- Runner dispatch capacity is reserved atomically and released after governed
  task completion.
- `PR_READY` transitions are centralized behind evidence metadata in
  `TaskService.mark_pr_ready`.
- Light Swarm blocks completion when required output evidence is missing.
- Deep Swarm forced execution requires registered decision-contract evidence.
- Runtime memory injection is scoped, authoritative, and audited.
- Operational loops consume provider-neutral connector state instead of only
  process-local fixtures.
- Strategy comparisons now aggregate observed task-level results and mark
  missing ledger values as unknown instead of treating them as zero.
- Repository-wide `ruff check backend` is clean and is now configured as a
  blocking CI step.

Local verification from this pass:

- `python -m pytest backend/tests -q`: 294 passed.
- `python -m mypy backend`: success for 209 source files.
- `python -m ruff check backend`: passed.
- `npm run build --prefix frontend`: passed.
- `git diff --check`: passed.

The remediation commit was pushed to `origin/main` and validated by GitHub
Actions:

- Accepted commit: `1fcb72f15cc5f8e3858be1599cd1d4032f582b3e`.
- Remote CI: `https://github.com/Masteradilio/local_forge_os/actions/runs/30414330405`.
- CI verdict: backend and frontend jobs passed.
- Immutable evidence: `docs/e2e/v6_1_compliance/`.

The V6.1 tag and GitHub Release are immutable historical publication records.
They are not accepted production-compliance evidence after the audit-of-audit
captured in `docs/compliance_backlog_V6-1.md`.

## 2. Audit Findings This Backlog Must Close

| ID | Finding | Required outcome |
| --- | --- | --- |
| CF-01 | Phase 11 strategy metrics are hard-coded | Metrics are calculated from observed executions |
| CF-02 | Published corpus hash represents empty content | Evidence uses the actual versioned corpus hash |
| CF-03 | Daily Triage uses process-local idempotency state | State survives restart in canonical storage |
| CF-04 | CI Sweeper simulates repairs and draft PR creation | It executes a bounded repair in a real test repository |
| CF-05 | PR Babysitter reports a worktree fix without performing one | It uses real comments, worktrees, validation, and draft PR updates |
| CF-06 | Light Swarm is a manually advanced state machine | It dispatches real workers through the governed execution path |
| CF-07 | Deep Swarm does not dispatch workers | Dynamic DAG nodes execute through the same governed worker path |
| CF-08 | Capability-aware RunnerPool is not used by Scheduler | One canonical pool owns real dispatch |
| CF-09 | Safety, autonomy, leases, handoffs, and checker are optional surfaces | They become mandatory runtime gates |
| CF-10 | LoopCoordinator has no real schedule/event runtime | Cron, interval, manual, and external event triggers execute durably |
| CF-11 | Loop kill does not cascade through scheduler and resources | Kill stops work and releases every owned resource |
| CF-12 | PathLease lacks renewal, wait, deadlock, and atomic conflict control | Concurrent write coordination is deterministic and restart-safe |
| CF-13 | Memory is not injected into the real execution path | Scoped authoritative memory is consumed and audited by workers |
| CF-14 | README quickstart contains invalid commands | Every quickstart command passes from a clean clone |
| CF-15 | Ruff is marked complete but omitted from final evidence and CI | Repository-wide Ruff becomes a blocking CI gate |
| CF-16 | Backlog, CHANGELOG, and phase evidence disagree | One generated evidence chain defines release truth |
| CF-17 | Several manifests use `HEAD` or invalid commit hashes | Every artifact references an immutable existing commit |
| CF-18 | Mandatory per-phase PR workflow was not followed consistently | Branch protection and machine-verifiable PR evidence enforce it |
| CF-19 | V6 is called an official release without a Git tag/release | Version tag and GitHub Release exist only after all gates pass |
| CF-20 | Tests validate declared return values more than real side effects | Integration tests inspect repositories, processes, artifacts, and remote state |

## 3. Compliance Release Contract

V6.1 is accepted only when:

- documentation labels the current state truthfully until every closure gate
  passes;
- no published benchmark value is a constant selected by the implementation;
- all evidence manifests reference real immutable Git commits;
- the same evidence generator produces manifests, summaries, and documentation
  tables;
- Loop triggers, idempotency, retry, pause, kill, and recovery survive restart;
- Scheduler uses the capability-aware RunnerPool;
- every code-changing node owns an isolated worktree and PathLease;
- all mutating actions pass SafetyKernel and Autonomy enforcement;
- all dependency edges requiring evidence carry valid TypedHandoff artifacts;
- implementer and checker identities are independent;
- `PR_READY` requires deterministic validation, checker approval, and the
  MechanicalPrePRGate;
- Light Swarm dispatches and completes real workers;
- Deep Swarm remains opt-in and is enabled only when real evidence justifies it;
- Daily Triage, CI Sweeper, and PR Babysitter operate against controlled real
  Git/GitHub-compatible fixtures, not only in-memory events;
- strategy comparisons execute the same tasks with the same models, budgets,
  environments, and acceptance tests;
- full backend, frontend, migration, security, clean-clone, and end-to-end
  regressions pass;
- Ruff and mypy are blocking CI checks;
- no automated actor can merge;
- every compliance phase is delivered through a reviewed pull request;
- local `main`, `origin/main`, release tag, release evidence, and GitHub Release
  point to the same accepted commit.

`PR_READY` is an engineering evidence state. It is not human acceptance,
permission to merge, or permission to deploy.

## 4. Execution Rules

- Complete phases in dependency order.
- Start every phase from the reviewed `origin/main` produced by the previous
  phase.
- Add the smallest failing test before changing runtime behavior.
- Run the targeted test first, then the nearest regression module.
- Run broad suites only at a phase exit gate or in Phase C12.
- Do not weaken, delete, skip, or rewrite a failing test merely to satisfy a
  gate.
- Do not replace a real side effect with a Boolean claiming the side effect
  occurred.
- Do not hand-author observed metrics, test counts, corpus hashes, commit hashes,
  or acceptance verdicts.
- Do not retain both old and new execution paths after parity is proven.
- Preserve compatibility adapters only when a test or documented migration
  requires them.
- Do not auto-merge, force-push, reset, clean, or discard user work.
- Record proof-run completion separately from performance-target achievement.

## 5. Required Evidence Layout

Store compact compliance evidence under:

```text
docs/e2e/v6_compliance/phase_CNN/
  manifest.json
  test_summary.json
  acceptance_report.md
```

Generated benchmark evidence belongs under:

```text
docs/e2e/v6_compliance/phase_C11/
  corpus_manifest.json
  run_manifest_<strategy>.json
  task_results.jsonl
  strategy_comparison.json
  benchmark_report.md
```

Each manifest must include:

- schema version;
- phase and task IDs;
- exact source commit;
- parent/base commit;
- repository URL;
- branch and pull request number;
- merge commit when accepted;
- GitHub Actions run URL and conclusion;
- environment fingerprint;
- exact commands and exit codes;
- test counts obtained from command output;
- hashes of inputs and committed evidence;
- provider, model, token, and cost attribution;
- known limitations;
- generated verdict and gate reasons.

The evidence generator must reject:

- `HEAD`, branch names, or unresolved refs in `source_commit`;
- a commit that does not exist;
- an input hash that cannot be reproduced;
- missing commands or exit codes;
- `ACCEPTED` with a failed mandatory command;
- `ACCEPTED` without a merged reviewed pull request;
- `ACCEPTED` when local and remote accepted commits differ.

## 6. Mandatory Phase Synchronization Gate

Every phase must finish with all of the following:

- [ ] Phase acceptance tests and evidence pass.
- [ ] `git diff --check` passes.
- [ ] Ruff passes for changed files.
- [ ] Mypy passes for changed backend modules.
- [ ] No secret, database, cache, worktree, transcript, or generated repository
      is staged.
- [ ] `origin` is fetched and ahead/behind/divergence is recorded.
- [ ] Work is committed on the phase branch.
- [ ] The branch is pushed to the online repository.
- [ ] A pull request is opened with evidence and limitations.
- [ ] Remote checks pass.
- [ ] A human reviews the pull request.
- [ ] The pull request is merged without force-push or auto-merge.
- [ ] Phase evidence is finalized with PR number, merge commit, and CI run URL.
- [ ] Local `main` is fast-forwarded to the reviewed `origin/main`.
- [ ] Local `HEAD` equals `origin/main`.
- [ ] The working tree is clean.

Branch protection must reject direct pushes to `main` after Phase C0.

---

## Phase C0 — Truth Reset and Immutable Baseline

### Goal

Stop publishing unsupported release claims, preserve the current V6 state, and
establish machine-verifiable evidence rules before changing runtime behavior.

### V6C-000 — Capture the audit baseline

- [ ] Record commit `d031f3e2f69c5ba8ac858344f2fc95807170cbc2`,
      remote commit, working-tree state, current CI run, open PRs, remote tags,
      and release state.
- [ ] Hash README, CHANGELOG, V6 backlog, phase manifests, test summaries, and
      strategy comparison artifacts.
- [ ] Record the current targeted Ruff failure count separately from the
      Phase 9 historical global count.
- [ ] Store the audit findings CF-01 through CF-20 in the Phase C0 report.

### V6C-001 — Correct current product status

- [ ] Label the current V6 state `architectural alpha` until compliance closure.
- [ ] Remove or qualify “production ready”, “official release”, “empirical
      superiority”, and equivalent unsupported claims.
- [ ] Mark operational loops as fixture-driven simulators until Phase C10.
- [ ] Mark Light and Deep Swarm as orchestration state machines until real worker
      execution passes.
- [ ] Preserve the historical claims in Git history rather than presenting them
      as current facts.

### V6C-002 — Reconcile backlog and changelog state

- [ ] Resolve the unchecked Phase 9 synchronization gate using actual PR #13 and
      merge commit `9ba6c650689c98b67993f98d5c9d9969a79fa346`.
- [ ] Replace stale `EVIDENCE_READY` text only when its remote evidence is
      verified.
- [ ] Correct Phase 0 and other manifests whose verdicts do not match their
      final lifecycle.
- [ ] Record which original V6 phases were direct pushes and therefore did not
      satisfy the per-phase PR contract.
- [ ] Do not retroactively fabricate PR numbers or reviews.

### V6C-003 — Remove invalid evidence identifiers

- [ ] Replace `HEAD` with the actual commit that produced each artifact.
- [ ] Replace invalid full hashes with existing Git object IDs.
- [ ] Verify phase source commits contain the claimed code.
- [ ] Correct the empty-content corpus hash.
- [ ] Invalidate any derived report that used an incorrect source or corpus
      hash.

### V6C-004 — Implement the evidence validator

- [ ] Add a versioned JSON schema for manifests and test summaries.
- [ ] Add commit existence and ancestry validation.
- [ ] Add input/output hash validation.
- [ ] Add command/exit-code and mandatory-gate validation.
- [ ] Add PR, merge commit, and CI run validation.
- [ ] Add deterministic verdict generation.
- [ ] Prevent manual `ACCEPTED` overrides.

**Targeted regression**

- [ ] Reject `source_commit: HEAD`.
- [ ] Reject nonexistent commits.
- [ ] Reject empty or mismatched corpus hashes.
- [ ] Reject `ACCEPTED` with missing Ruff.
- [ ] Reject `ACCEPTED` without a reviewed merged PR.
- [ ] Accept a complete immutable fixture manifest.

**Phase C0 exit gate**

- [ ] Public status is truthful.
- [ ] Existing evidence is classified as valid, stale, invalid, or historical.
- [ ] The evidence validator passes.
- [ ] Branch protection for `main` is enabled.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C1 — Packaging, Quickstart, and Release Semantics

### Goal

Make the documented installation and first-run path work literally from a clean
clone and define an honest version/release lifecycle.

### V6C-100 — Repair installation instructions

- [ ] Replace `pip install -e backend` with the canonical root package install.
- [ ] Document runtime-only and development installs separately.
- [ ] Document Windows and POSIX virtual-environment activation accurately.
- [ ] Verify Python and Node version ranges against package metadata and CI.
- [ ] Remove commands that depend on undeclared global packages.

### V6C-101 — Repair database bootstrap instructions

- [ ] Either implement a supported `bootstrap-db` command or document the real
      existing initialization command.
- [ ] Make database creation and schema v1-to-current upgrade explicit.
- [ ] Provide a non-destructive status command that reports schema version.
- [ ] Fail early with actionable errors when the database cannot be upgraded.

### V6C-102 — Add executable quickstart verification

- [ ] Create a clean temporary clone in CI.
- [ ] Install with the exact README command.
- [ ] initialize the database;
- [ ] run CLI version and doctor commands;
- [ ] start the backend and verify its health endpoint;
- [ ] build and start the frontend;
- [ ] execute one report-only Loop fixture;
- [ ] shut down and clean temporary processes safely.

### V6C-103 — Define version and release states

- [ ] Define `alpha`, `beta`, release candidate, and stable criteria.
- [ ] Keep V6.1 pre-release until all compliance gates pass.
- [ ] Make package version, CHANGELOG version, evidence version, Git tag, and
      GitHub Release agree.
- [ ] Prevent the release workflow from publishing an untagged stable release.

**Targeted regression**

- [ ] Clean-clone installation on Windows and Linux.
- [ ] Database bootstrap and upgrade from a V5 fixture.
- [ ] README command smoke test.
- [ ] Package/CLI version consistency.

**Phase C1 exit gate**

- [ ] A new user can execute the documented quickstart unchanged.
- [ ] Release terminology is machine-verifiable.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C2 — One Canonical Execution Spine

### Goal

Compose existing V6 services into one governed runtime and eliminate parallel
execution paths that bypass V6 controls.

### V6C-200 — Define the execution contract

- [ ] Add one `GovernedExecutionRequest` containing project, Loop, Run, Task,
      attempt, autonomy, capability, workspace, budget, policy, and required
      evidence.
- [ ] Add one `GovernedExecutionResult` containing status, artifacts, tests,
      costs, resource releases, checker verdict, and next action.
- [ ] Define legal stage transitions and terminal states.
- [ ] Define idempotency keys for task attempts and external side effects.

### V6C-201 — Build the governed execution orchestrator

- [ ] Compose SafetyKernel, AutonomyService, RunnerPoolService, WorktreeService,
      PathLeaseService, runner execution, TypedHandoffService,
      MakerCheckerService, MechanicalPrePRGate, AuditService, and cost ledger.
- [ ] Execute stages in a fixed server-owned order.
- [ ] Persist the stage before and after every side effect.
- [ ] Resume from the last committed stage after restart.
- [ ] Fail closed when a required service or actor identity is unavailable.

### V6C-202 — Route Scheduler through the governed orchestrator

- [ ] Replace the round-robin `TaskRunnerPool` path with the
      capability-aware RunnerPool dispatch.
- [ ] Keep a temporary compatibility adapter only while parity tests run.
- [ ] Remove the old pool once all scheduler paths use the canonical service.
- [ ] Preserve local worktree runner behavior through the new runner contract.
- [ ] Record runner selection and rejection reasons.

### V6C-203 — Route every task start through the same path

- [ ] Scheduler tasks.
- [ ] recovery/healing attempts;
- [ ] Loop-created tasks;
- [ ] Light Swarm nodes;
- [ ] Deep Swarm nodes;
- [ ] CLI manual runs;
- [ ] API-triggered runs.

### V6C-204 — Add cross-component audit correlation

- [ ] Correlate Loop Run, scheduler Run, Task, TaskRun, Swarm Run, graph node,
      worktree, lease, runner, handoff, checker, pre-PR gate, and pull request.
- [ ] Expose one replay timeline.
- [ ] Redact secrets and untrusted external payloads.

**Targeted regression**

- [ ] No scheduler task can bypass the governed orchestrator.
- [ ] Compatibility and capability-aware paths produce equivalent successful
      local execution before old-path removal.
- [ ] Missing safety/autonomy/checker services fail closed.
- [ ] Restart resumes without repeating a completed side effect.
- [ ] Audit replay reconstructs the full execution.

**Phase C2 exit gate**

- [ ] There is one production task-execution path.
- [ ] The old round-robin pool is removed or unreachable in production.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C3 — Real Loop Triggering, Persistence, and Lifecycle

### Goal

Turn Loop definitions into durable recurring operations rather than manually
triggered records.

### V6C-300 — Implement trigger adapters

- [ ] Manual trigger adapter.
- [ ] Fixed-interval trigger adapter.
- [ ] Cron trigger adapter with timezone handling.
- [ ] External event/webhook trigger adapter.
- [ ] Startup reconciliation for missed or pending triggers.
- [ ] Deterministic next-eligible-run calculation.

### V6C-301 — Persist triage and idempotency

- [ ] Replace process-local `acting_on` dictionaries and sets with canonical
      LoopItem and idempotency records.
- [ ] Persist detector version, input hash, classification, recommendation, and
      triage evidence.
- [ ] Enforce uniqueness atomically in storage.
- [ ] Prevent duplicate work after restart, retry, or repeated webhook delivery.

### V6C-302 — Create executable work from actionable items

- [ ] Convert each actionable LoopItem into a versioned task contract.
- [ ] Persist Tasks and dependency artifacts.
- [ ] Create the scheduler Run in a non-running pre-dispatch state.
- [ ] Signal the scheduler only after the transaction commits.
- [ ] Link LoopItem to created Run, Task, and eventual pull request.

### V6C-303 — Replace default fake triage

- [ ] Remove “manual trigger without payload is actionable” as production
      behavior.
- [ ] Require a registered detector or an explicit manual task contract.
- [ ] Return safe `NO_OP` when no detector evidence exists.
- [ ] Record detector errors separately from no-op outcomes.

### V6C-304 — Implement lifecycle cascade

- [ ] Pause prevents new dispatch while preserving state.
- [ ] Resume re-evaluates budgets, leases, and stale evidence.
- [ ] Kill cancels scheduler work and active workers.
- [ ] Kill releases runner and path leases.
- [ ] Kill preserves worktree evidence for human inspection.
- [ ] Restart reconciles Loop, scheduler, worker, and resource state.

**Targeted regression**

- [ ] Interval and cron timing with timezone and missed-run cases.
- [ ] Duplicate webhook delivery.
- [ ] Database restart between trigger, triage, Run creation, and scheduler wake.
- [ ] Atomic item/task creation.
- [ ] Pause/resume with queued and active tasks.
- [ ] Kill cascade and resource release.
- [ ] No detector produces `NO_OP`, not invented work.

**Phase C3 exit gate**

- [ ] A scheduled report-only Loop executes across process restart without
      duplicate items.
- [ ] Kill stops real downstream execution.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C4 — Non-Bypassable Safety and Autonomy Enforcement

### Goal

Make policy enforcement part of the execution path rather than an optional API
or CLI check.

### V6C-400 — Add one action gateway

- [ ] Route file writes, commands, network, provider calls, Git operations, pull
      request operations, and external connectors through a common action
      gateway.
- [ ] Require project, actor, autonomy, policy, run, task, and attempt identity.
- [ ] Evaluate SafetyKernel and AutonomyService before execution.
- [ ] Re-evaluate policy before persisting or publishing results.
- [ ] Prevent direct use of lower-level mutating adapters outside the gateway.

### V6C-401 — Enforce autonomy levels end to end

- [ ] L0 cannot execute.
- [ ] L1 cannot mutate repositories or external systems.
- [ ] L2 can mutate only an approved isolated worktree and create draft PRs.
- [ ] L3 can operate unattended only up to `PR_READY`.
- [ ] No level can merge.
- [ ] Level changes require persisted human approval and invalidate stale
      execution grants.

### V6C-402 — Make pre-PR validation mandatory

- [ ] Invoke MechanicalPrePRGate automatically after checker approval.
- [ ] Check protected paths, file count, diff growth, secrets, generated files,
      test evidence, checker identity, stale approvals, and merge policy.
- [ ] Bind the gate result to the exact diff hash.
- [ ] Invalidate the gate after any material diff change.
- [ ] Prevent draft PR creation or `PR_READY` on gate failure.

### V6C-403 — Close bypass paths

- [ ] Direct runner mutation.
- [ ] skill/tool invocation;
- [ ] nested shell wrappers;
- [ ] symlink and path traversal;
- [ ] direct Git library invocation;
- [ ] direct connector invocation;
- [ ] graph mutation requesting higher autonomy;
- [ ] memory content attempting policy elevation.

**Targeted regression**

- [ ] Every known mutation entry point reaches the action gateway.
- [ ] L1 mutation attempts fail.
- [ ] L2 main-branch writes fail.
- [ ] L3 merge attempts fail.
- [ ] Stale gate evidence fails.
- [ ] Prompt, skill, runner, and graph bypass attempts fail closed.

**Phase C4 exit gate**

- [ ] Static and runtime call-path audits find no ungoverned mutation path.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C5 — Atomic Resource, Worktree, and Path Coordination

### Goal

Make concurrent execution safe under real scheduler and Swarm load.

### V6C-500 — Harden RunnerPool leases

- [ ] Reserve capacity atomically.
- [ ] Prevent concurrent over-allocation.
- [ ] Persist lease owner, task, attempt, expiry, renewal, and release reason.
- [ ] Reconcile leases using actual active TaskRuns rather than resetting all
      counts.
- [ ] Add project, Loop, lane, provider, and global backpressure.
- [ ] Add fairness and queue aging without bypassing priority.

### V6C-501 — Complete worktree attempt lifecycle

- [ ] Create real worktrees through the governed orchestrator.
- [ ] Bind worktree, branch, source commit, TaskRun, runner, and attempt.
- [ ] Persist state transitions before destructive cleanup.
- [ ] Reconcile Git state after restart.
- [ ] Preserve uncommitted work on stale or crashed attempts.
- [ ] Verify cleanup targets remain inside the workspace root.

### V6C-502 — Complete PathLease behavior

- [ ] Add lease renewal.
- [ ] Add bounded wait with cancellation.
- [ ] Persist wait-for relationships.
- [ ] Detect deadlock cycles.
- [ ] Apply deterministic victim or escalation policy.
- [ ] Notify overlapping workers.
- [ ] Release leases on completion, cancellation, breaker, timeout, and crash.

### V6C-503 — Close lease races

- [ ] Make conflict check and acquisition atomic.
- [ ] Add database constraints or serialized acquisition per project.
- [ ] Test simultaneous parent/child path requests.
- [ ] Normalize Windows case, separators, symlinks, and real paths.
- [ ] Prevent two successful owners for overlapping active paths.

**Targeted regression**

- [ ] Concurrent runner dispatch never exceeds capacity.
- [ ] Crash recovery preserves valid leases and releases leaked leases only.
- [ ] Parent/child PathIntent race.
- [ ] TTL renewal race.
- [ ] Deadlock cycle and deterministic resolution.
- [ ] Pause/kill releases resources.
- [ ] Orphan worktree reconciliation is report-only before cleanup.

**Phase C5 exit gate**

- [ ] A concurrent multi-task fixture completes without silent collision or
      leaked resources.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C6 — Typed Evidence, Independent Checker, and PR_READY Integrity

### Goal

Make evidence-carrying dependencies and independent verification mandatory for
task completion.

### V6C-600 — Bind TypedHandoff artifacts to graph edges

- [ ] Declare required artifact type and schema version on dependency edges.
- [ ] Persist producer, consumer, attempt, content hash, and validation status.
- [ ] Prevent dependent readiness when evidence is missing, invalid, rejected,
      or stale.
- [ ] Update node artifact ownership when a node completes.
- [ ] Preserve immutable artifact versions.

### V6C-601 — Enforce producer and consumer contracts

- [ ] Verify producer ownership.
- [ ] Verify consumer compatibility.
- [ ] Verify content hashes and referenced file/test artifacts.
- [ ] Define consume-once only for artifact types that require it.
- [ ] Aggregate multiple upstream artifacts deterministically.

### V6C-602 — Enforce independent checker execution

- [ ] Dispatch checker as a real separate TaskRun.
- [ ] Require a different agent/runner context from the maker.
- [ ] Provide task contract, diff, deterministic evidence, risks, and
      `not_checked`.
- [ ] Do not provide hidden maker reasoning.
- [ ] Persist accept/reject/repair verdict and reasons.

### V6C-603 — Centralize PR_READY transition

- [ ] Remove direct `PR_READY` assignments from Light Swarm, Deep Swarm,
      pipeline, API, and CLI paths.
- [ ] Add one server-owned transition function.
- [ ] Require completed deterministic checks.
- [ ] Require valid TypedHandoff lineage.
- [ ] Require independent checker acceptance.
- [ ] Require current MechanicalPrePRGate acceptance.
- [ ] Require no open breaker, lease conflict, or unresolved risk gate.

**Targeted regression**

- [ ] Manually completing all nodes without artifacts does not produce
      `PR_READY`.
- [ ] Self-checker and role-spoofing attempts fail.
- [ ] Tampered and stale artifacts fail.
- [ ] Diff change invalidates checker/pre-PR evidence.
- [ ] Valid maker/checker flow reaches `PR_READY`.

**Phase C6 exit gate**

- [ ] `PR_READY` can be reached through exactly one validated transition.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C7 — Real Light Swarm Execution

### Goal

Turn Light Swarm from a persisted DAG controller into bounded real multi-worker
execution.

### V6C-700 — Dispatch ready nodes

- [ ] Ask the capability-aware RunnerPool for each ready node.
- [ ] Reserve runner, budget, worktree, and PathIntent before starting.
- [ ] Start the node through the governed orchestrator.
- [ ] Persist worker identity and start evidence.
- [ ] Apply backpressure when resources are unavailable.

### V6C-701 — Execute node types

- [ ] Research nodes produce validated research artifacts.
- [ ] Implement nodes create real worktree changes.
- [ ] Test nodes execute the declared targeted tests.
- [ ] Critique nodes inspect artifacts and risks.
- [ ] Verify nodes run in an independent context.
- [ ] Unsupported node types fail before dispatch.

### V6C-702 — Replace manual completion

- [ ] Accept completion only from the owning active TaskRun.
- [ ] Validate required output artifacts before state transition.
- [ ] Derive cost, tokens, duration, and tests from observed execution.
- [ ] Release resources on terminal state.
- [ ] Keep administrative override explicit, human-approved, and non-accepting.

### V6C-703 — Integrate repair and circuit breakers

- [ ] Fingerprint failures from real runner/test output.
- [ ] Retry only classified recoverable failures.
- [ ] Detect repeated patch/test stagnation.
- [ ] Add critique or repair nodes within Light Swarm bounds.
- [ ] Escalate when retry, cost, time, or no-progress limits are reached.

### V6C-704 — Complete pause, kill, and restart

- [ ] Pause stops new dispatch.
- [ ] Kill cancels active workers.
- [ ] Restart reconciles running nodes, worktrees, leases, and artifacts.
- [ ] Completed side effects are not repeated.
- [ ] Interrupted nodes resume or escalate according to policy.

**Targeted regression**

- [ ] Two non-overlapping implement nodes run concurrently.
- [ ] Overlapping nodes serialize or escalate.
- [ ] Runner unavailability applies backpressure.
- [ ] Real test failure blocks downstream verify.
- [ ] Checker rejection produces bounded repair.
- [ ] Pause, kill, crash, and restart release/recover resources.
- [ ] No manual status call can manufacture `PR_READY`.

**Phase C7 exit gate**

- [ ] Light Swarm completes a real controlled repository task and creates a
      validated draft PR artifact.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C8 — Governed Deep Swarm Execution

### Goal

Connect the existing versioned dynamic task graph to real bounded workers while
keeping Deep Swarm experimental until measured evidence supports it.

### V6C-800 — Connect dynamic ready nodes to the execution spine

- [ ] Dispatch graph-selected nodes through the governed orchestrator.
- [ ] Use the same RunnerPool, Safety, worktree, lease, handoff, and checker
      contracts as Light Swarm.
- [ ] Prevent API clients from claiming completion without owning execution.
- [ ] Bind mutation versions to active worker state.

### V6C-801 — Govern dynamic expansion

- [ ] Require evidence and reason for every expansion.
- [ ] Apply node, depth, fan-out, mutation, worker, cost, token, and duration
      bounds.
- [ ] Reject stale graph-version mutations.
- [ ] Prevent mutations from changing server-owned status, policy, or autonomy.
- [ ] Stop expansion on marginal no-progress.

### V6C-802 — Reconcile graph and execution after restart

- [ ] Replay the mutation journal.
- [ ] Validate latest snapshot against replay.
- [ ] Reconcile graph nodes with TaskRuns, worktrees, leases, and artifacts.
- [ ] Recover the ready queue without duplicating external actions.
- [ ] Escalate irreconcilable state.

### V6C-803 — Preserve fallback discipline

- [ ] Use Light Swarm when the task fits bounded static decomposition.
- [ ] Use single-worker execution when multi-worker overhead is unjustified.
- [ ] Keep Deep Swarm disabled by default.
- [ ] Require Phase C11 evidence before recommending it.

**Targeted regression**

- [ ] Dynamic child executes through a real runner.
- [ ] Concurrent stale mutation rejection.
- [ ] Crash during mutation and worker dispatch.
- [ ] Typed artifact flow across dynamically created edges.
- [ ] Duplicate side-effect prevention after replay.
- [ ] Deep-to-Light and single-worker fallback.

**Phase C8 exit gate**

- [ ] Deep Swarm can execute a controlled dynamic-decomposition task without
      bypassing V6 compliance gates.
- [ ] It remains experimental pending Phase C11.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C9 — Operational Memory in the Real Runtime

### Goal

Use provenance-aware memory in actual Loop/Swarm execution without allowing
memory to influence permissions.

### V6C-900 — Inject scoped memory into workers

- [ ] Retrieve only authoritative, current, project-scoped facts.
- [ ] Filter by repository, task, files, failure fingerprint, and policy scope.
- [ ] Include provenance and validity with every injected fact.
- [ ] Record exactly which facts influenced the task.
- [ ] Keep memory text read-only and outside policy/system instruction channels.

### V6C-901 — Learn from validated outcomes

- [ ] Learn only after deterministic evidence and checker acceptance.
- [ ] Link learned facts to Run, TaskRun, artifacts, tests, verifier, and commit.
- [ ] Reject facts from failed, killed, partial, or rejected attempts as
      authoritative.
- [ ] Mark superseded or contradicted facts explicitly.

### V6C-902 — Run consolidation durably

- [ ] Schedule bounded consolidation as a real Loop/background job.
- [ ] Persist checkpoint and resume state.
- [ ] Enforce staleness and retention policies.
- [ ] Require human or deterministic evidence before replacing authoritative
      facts.

### V6C-903 — Evaluate memory retrieval

- [ ] Build a task-grounded retrieval corpus from verified fixtures.
- [ ] Measure Recall@k, MRR, latency, zero-result, stale-hit, and
      contradictory-hit rates.
- [ ] Compare memory disabled, structured retrieval, and optional embeddings.
- [ ] Keep embeddings optional unless they improve measured outcomes.

**Targeted regression**

- [ ] Execution receives only scoped authoritative facts.
- [ ] Failed attempts do not become authoritative memory.
- [ ] Prompt-injected memory cannot elevate policy.
- [ ] Supersession and contradiction survive restart.
- [ ] Retrieval metrics reproduce from the same corpus hash.

**Phase C9 exit gate**

- [ ] At least one real worker uses and audits operational memory.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C10 — Real Daily Triage, CI Sweeper, and PR Babysitter

### Goal

Replace fixture-only simulators with real operational loops tested against
controlled Git and GitHub-compatible repositories.

### V6C-1000 — Add connector boundaries

- [ ] Define provider-neutral interfaces for issues, pull requests, reviews,
      checks, workflow runs, comments, branches, and draft PR creation.
- [ ] Implement a deterministic local/fake connector for tests.
- [ ] Implement a GitHub adapter with least-privilege authentication.
- [ ] Add event pagination, rate-limit, retry, and idempotency handling.
- [ ] Treat all external text as untrusted data.

### V6C-1001 — Rebuild Daily Project Triage as L1

- [ ] Fetch real issue, PR, review, and CI state through the connector.
- [ ] Run cheap deterministic filtering before model calls.
- [ ] Persist findings, detector evidence, and `acting_on` state.
- [ ] Produce report-only output with no external mutation.
- [ ] Measure false positives and missed items against labeled outcomes.
- [ ] Resume without duplicating findings.

### V6C-1002 — Rebuild CI Sweeper as L2

- [ ] Fetch real failed-check metadata and bounded relevant logs.
- [ ] Classify code regression, flake, environment, configuration, dependency,
      and unknown failures.
- [ ] Auto-act only on allowlisted code regressions.
- [ ] Create a real task, worktree, PathIntent, and governed worker execution.
- [ ] Rerun the original failing test and nearest regression.
- [ ] Use an independent checker and pre-PR gate.
- [ ] Create a real draft PR through the connector.
- [ ] Persist the PR URL and external idempotency key.
- [ ] Open the circuit breaker after bounded repeated failure.
- [ ] Never weaken or remove a failing test to claim success.

### V6C-1003 — Rebuild PR Babysitter as L2

- [ ] Fetch real review threads, comments, requested changes, CI, and mergeability.
- [ ] Persist comment/thread identity and deduplicate deliveries.
- [ ] Map comments to the correct commit, file, side, and line.
- [ ] Invalidate evidence when upstream or reviewed diff changes.
- [ ] Execute allowlisted small fixes through the governed worker path.
- [ ] Re-run targeted checks and independent verification.
- [ ] Update the draft PR without approving or merging.
- [ ] Escalate conflicts, ambiguous comments, and protected-path changes.

### V6C-1004 — Add controlled remote end-to-end fixtures

- [ ] Create a dedicated disposable repository or local GitHub-compatible test
      harness.
- [ ] Seed issues, PRs, comments, CI states, failures, and conflicts.
- [ ] Verify actual branches, commits, worktrees, artifacts, and draft PR state.
- [ ] Clean fixtures without touching production repositories.
- [ ] Keep credentials outside evidence and logs.

**Targeted regression**

- [ ] Duplicate webhook delivery.
- [ ] Pagination and rate-limit handling.
- [ ] Malicious issue/review text.
- [ ] Real code-regression repair.
- [ ] Flake/environment/config/dependency no-edit behavior.
- [ ] Draft PR creation and human-merge requirement.
- [ ] Upstream change invalidates stale evidence.
- [ ] Merge conflict escalation.
- [ ] Restart during each loop.

**Phase C10 exit gate**

- [ ] All three loops operate on real controlled repository state.
- [ ] No service claims a worktree, test, or PR side effect without evidence.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C11 — Real Comparative Evaluation

### Goal

Replace the hard-coded strategy matrix with observed, reproducible executions
and determine whether Loop and Swarm actually improve outcomes.

### V6C-1100 — Build the evaluation corpus

- [ ] Include enough tasks to represent single-file fixes, multi-file changes,
      independent parallel work, dependent work, ambiguous failures, conflicts,
      and dynamic decomposition.
- [ ] Label expected classification, allowed action, expected files, tests,
      required evidence, and acceptance outcome.
- [ ] Keep holdout tasks separate from development fixtures.
- [ ] Version and hash every repository snapshot, event stream, and task
      contract.
- [ ] Reject empty or mismatched corpus hashes.

### V6C-1101 — Implement observed metrics collection

- [ ] Remove hard-coded strategy outcomes from production code.
- [ ] Derive classification metrics from predictions and labels.
- [ ] Derive `PR_READY` rate from persisted task outcomes.
- [ ] Derive human acceptance from recorded review decisions.
- [ ] Derive duration from monotonic timestamps.
- [ ] Derive tokens and costs from provider ledger entries.
- [ ] Derive collisions, retries, interventions, duplicate actions, restarts,
      and safety violations from audit events.
- [ ] Use `unknown`, not zero, when a metric is unavailable.

### V6C-1102 — Run controlled strategy comparisons

Execute the same corpus with:

- [ ] V5/single-worker baseline.
- [ ] Loop plus single worker.
- [ ] Loop plus Light Swarm.
- [ ] Loop plus Deep Swarm where task structure justifies it.
- [ ] maker/checker disabled only as a controlled non-release comparison;
- [ ] operational memory enabled and disabled.

Keep constant:

- task corpus and source commits;
- model/provider configuration;
- budget and timeout;
- machine/environment;
- acceptance tests;
- human review rubric.

### V6C-1103 — Add statistical and evidence discipline

- [ ] Run enough repetitions to report sample size and uncertainty.
- [ ] Report median and distribution, not only best run.
- [ ] Record failures and timeouts.
- [ ] Separate proof success from performance improvement.
- [ ] Do not exclude unfavorable runs without a documented invalidation rule.
- [ ] Preserve raw task-level results in JSONL.

### V6C-1104 — Apply strict strategy gates

- [ ] Zero auto-merges.
- [ ] Zero unauthorized mutations.
- [ ] Zero duplicate external actions.
- [ ] All mandatory safety and restart invariants pass.
- [ ] Light Swarm becomes recommended only if it improves accepted outcomes or
      preserves quality while materially reducing time/cost.
- [ ] Deep Swarm becomes recommended only when it outperforms Light Swarm on
      tasks requiring dynamic decomposition.
- [ ] Otherwise retain `PARTIAL`, `REJECTED`, or experimental status.

### V6C-1105 — Generate comparison artifacts

- [ ] Generate the strategy matrix directly from task-level results.
- [ ] Generate README/CHANGELOG tables from the same artifact.
- [ ] Include source commit, corpus hash, environment, model, budget, and sample
      size.
- [ ] Verify every aggregate can be recomputed.

**Targeted regression**

- [ ] Metric calculations from known labeled fixtures.
- [ ] Empty corpus rejection.
- [ ] Mismatched hash rejection.
- [ ] Missing ledger value produces `unknown`.
- [ ] Aggregate recomputation equals published results.
- [ ] Changing one task result changes the relevant aggregate.
- [ ] No constant strategy result remains in runtime code.

**Phase C11 exit gate**

- [ ] All published performance claims come from observed runs.
- [ ] Strategy recommendations match strict gate outcomes.
- [ ] Complete the mandatory phase synchronization gate.

---

## Phase C12 — Quality Gates, Documentation, and Stable Release

### Goal

Close repository-wide quality debt, prove clean-clone reproducibility, align all
documentation with verified behavior, and publish the first compliant V6
release.

No new product feature may be added in this phase.

### V6C-1200 — Eliminate Ruff debt

- [ ] Fix repository-wide Ruff findings without behavior-changing bulk rewrites.
- [ ] Remove unused imports and variables.
- [ ] Normalize import ordering.
- [ ] Resolve line-length issues surgically.
- [ ] Keep generated/vendor paths explicitly excluded rather than silently
      ignored.
- [ ] Add `ruff check backend` as a blocking CI job.

### V6C-1201 — Strengthen CI

- [ ] Backend package install.
- [ ] Ruff.
- [ ] Mypy.
- [ ] Full backend tests.
- [ ] Frontend lint/type checks.
- [ ] Frontend tests and production build.
- [ ] database migration from V5 fixture;
- [ ] clean-clone README smoke;
- [ ] safety/adversarial tests;
- [ ] compliance evidence validation;
- [ ] controlled Loop/Light Swarm end-to-end test;
- [ ] secret and generated-artifact scan.

### V6C-1202 — Run final regression

- [ ] Full backend test suite.
- [ ] Repository-wide Ruff.
- [ ] Repository-wide mypy.
- [ ] Full frontend test suite.
- [ ] Frontend production build.
- [ ] CLI command-group smoke.
- [ ] API route smoke.
- [ ] schema v1-to-current and V5-to-current migrations;
- [ ] Loop trigger/restart/kill suite;
- [ ] Safety/Autonomy bypass suite.
- [ ] resource/worktree/deadlock suite;
- [ ] typed evidence/checker/PR_READY suite;
- [ ] Light Swarm end-to-end suite;
- [ ] Deep Swarm controlled suite if included;
- [ ] memory runtime and retrieval suite;
- [ ] three operational Loop end-to-end suites;
- [ ] real comparative benchmark reproduction;
- [ ] clean-clone quickstart.

### V6C-1203 — Align documentation

- [ ] Update README with only verified capabilities.
- [ ] Update CHANGELOG with corrections and V6.1 closure.
- [ ] Update `MASTER_BACKLOG_V6.md` historical status accurately.
- [ ] Link this compliance backlog and final evidence.
- [ ] Correct install, database, Loop, Swarm, and benchmark commands.
- [ ] Mark experimental capabilities explicitly.
- [ ] Link every metric table to reproducible evidence.
- [ ] Remove claims contradicted by strict gate results.

### V6C-1204 — Clean the repository safely

- [ ] Inventory before deletion.
- [ ] Remove only confirmed caches, databases, logs, worktrees, build output, and
      temporary fixture repositories.
- [ ] Preserve ambiguous or user-authored files.
- [ ] Verify `.gitignore`.
- [ ] Verify no secret, large generated artifact, or private fixture is tracked.
- [ ] Rebuild and test from a fresh clone.

### V6C-1205 — Publish the compliant release

- [x] Generate final evidence at the exact release candidate commit.
- [x] Open the final release pull request or obtain explicit owner-directed
      synchronization approval.
- [x] Require all remote checks and human review.
- [x] Merge without auto-merge or synchronize the owner-approved commit without
      auto-merge.
- [x] Verify local and remote `main`.
- [x] Create an annotated version tag only after explicit human approval.
- [x] Push the tag.
- [x] Create the GitHub Release from the accepted tag.
- [x] Link release notes to immutable evidence.
- [x] Verify package, CHANGELOG, tag, GitHub Release, and evidence all identify
      the same commit.

**Phase C12 exit gate**

- [x] Final compliance verdict was published historically, but is now disputed.
- [x] All mandatory tests and CI gates pass.
- [x] No hard-coded benchmark evidence remains in the accepted compliance path.
- [x] All three operational loops consume controlled connector state.
- [x] Light Swarm enforces governed-worker evidence.
- [x] Deep Swarm status matches measured evidence and remains gated.
- [x] Quickstart commands are corrected for supported setup.
- [x] Repository is clean and synchronized.
- [x] Version tag and GitHub Release point to the historical commit.
- [ ] LocalForge may be described as a supervised-production-ready stable
      release.

---

## 7. Phase Dependency Map

```text
C0  Truth reset and immutable evidence
 |
C1  Packaging and quickstart
 |
C2  Canonical execution spine
 |
C3  Real Loop lifecycle
 |
C4  Non-bypassable safety and autonomy
 |
C5  Resources, worktrees, and PathIntents
 |
C6  Typed evidence, checker, and PR_READY
 |
C7  Real Light Swarm
 |
C8  Governed Deep Swarm
 |
C9  Operational memory integration
 |
C10 Real operational loops
 |
C11 Real comparative evaluation
 |
C12 Quality, documentation, and stable release
```

## 8. Recommended Branch Sequence

```text
fix/v6c-c00-truth-evidence
fix/v6c-c01-quickstart
feat/v6c-c02-execution-spine
feat/v6c-c03-loop-runtime
feat/v6c-c04-action-gateway
feat/v6c-c05-resource-coordination
feat/v6c-c06-evidence-pr-ready
feat/v6c-c07-light-swarm-runtime
feat/v6c-c08-deep-swarm-runtime
feat/v6c-c09-memory-runtime
feat/v6c-c10-operational-loops
test/v6c-c11-real-evaluation
release/v6.1-compliance
```

## 9. Final Compliance Scorecard

| Area | Required proof | Release requirement |
| --- | --- | --- |
| Evidence | Immutable commits, hashes, commands, PR, CI | Validator-generated `ACCEPTED` |
| Loop runtime | Real trigger, persistence, restart, kill | End-to-end pass |
| Dispatch | Scheduler uses capability-aware RunnerPool | Old pool unreachable |
| Safety | Every mutation passes action gateway | Zero bypass cases |
| Worktrees | Real isolated attempts and atomic PathIntents | No silent collisions |
| Handoffs | Valid typed artifacts on dependency edges | Missing evidence blocks readiness |
| Verification | Independent checker and pre-PR gate | Self-verification impossible |
| Light Swarm | Real bounded worker execution | Controlled repository task accepted |
| Deep Swarm | Real governed dynamic execution | Experimental unless benchmark gate passes |
| Memory | Scoped authoritative facts used and audited | No policy elevation |
| Operational loops | Real controlled issue/CI/PR workflows | Three loop contracts pass |
| Benchmark | Observed same-corpus executions | Aggregates reproducible |
| Quality | Ruff, mypy, tests, build, migration, security | All blocking CI checks pass |
| Quickstart | Clean-clone execution | README commands pass unchanged |
| Release | Tag, GitHub Release, evidence, commit | All identifiers agree |

## 10. Explicit Non-Goals

- Adding more providers for marketing breadth.
- A terminal emulator or custom renderer.
- Self-modifying LocalForge.
- Unlimited or very large agent swarms.
- Automatic merge or deployment.
- Replacing the current server-owned DAG with agent chat.
- New UI features unrelated to compliance closure.
- Enabling embeddings without measured retrieval benefit.
- Claiming automatic merge-conflict resolution.
- Lowering acceptance thresholds to preserve the V6 release claim.
- Treating passing unit tests as proof that external side effects occurred.
