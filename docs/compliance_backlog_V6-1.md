# LocalForge OS V6.1 — Audit-of-Audit Compliance Backlog

> Document version: 1.0
>
> Status: `IN_PROGRESS`
>
> Created: 2026-07-28
>
> Audit baseline: `e2cc2a32fb0c1bb97dbb8fa54f5c9468398b636e`
>
> Audited tag: `v6.1.0`
>
> Recommended target release: `v6.2.0`
>
> Continues: `MASTER_BACKLOG_V6.md` and `compliance_backlog_V6.md`

## 1. Objective

Correct the implementation, evidence, release-process, and publication gaps
that remained after the first V6.1 compliance pass.

The target is a truthful **supervised-production-ready stable release**:

- LocalForge may execute bounded engineering work unattended up to
  `PR_READY`;
- every mutation is governed, attributable, reversible where practical, and
  supported by persisted evidence;
- a human must review and merge every pull request;
- loops and swarms perform real controlled work instead of returning simulated
  success objects;
- state, idempotency, resource ownership, cancellation, and recovery survive
  process restarts;
- release claims are generated from observed execution and validated immutable
  evidence;
- a clean installation and a CPU-only demonstration can be verified without a
  local GPU;
- known limitations remain explicit and cannot be converted into `ACCEPTED` by
  documentation alone.

The existing annotated tag `v6.1.0` is immutable historical state. Do not move,
delete, or recreate it. Substantial runtime corrections must be published under
a new version. `v6.2.0` is recommended because this backlog changes runtime
behavior and evidence contracts, not only patches release notes.

## 2. Current Truth and Release Boundary

The audited V6.1 state has legitimate strengths:

- local `main`, `origin/main`, and `v6.1.0` resolve to the same commit;
- the release commit passed remote Ruff, mypy, backend tests, frontend tests,
  and frontend build;
- Scheduler starts pass through a governed execution service and use persisted
  RunnerPool dispatch decisions;
- scoped memory retrieval is present in runtime context construction;
- an annotated tag and GitHub Release exist.

Those facts do not close the findings below. Until every mandatory exit gate in
this document passes, the product status must be:

```text
V6.1: historical experimental release with disputed compliance acceptance
Next release: remediation in progress
Production claim: NOT ACCEPTED
```

## 3. Audit-of-Audit Findings

| ID | Non-conformity | Required release outcome |
| --- | --- | --- |
| AOA-01 | The published V6.1 manifest declares `ACCEPTED`, but the repository's own validator returns `INVALID` | The canonical final manifest passes the same validator in CI and after download from the GitHub Release |
| AOA-02 | V6.1 implementation and evidence commits were pushed directly to `main`; no reviewed PR is associated with them; 470 backlog items remain unchecked | Every remediation phase is delivered by a reviewed PR, with evidence generated from real GitHub state |
| AOA-03 | Daily Triage, CI Sweeper, and PR Babysitter retain process-local state and simulated side effects | All three loops operate through durable state and controlled real repository/GitHub-compatible adapters |
| AOA-04 | Strategy “observations” still assign synthetic token, cost, duration, and outcome values | Comparative metrics come exclusively from persisted executions and provider/cost ledgers |
| AOA-05 | `PR_READY` can be reached through the generic status method, and any non-empty dictionary is accepted as gate evidence | Exactly one server-owned transition validates a typed, complete, independently checked evidence bundle |
| AOA-06 | Light Swarm and Deep Swarm retain manually advanced graph state and do not dispatch all executable nodes through the canonical governed worker path | Ready nodes create real attempts, acquire resources, run workers, produce artifacts, and pass independent checking |
| AOA-07 | Loop schedules are stored but not executed by a durable schedule runtime; kill does not cascade to scheduler tasks and owned resources | Interval, cron, manual, and authenticated external triggers work durably; pause/kill/restart affect the complete ownership tree |
| AOA-08 | PathLease does not implement renewal, bounded waiting, deadlock handling, or race-safe acquisition | Concurrent writers are coordinated atomically and deterministically across processes and restarts |
| AOA-09 | Git tag and product documentation say V6.1 while backend, package, frontend, and CLI report `0.5.0` | One version source drives every package, CLI, image, manifest, tag, and release |
| AOA-10 | Importing `localforge.services.compliance_evidence` in a clean interpreter fails through a circular import | All supported public modules import independently in a clean installed environment |
| AOA-11 | The repository is private while README calls it open source; there is no hosted demo, release asset, video, or current visual walkthrough | Publication state is truthful and an evidence-backed, GPU-free recruiter path is available |
| AOA-12 | Green unit tests do not cover all production claims, migrations, security boundaries, recovery, and external side effects | Production acceptance includes clean-clone, migration, concurrency, recovery, security, and controlled end-to-end evidence |

## 4. Non-Negotiable Invariants

- No automated actor may merge, deploy, approve its own PR, or push directly to
  protected `main`.
- Human review is mandatory. “Owner-authorized synchronization” is not a
  substitute for a reviewed PR in compliance evidence.
- No code path other than the canonical gate may assign task status
  `PR_READY`.
- `PR_READY` means mechanically verified engineering readiness, not permission
  to merge or deploy.
- Every file write, command, Git mutation, external mutation, PR creation, and
  readiness transition passes the ActionGateway and emits correlated audit
  evidence.
- A Boolean, status string, log message, or mocked return object is not proof
  that an external side effect occurred.
- Unit-test success is not sufficient evidence for a production side effect.
  Tests must inspect the repository, process, database, artifact, or controlled
  remote state that should have changed.
- Benchmark values may not be selected by implementation code, fixtures, or
  documentation.
- Unknown token, cost, duration, or provider data remains `UNKNOWN`; it must not
  become zero.
- The existing `v6.1.0` tag and historical artifacts remain unchanged.
- Repository visibility, tag creation, release publication, merge, push, and
  deployment require explicit owner approval at the relevant phase.
- Full-suite execution follows `AGENTS.md`: targeted tests first; broad final
  validation only with explicit human authorization.

## 5. Task and Verdict Semantics

All checkboxes in this document start unchecked.

Task statuses:

- `NOT_STARTED`: no implementation evidence exists;
- `IN_PROGRESS`: code may exist, but the task exit gate has not passed;
- `EVIDENCE_READY`: local/PR evidence exists, but review, merge, or remote CI is
  incomplete;
- `ACCEPTED`: validator-confirmed evidence, reviewed PR, merge commit, and
  required CI all exist;
- `PARTIAL`: useful behavior exists, but one or more mandatory outcomes are
  unproven;
- `REJECTED`: a safety, integrity, or mandatory functional gate failed.

Only the evidence validator may produce the final phase verdict. Authored
Markdown, checkbox state, test names, and manually entered JSON verdicts are
not authoritative.

## 6. Evidence Architecture

### 6.1 Candidate evidence committed with each phase

```text
docs/e2e/v6_2_compliance/phase_RNN/
  candidate_manifest.json
  test_summary.json
  acceptance_report.md
  known_limitations.md
```

The candidate manifest must include:

- schema version and phase/task IDs;
- exact source commit and parent commit;
- input and fixture hashes;
- environment fingerprint;
- exact commands, exit codes, test counts, and relevant durations;
- changed runtime surfaces;
- observed side-effect locations;
- known limitations;
- candidate verdict generated by the validator.

### 6.2 Final release evidence

A committed artifact cannot truthfully contain the merge commit that contains
itself. Avoid circular evidence.

The release process therefore has two stages:

1. The reviewed release PR contains candidate evidence for its head commit.
2. After human merge and tag approval, the release workflow generates a final
   acceptance bundle from the immutable tag commit, reviewed PR, merge commit,
   remote CI runs, and candidate inputs.

Publish the final bundle as GitHub Release assets:

```text
localforge-v6.2.0-compliance-manifest.json
localforge-v6.2.0-test-summary.json
localforge-v6.2.0-sbom.spdx.json
localforge-v6.2.0-demo-run.json
SHA256SUMS
```

The downloaded manifest must validate independently against the tagged
repository.

### 6.3 Validator fail-closed requirements

The canonical validator must reject:

- `HEAD`, branch names, missing commits, or mutable refs as evidence identities;
- missing source/parent commits;
- missing, empty, or mismatched input hashes;
- missing mandatory commands or non-integer exit codes;
- a manually authored `ACCEPTED`;
- missing reviewed PR, merge commit, human review, or CI URL;
- a PR that was not merged into the expected protected branch;
- a CI run for a different commit;
- a tag that does not resolve to the accepted commit;
- package versions that disagree with the release version;
- failed or skipped mandatory checks;
- synthetic benchmark observations;
- `ACCEPTED` while any mandatory phase is `PARTIAL`, `INVALID`, or
  `REJECTED`.

## 7. Mandatory Phase Delivery Gate

Each phase must follow this sequence:

- [ ] Create a dedicated branch from the reviewed `origin/main`.
- [ ] Add the smallest failing regression test before the runtime fix.
- [ ] Implement only the phase scope.
- [ ] Run the targeted failing test.
- [ ] Run the nearest related test module.
- [ ] Run changed-file Ruff and mypy checks.
- [ ] Run `git diff --check`.
- [ ] Generate candidate evidence; do not hand-author the verdict.
- [ ] Open a PR containing implementation, tests, evidence, limitations, and
      rollback notes.
- [ ] Obtain human review.
- [ ] Require remote CI for the exact PR head.
- [ ] Merge only after owner approval.
- [ ] Verify the merge commit on `origin/main`.
- [ ] Generate the accepted phase record from merged GitHub state.

If repository-plan limitations prevent branch protection while private, the
phase remains `EVIDENCE_READY`. Do not label that condition `ACCEPTED`. Enable
an enforceable ruleset when the repository becomes public or the account plan
supports it.

---

## Phase R0 — Truth Reset and Immutable Audit Baseline

### Goal

Remove the false stable-release boundary before additional implementation and
make the ten audited defects reproducible.

### V61C-000 — Publish the audit-of-audit record

- [x] Add an immutable audit report mapping AOA-01 through AOA-12 to exact
      files, lines, commands, and observed results.
- [x] Record `e2cc2a32fb0c1bb97dbb8fa54f5c9468398b636e` as the audited baseline.
- [x] Record the successful V6.1 CI separately from the failed compliance
      verdict.
- [x] Preserve the original release and evidence for historical traceability.

### V61C-001 — Correct current product status

- [x] Replace “accepted supervised-production-ready stable release” with
      truthful experimental/partial wording in README and release-facing docs.
- [x] Mark the V6.1 acceptance report and manifest as historical disputed
      evidence without rewriting the `v6.1.0` tag.
- [x] Add the validator's exact V6.1 rejection reasons.
- [x] State which features are real, partial, simulated, or experimental.

### V61C-002 — Reconcile backlog truth

- [x] Remove the contradiction between 470 unchecked items and the accepted
      closure block.
- [x] Preserve completed work as implementation history, not compliance proof.
- [x] Generate backlog status from validated task evidence where practical.
- [x] Prevent a final release verdict while mandatory checkboxes or phase
      records remain unresolved.

### V61C-003 — Establish the next release identity

- [ ] Approve the next version with the owner; default recommendation is
      `6.2.0`.
- [x] Document that `v6.1.0` will not be moved or replaced.
- [x] Define candidate and stable tag conventions.

### Required regression tests

- [x] Current V6.1 manifest returns `INVALID`.
- [x] A release summary cannot claim stable acceptance from a green CI result
      alone.
- [x] An unresolved mandatory task prevents final acceptance.

### Phase R0 exit gate

- [ ] Product status is truthful everywhere.
- [x] The baseline audit is immutable and reproducible.
- [x] No new stable-release claim exists.

---

## Phase R1 — Packaging, Version Integrity, and Import Hygiene

### Goal

Make installation, import, migration, and version behavior coherent before
changing orchestration.

### V61C-100 — Create one release-version source

- [x] Define one canonical version source.
- [x] Derive Python package, `localforge --version`, backend metadata, frontend
      package, container labels, manifests, and release notes from it.
- [x] Add a CI check that fails on version drift.
- [x] Verify candidate tags match the derived version.

### V61C-101 — Eliminate circular imports

- [x] Remove eager re-export cycles among `services`, `storage`,
      `transactions`, and `audit`.
- [x] Define supported public import boundaries.
- [x] Avoid test-order-dependent import success.
- [x] Verify modules under a clean interpreter, not only through pytest.

### V61C-102 — Verify clean installation

- [x] Build an sdist and wheel in an isolated environment.
- [x] Install the wheel without the repository on `PYTHONPATH`.
- [x] Run CLI version/help and import smoke tests.
- [x] Verify Windows and Linux installation paths.
- [x] Correct the demo guide's nonexistent sample-directory reference.

### V61C-103 — Verify database upgrade and rollback safety

- [x] Create a versioned V5/V6 fixture database.
- [x] Upgrade it to the current schema without losing projects, runs, tasks,
      audit events, memory, graphs, leases, or artifacts.
- [x] Document backup and restore.
- [x] Fail safely on an unsupported future schema.

### Required regression tests

- [x] Fresh interpreter imports every supported public module independently.
- [x] Installed CLI reports the candidate release version.
- [x] Backend, frontend, manifest, and tag version consistency check passes.
- [x] Clean wheel install and CLI smoke pass on Windows and Linux CI.
- [x] Database fixture upgrade and backup/restore pass.

### Phase R1 exit gate

- [x] No import-order dependency remains.
- [x] One version is reported across all deliverables.
- [x] Clean installation and migration evidence is reproducible.

---

## Phase R2 — Canonical Evidence, Reviewed PRs, and Release Truth

### Goal

Make it impossible for authored JSON or Markdown to override repository and CI
facts.

### V61C-200 — Define the canonical evidence schema

- [x] Replace incompatible V6.1 manifest shapes with one versioned schema.
- [x] Require immutable commits, PR, merge, CI, commands, hashes, environment,
      limitations, and generated gate reasons.
- [x] Distinguish candidate evidence from final post-merge release evidence.
- [x] Add deterministic JSON serialization and SHA-256 checksums.

### V61C-201 — Harden the compliance validator

- [x] Validate the actual published schema, not only test-only fixture shapes.
- [x] Query or consume trusted GitHub metadata for PR, review, merge, tag, and
      CI association.
- [x] Reject direct-to-main implementation as reviewed-PR evidence.
- [x] Reject self-review and missing human review.
- [x] Reject mismatched package/release versions.
- [x] Reject synthetic benchmark records and incomplete mandatory phases.

### V61C-202 — Integrate validation into CI and release workflow

- [x] Validate candidate evidence on every compliance PR.
- [ ] Generate final evidence only after reviewed merge and owner-approved tag.
- [ ] Revalidate downloaded release assets in a clean job.
- [x] Upload validator output and checksums as immutable workflow artifacts.

### V61C-203 — Enforce reviewed delivery

- [ ] Configure a GitHub ruleset or branch protection for `main`.
- [ ] Require PR review and successful mandatory checks.
- [ ] Disable force pushes and branch deletion where supported.
- [ ] Document the exact human-only exception process for emergencies; an
      exception must invalidate normal release acceptance until reviewed.

### Required regression tests

- [x] Published V6.1 manifest is rejected for the expected reasons.
- [x] Manual `ACCEPTED` override is rejected.
- [x] Missing/mismatched PR, review, merge, tag, or CI data is rejected.
- [x] A complete immutable fixture reaches `ACCEPTED`.
- [ ] A final release asset validates after download in a clean checkout.

### Phase R2 exit gate

- [x] Validator output is the only release truth.
- [x] Evidence cannot claim facts absent from GitHub.
- [x] Reviewed PR delivery is mechanically enforced or remains explicitly
      `EVIDENCE_READY`.

---

## Phase R3 — Non-Bypassable ActionGateway and `PR_READY`

### Goal

Guarantee that every mutation and readiness decision crosses one typed,
audited, fail-closed gate.

### V61C-300 — Define typed readiness evidence

- [x] Add a versioned `PRReadyEvidence` contract.
- [x] Require task/run identity, source commit, worktree/branch, diff hash,
      test commands and results, typed handoffs, maker identity, independent
      checker identity, risk verdict, safety verdict, and pre-PR gate result.
  - Candidate R3 implementation now requires task-run identity,
    branch/worktree context, source commit, target commit, diff hash,
    deterministic checks, persisted artifacts, independent maker/checker
    identities and attempt IDs, typed `PR_READY` handoff ownership, risk
    verdict, safety verdict, and pre-PR gate success.
- [x] Reject unknown, stale, cross-task, or mismatched evidence.
  - Candidate R3 implementation rejects unknown, cross-task, branch/worktree
    mismatches, unknown handoff/artifact paths, stale current source/target
    commit metadata, and persisted worktree-manifest source commit mismatches.
- [x] Bind evidence to the exact source and target commits.

### V61C-301 — Make one transition authoritative

- [x] Prevent generic `update_task_status()` from accepting `PR_READY`.
- [x] Route all readiness transitions through one server-owned service.
- [ ] Remove direct readiness assignment from Pipeline, Light Swarm, Deep
      Swarm, API, CLI, fixtures, and recovery paths.
- [x] Make the transition atomic with evidence persistence.
- [x] Make readiness idempotent for the same evidence and reject conflicting
      replay.

### V61C-302 — Enforce independent checking

- [x] Prohibit maker and checker from sharing identity or attempt ownership.
  - Candidate R3 implementation prohibits identical maker/checker identities;
    it now also prohibits identical maker/checker attempt identities.
- [ ] Require checker execution after the final maker commit.
- [ ] Invalidate checker evidence when source, dependency, test, or target
      branch state changes.
- [ ] Require MechanicalPrePRGate success after checker approval.
  - Candidate R3 implementation requires `pre_pr_gate.passed == true`; explicit
    ordering after checker approval remains open.

### V61C-303 — Close ActionGateway bypasses

- [ ] Inventory every file, shell, Git, external API, PR, status, and artifact
      mutation path.
- [ ] Route all paths through a shared ActionGateway.
- [ ] Deny unknown action kinds and missing execution context.
- [ ] Persist autonomy and safety decisions with one correlation ID.
- [ ] Prove that auto-merge, force-push, test weakening, protected-path writes,
      and policy elevation are denied.

### Required regression tests

- [x] Empty or arbitrary dictionaries cannot satisfy `PRReadyEvidence`.
- [x] Generic status APIs cannot reach `PR_READY`.
- [x] Same maker/checker identity is rejected.
- [x] Stale evidence is rejected after source or target branch changes.
- [x] Missing tests, diff, handoff, checker, or pre-PR gate blocks readiness.
  - Candidate R3 implementation covers missing tests, diff hash, checker,
    typed handoff, pre-PR gate, risk/safety verdicts, and persisted artifacts.
- [ ] Every mutation surface has a negative bypass test.
- [x] A valid controlled task reaches `PR_READY` exactly once.

### Phase R3 exit gate

- [x] Static search and tests find one readiness transition.
- [ ] No mutation bypasses the ActionGateway.
- [ ] Valid readiness has complete independently verified evidence.

---

## Phase R4 — Durable Loop Runtime and Lifecycle Cascade

### Goal

Execute real interval, cron, manual, and external-event loops with durable
ownership, idempotency, cancellation, and restart recovery.

### V61C-400 — Implement the schedule runtime

- [x] Parse and validate interval and cron expressions.
- [x] Define timezone and daylight-saving behavior.
- [x] Persist `next_run_at`, last trigger, trigger revision, and misfire policy.
- [x] Claim due schedules atomically across multiple coordinator processes.
- [x] Support bounded catch-up after downtime without duplicate execution.

### V61C-401 — Implement authenticated external triggers

- [x] Add provider-neutral webhook/event adapters.
- [x] Verify signatures or credentials before accepting external events.
- [x] Persist stable provider event IDs and idempotency keys.
- [x] Sanitize untrusted text without relying on string replacement alone.
- [x] Apply rate limits, bounded payload sizes, and replay windows.

### V61C-402 — Persist triage and actionable work

- [x] Remove default fake actionable items.
- [x] Persist triage input, classification, decision, and resulting task IDs.
- [x] Make retries reuse the same persisted identity.
- [x] Ensure actionable items enter the canonical Scheduler path.

### V61C-403 — Implement full pause, kill, and recovery cascade

- [ ] Define ownership from LoopRun to Scheduler Run, tasks, task runs, worker
      processes, RunnerPool leases, PathLeases, worktrees, and external action
      reservations.
- [x] Pause prevents new dispatch without corrupting active work.
- [ ] Kill cancels active work, terminates bounded subprocesses, releases
      resources, and records incomplete artifacts.
  - Candidate implementation now cancels the associated Scheduler Run, cancels
    pending/running TaskRuns, releases PathLeases, releases RunnerPool
    reservations, marks worktree attempt manifests `CANCELLED`, and proves
    repeated kill idempotency for those persisted owners. Controlled worker
    subprocess termination, external action reservations, and incomplete
    artifact capture remain open.
- [ ] Restart reconciliation recovers or safely fails every orphaned owner.
  - Candidate recovery now completes interrupted triage without duplicate tasks,
    safely fails RUNNING LoopRuns missing their scheduler owner, and propagates
    terminal scheduler states back to the LoopRun. Full orphan reconciliation for
    subprocesses, worktrees on disk, leases, and external reservations remains
    open.
- [ ] Repeated pause/kill/recovery calls are idempotent.

### Required regression tests

- [x] Fake-clock interval and cron execution.
- [x] Two coordinators cannot claim the same trigger.
- [x] Restart before/after triage and task creation does not duplicate work.
- [x] Authenticated webhook replay is deduplicated.
- [ ] Kill cancels actual controlled worker processes and releases resources.
  - Persisted scheduler, task-run, RunnerPool, PathLease, and worktree-manifest
    resource release is covered by
    `backend/tests/test_phase6_circuit_breakers.py::test_kill_loop_run`.
- [x] Recovery reconciles orphaned LoopRun and Scheduler state.

### Phase R4 exit gate

- [ ] All trigger kinds execute durably.
  - Candidate R4 implementation executes manual, interval, cron, and
    authenticated external events through durable loop records; full R4
    lifecycle ownership acceptance remains open.
- [x] No fake actionable default remains.
- [ ] Lifecycle actions affect the complete ownership tree.

---

## Phase R5 — Atomic Runner, Worktree, and Path Coordination

### Goal

Make concurrent execution deterministic and restart-safe.

### V61C-500 — Harden RunnerPool reservation

- [x] Preserve atomic capacity reservation across concurrent schedulers.
- [x] Add lease identity, heartbeat, expiry, and owner fencing tokens.
- [x] Prevent a stale process from releasing or using a newer owner's lease.
- [ ] Implement bounded backpressure and fairness.
- [ ] Reconcile capacity from persisted task-run truth after restart.

### V61C-501 — Make PathLease acquisition race-safe

- [x] Normalize Windows/Linux paths, separators, and case rules.
- [ ] Normalize symlinks and enforce repository-boundary canonicalization.
- [x] Enforce exact-path conflicts through a database active-lease key.
- [ ] Enforce parent/child overlap conflicts atomically at the
      database/transaction layer.
- [x] Prevent two sessions from acquiring the exact same normalized path after
      identical pre-checks.
- [x] Associate every write lease with task run, attempt, worktree, and fencing
      token.

### V61C-502 — Add renewal, wait, and deadlock behavior

- [x] Implement lease renewal/heartbeat.
- [ ] Add bounded FIFO waiting with timeout and cancellation.
- [ ] Persist the wait-for graph.
- [ ] Detect deadlock cycles and choose a deterministic victim.
- [ ] Escalate repeated contention instead of busy-waiting.

### V61C-503 — Complete worktree lifecycle

- [ ] Create a real isolated worktree before code mutation.
- [ ] Bind its branch and base commit to the task attempt.
- [ ] Validate repository cleanliness and target-branch drift.
- [ ] Reconcile stale worktrees without deleting user-owned paths.
- [ ] Release or retain failed worktrees according to evidence/diagnostic
      policy.

### Required regression tests

- [ ] Concurrent database sessions race for the same path.
- [x] Case, separator, exact-path, and directory overlap conflicts.
- [ ] Symlink and repository-boundary overlap conflicts.
- [x] Renewal prevents premature takeover.
- [x] Expired leases can be safely reclaimed with fencing.
- [ ] Deadlock victim selection is deterministic.
- [ ] Kill and restart release/reconcile all owned resources.
- [ ] Real temporary Git worktree lifecycle is inspected on disk.

### Phase R5 exit gate

- [ ] No silent path collision is possible in supported databases.
- [x] Stale owners cannot release runner/path leases after lease loss when
      fencing tokens are used.
- [ ] Resource state survives and reconciles after restart.

---

## Phase R6 — Real Light Swarm Execution

### Goal

Replace manually advanced swarm state with bounded governed worker execution.

### V61C-600 — Dispatch ready nodes

- [ ] Convert every ready node into a persisted task attempt.
- [ ] Dispatch through GovernedExecution and the capability-aware RunnerPool.
- [ ] Acquire the required worktree and PathLeases before mutation.
- [ ] Persist selected runner, worker identity, start/end time, cost, tokens,
      and exit reason.
- [ ] Apply global and per-node concurrency limits.

### V61C-601 — Execute typed node roles

- [ ] Implement bounded maker, test, critique, verify, and aggregation workers.
- [ ] Bind input/output TypedHandoff artifacts to DAG edges.
- [ ] Enforce maker/checker separation.
- [ ] Reject node completion without the contracted artifact.
- [ ] Restrict manual completion endpoints to authenticated internal worker
      callbacks with ownership tokens.

### V61C-602 — Implement failure and lifecycle behavior

- [ ] Route retries through persisted attempt budgets and circuit breakers.
- [ ] Propagate failure/blocking only through affected descendants.
- [ ] Pause stops new node dispatch.
- [ ] Kill cancels active nodes and releases resources.
- [ ] Restart reconstructs ready/running/blocked nodes from durable state.

### V61C-603 — Aggregate through the canonical readiness gate

- [x] Remove direct `run.verdict = "PR_READY"` behavior.
- [x] Aggregate evidence without changing task readiness.
- [ ] Submit the complete typed evidence bundle to the R3 readiness service.
- [ ] Preserve `PARTIAL`, `FAILED`, or `NEEDS_HUMAN` when a gate is missing.

### Required regression tests

- [ ] A controlled multi-node repository task produces real commits/artifacts.
- [ ] RunnerPool dispatch logs exist for every executable node.
- [ ] Worktrees and leases exist during execution and reconcile afterward.
- [ ] Missing artifact or same-identity checker blocks completion.
- [ ] Pause, retry, kill, and restart operate on real attempts.
- [x] No Light Swarm aggregate result can manufacture task `PR_READY`.
- [ ] Restrict manual completion endpoints with authenticated ownership tokens.

### Phase R6 exit gate

- [ ] Light Swarm performs real bounded work.
- [ ] Every executable node uses the canonical governed path.
- [x] Light Swarm no longer produces `PR_READY` directly.
- [ ] Only the canonical readiness service can produce `PR_READY` across every
      swarm/manual status surface.

---

## Phase R7 — Governed Deep Swarm Execution

### Goal

Execute validated dynamic DAG nodes through the same safety and evidence path
without enabling uncontrolled expansion.

### V61C-700 — Connect dynamic nodes to governed execution

- [ ] Dispatch dynamically ready atomic nodes through GovernedExecution.
- [ ] Enforce RunnerPool, worktree, lease, budget, and ActionGateway rules.
- [ ] Require typed dependency evidence before a node becomes ready.
- [ ] Persist every dynamic attempt and resource owner.

### V61C-701 — Govern graph mutation

- [x] Require a registered decision-contract artifact for expansion.
- [ ] Validate graph version, parent revision, acyclicity, node/edge limits,
      budget effect, and allowed node types atomically.
- [x] Reject stale or conflicting graph mutations.
- [ ] Audit the proposer, rationale, evidence, and validator verdict.

### V61C-702 — Implement recovery and cancellation

- [ ] Reconcile graph version, queue, attempts, leases, and artifacts together.
- [ ] Cancel descendants deterministically.
- [ ] Resume only nodes whose ownership and evidence are still valid.
- [ ] Prevent duplicate external actions during replay.

### V61C-703 — Preserve experimental gating

- [ ] Keep Deep Swarm disabled by default until Phase R9 evidence passes.
- [ ] Do not advertise production superiority without accepted comparative
      evidence.
- [ ] Provide deterministic fallback to Light Swarm or single-worker mode.

### Required regression tests

- [ ] Controlled dynamic expansion executes real worker nodes.
- [x] Stale/conflicting mutation is rejected.
- [ ] Crash during expansion or node execution recovers without duplication.
- [ ] Budget/node/depth limits cannot be bypassed.
- [x] Forced expansion without registered decision evidence is rejected.

### Phase R7 exit gate

- [ ] Dynamic execution is governed by the same invariants as static execution.
- [x] Deep Swarm remains experimental unless explicit opt-in and registered
      decision evidence are present.
- [ ] Deep Swarm benchmark acceptance gate still required before production
      promotion.

---

## Phase R8 — Real Operational Loops and Connectors

### Goal

Replace local dictionaries, sets, and claimed side effects with durable,
inspectable behavior.

### V61C-800 — Implement production connector boundaries

- [ ] Keep the deterministic LocalRepositoryConnector for tests and demo.
- [ ] Add a GitHub-compatible connector with least-privilege capabilities.
- [ ] Implement pagination, rate-limit handling, bounded retries, timeouts,
      idempotency, and sanitized logging.
- [ ] Separate read-only L1 credentials from draft-PR L2 credentials.
- [ ] Keep merge, approval, and deployment capabilities absent.

### V61C-801 — Make Daily Triage durable

- [x] Replace `_acting_on_store` with durable event/decision state.
- [x] Deduplicate across process restart.
- [ ] Deduplicate across multiple workers with database transaction fencing.
- [ ] Persist the source revision and invalidate stale classifications.
- [ ] Prove zero external mutations in L1 mode.

### V61C-802 — Make CI Sweeper perform a bounded repair

- [ ] Remove simulated repair summaries.
- [ ] Fetch a controlled failed check and reproduce the failing test.
- [ ] Create a real isolated worktree and branch.
- [ ] Apply only an allowlisted bounded correction through governed workers.
- [ ] Rerun the original failure and adjacent regression tests.
- [ ] Require independent checker evidence.
- [ ] Create/update an idempotent draft PR through the connector.
- [ ] Inspect the resulting repository, diff, test artifact, and draft PR.

### V61C-803 — Make PR Babysitter perform real review work

- [x] Replace process-local `processed_event_ids` with durable idempotency.
- [ ] Bind comments to exact PR head SHA, path, and line.
- [ ] Create a real worktree for eligible small fixes.
- [ ] Apply, test, independently verify, and push/update only the draft branch.
- [ ] Invalidate evidence when upstream or PR head changes.
- [ ] Escalate merge conflicts; never silently resolve, approve, or merge them.

### V61C-804 — Add controlled remote end-to-end fixtures

- [ ] Use a dedicated disposable repository/account or a fully compatible local
      Git server fixture.
- [ ] Create issues, failed checks, review comments, branches, and draft PRs.
- [ ] Verify remote state after each action.
- [ ] Clean only disposable fixture resources.
- [ ] Record rate-limit and API failure behavior.

### Required regression tests

- [x] Idempotency survives service restart for all three loops.
- [ ] Daily Triage performs no external mutation.
- [ ] CI Sweeper changes a real temporary repository and creates one draft PR.
- [ ] CI Sweeper cannot edit flaky/environment failures or weaken tests.
- [ ] PR Babysitter changes the expected line on the correct head SHA.
- [ ] Replayed events do not duplicate commits, comments, or PRs.
- [ ] Upstream drift invalidates stale evidence.

### Phase R8 exit gate

- [ ] No operational loop reports an unperformed side effect.
- [ ] All loop identities and attempts are durable.
- [ ] Remote mutations remain draft-only and human-merge-only.

---

## Phase R9 — Observed Comparative Evaluation

### Goal

Replace synthetic strategy outcomes with reproducible executions of the same
corpus under controlled conditions.

### V61C-900 — Build an immutable evaluation corpus

- [x] Version each task, repository fixture, expected outcome, acceptance test,
      safety expectation, and difficulty class.
- [x] Separate development fixtures from holdout tasks.
- [x] Hash actual non-empty corpus files.
- [x] Record licenses and provenance for every fixture.

### V61C-901 — Instrument observed execution

- [x] Persist strategy, task, model/provider, prompt/context revision, attempts,
      start/end times, tokens, cost ledger entries, readiness evidence, safety
      events, and human outcome.
- [x] Remove constants for tokens, costs, durations, or success.
- [x] Mark unavailable measurements `UNKNOWN`.
- [x] Bind each observation to task-run and artifact IDs.

### V61C-902 — Run fair strategy comparisons

- [x] Execute single-worker baseline, Loop single-worker, Light Swarm, and
      optionally Deep Swarm on the same corpus.
- [x] Keep model/provider eligibility, budgets, timeout, environment, target
      commit, and acceptance tests equivalent.
- [x] Record warm-up policy and repeated runs.
- [x] Preserve failures and timeouts in aggregates.

### V61C-903 — Apply statistical and release discipline

- [x] Report sample size, variance, confidence interval where meaningful, and
      missing data.
- [x] Calculate `PR_READY` rate only from valid canonical readiness records.
- [x] Calculate cost/tokens only from provider and local ledger evidence.
- [x] Separate proof-run completion from target achievement.
- [x] Keep a strategy `PARTIAL` when superiority or safety thresholds are not
      met.

### V61C-904 — Generate all benchmark publications

- [ ] Generate JSONL observations, aggregates, tables, and Markdown from the
      same data.
- [x] Remove hand-maintained performance tables from release truth.
- [x] Include reproduction commands and environment fingerprints.
- [ ] Validate hashes and row counts in CI.

### Required regression tests

- [x] Metrics change when persisted observations change.
- [x] No production evaluation code assigns synthetic token/cost/duration.
- [x] Unknown measurements remain unknown.
- [x] Same-corpus/fair-budget violations invalidate comparison.
- [ ] Generated README/report tables match JSON aggregates exactly.

### Phase R9 exit gate

- [x] Every published number traces to an observed task run.
- [x] Light/Deep Swarm status reflects measured evidence.
- [x] Unsupported superiority claims are absent.

---

## Phase R10 — Production Hardening and Operability

### Goal

Prove that supervised operation is secure, observable, recoverable, and
bounded beyond the happy path.

### V61C-1000 — Define and enforce the threat model

- [ ] Document trusted actors, untrusted inputs, secrets, protected resources,
      and external capabilities.
- [x] Add API authentication/authorization appropriate to local and hosted
      modes.
- [ ] Restrict CORS, payload sizes, filesystem roots, network access, and
      subprocess environment.
- [x] Redact secrets from prompts, logs, artifacts, audit records, and demo
      exports.
- [ ] Add dependency, secret, and static-security scans to release CI.

### V61C-1001 — Add production observability

- [ ] Emit structured logs with project/run/task/attempt/correlation IDs.
- [ ] Add metrics for queue depth, dispatch latency, active workers, failures,
      retries, breaker state, lease contention, costs, and readiness outcomes.
- [x] Add health, readiness, and dependency diagnostics.
- [ ] Define audit retention/export and personally identifiable information
      handling.
- [ ] Provide an operator view for active loops, workers, leases, and blockers.

### V61C-1002 — Add recovery and failure-injection tests

- [ ] Kill coordinator, scheduler, and worker processes at controlled points.
- [ ] Inject database lock, disk-full, timeout, provider failure, rate limit,
      malformed event, stale branch, and lost-lease conditions.
- [ ] Verify bounded retries, no duplicate external action, and honest terminal
      state.
- [ ] Verify backups and documented recovery.

### V61C-1003 — Verify capacity and backpressure

- [ ] Measure bounded concurrency on representative CPU-only hardware.
- [ ] Verify queue fairness and resource ceilings.
- [ ] Prevent runaway task, graph, token, cost, disk, and process growth.
- [ ] Document supported scale and non-goals.

### V61C-1004 — Produce deployment reference

- [ ] Provide a CPU-only reference deployment with persistent storage.
- [ ] Define configuration/secrets through environment or secret stores.
- [ ] Provide startup, shutdown, backup, upgrade, rollback, and health
      procedures.
- [ ] Keep optional model providers and GPU acceleration outside core
      availability requirements.

### Required regression tests

- [x] Authentication and authorization negative cases.
- [ ] Prompt-injection, path traversal, command-injection, SSRF, secret
      redaction, and oversized-payload tests.
- [ ] Dependency and secret scans have blocking release thresholds.
- [ ] Crash/failure injection preserves durable truth and avoids duplication.
- [ ] Resource-limit and backpressure tests terminate within defined ceilings.

### Phase R10 exit gate

- [ ] Threat model controls are enforced.
- [ ] Operators can diagnose and recover supported failures.
- [ ] CPU-only supervised deployment is documented and reproducible.

---

## Phase R11 — GPU-Free Demonstration and Public Portfolio Readiness

### Goal

Let a recruiter verify the real control-plane behavior without installing the
project, providing API keys, or owning a GPU.

### V61C-1100 — Create a deterministic CPU-only demo scenario

- [x] Add `localforge demo --scenario ci-regression --deterministic`.
- [ ] Use a disposable local Git repository, versioned event, real worktree,
      real diff, real tests, governed gates, and persisted artifacts.
- [x] Use clearly labeled pre-recorded worker outputs only where model
      inference is not required.
- [x] Do not label replayed output as a live model call.
- [x] Export a sanitized, schema-versioned `demo_run.json`.

### V61C-1101 — Build an interactive evidence replay

- [x] Create a static browser experience driven by `demo_run.json`.
- [ ] Show event/PRD, triage, DAG, dispatch, worktree, safety decisions,
      maker/checker handoff, tests, readiness gate, diff, and draft PR.
- [ ] Link every displayed fact to its evidence record and source commit.
- [ ] Make the replay deployable to GitHub Pages or equivalent static hosting.
- [x] Ensure no backend, GPU, provider credential, or paid request is required.

### V61C-1102 — Produce a concise visual walkthrough

- [ ] Record a 3–5 minute narrated demonstration.
- [ ] Add a short GIF or video preview above the README fold.
- [ ] Include architecture, safety boundaries, failure behavior, and final
      evidence—not only the happy-path UI.
- [ ] Attach the sanitized run and checksums to the release.

### V61C-1103 — Create the recruiter path

- [ ] Add prominent `Watch`, `Try`, `Verify`, and `Architecture` links.
- [ ] Provide a one-page technical case study: problem, design decisions,
      tradeoffs, measured results, limitations, and individual contribution.
- [ ] Link CI, accepted evidence, release assets, architecture decision records,
      and a representative reviewed PR.
- [ ] Keep setup instructions as a secondary path.

### V61C-1104 — Prepare safe public publication

- [ ] Run tracked-file and Git-history secret review.
- [ ] Review `.gitignore`, generated artifacts, private fixtures, log files,
      model outputs, personal data, and large files.
- [ ] Verify MIT license, third-party notices, contribution, security, support,
      and code-of-conduct documents.
- [ ] Improve GitHub description, topics, homepage, release notes, and social
      preview.
- [ ] Change repository visibility only after explicit owner approval.

### Required regression tests

- [x] Deterministic demo completes on CPU without provider keys.
- [x] Demo output validates against its schema and checksums.
- [x] Static replay renders from the release artifact.
- [x] Demo contains no secret or private path.
- [x] Displayed events, results, and metrics match the evidence bundle.

### Phase R11 exit gate

- [ ] A reviewer can understand and verify one complete run in under five
      minutes.
- [ ] No local GPU or installation is needed for the primary demo.
- [ ] Public claims match accepted evidence and known limitations.

---

## Phase R12 — Final Regression, Release Candidate, and Stable Publication

### Goal

Validate all product and evidence contracts from a clean environment and
publish only after explicit human approval.

### V61C-1200 — Run the final clean-clone validation ladder

- [ ] Fresh Linux clone and wheel installation.
- [ ] Fresh Windows clone and wheel installation.
- [ ] Backend Ruff.
- [ ] Backend mypy.
- [ ] Full backend tests.
- [ ] Frontend tests and production build.
- [ ] Import matrix.
- [ ] Database migration, backup, and restore.
- [ ] Loop schedule/restart/kill integration suite.
- [ ] Runner/lease/worktree concurrency suite.
- [ ] `PR_READY` and ActionGateway adversarial suite.
- [ ] Light Swarm controlled repository end-to-end suite.
- [ ] Deep Swarm controlled suite if enabled; otherwise verify disabled default.
- [ ] Operational-loop controlled remote suite.
- [ ] Observed benchmark reproduction.
- [ ] Security and secret scans.
- [x] CPU-only deterministic demo and static replay validation.
- [x] `git diff --check`.

### V61C-1201 — Reconcile all release documentation

- [ ] Generate README benchmark tables from accepted data.
- [ ] Update CHANGELOG from merged PRs.
- [ ] Document architecture, deployment, operations, recovery, security,
      limitations, and demo.
- [ ] Remove stale V6.1 production claims.
- [ ] Verify all commands and links from a clean clone.

### V61C-1202 — Sanitize the release tree

- [ ] Inventory untracked/ignored and generated files without destructive
      cleanup.
- [ ] Remove only explicitly approved build/test artifacts.
- [ ] Verify no secret, local database, private fixture, cache, model weight, or
      personal path is tracked.
- [ ] Produce SBOM and SHA-256 checksums.

### V61C-1203 — Open and validate the release PR

- [ ] Create the release branch from reviewed `origin/main`.
- [x] Include candidate manifests and complete known limitations.
- [ ] Require human review and exact-head remote CI.
- [x] Keep the verdict `EVIDENCE_READY` before merge.
- [ ] Merge only after explicit owner approval.

### V61C-1204 — Generate final acceptance evidence

- [ ] Resolve the immutable merge and tag commits.
- [ ] Verify package, frontend, CLI, image, docs, and tag versions.
- [ ] Generate final manifest from GitHub PR/review/merge/CI state.
- [ ] Run the canonical validator in a clean checkout.
- [ ] Require final validator verdict `ACCEPTED`.

### V61C-1205 — Publish the stable release

- [ ] Obtain explicit owner approval to create and push the annotated tag.
- [ ] Create the GitHub Release from the accepted tag.
- [ ] Upload final evidence, test summary, SBOM, demo run, and checksums.
- [ ] Re-download and validate every release asset.
- [ ] Verify demo, release, CI, PR, tag, manifest, and repository state.
- [ ] Change repository visibility only with separate explicit owner approval.

### Final release exit gate

- [ ] Every phase R0–R12 is validator-confirmed `ACCEPTED`.
- [ ] No mandatory task remains unchecked.
- [ ] Final compliance manifest validates after release download.
- [ ] All ten original audit findings are closed by runtime and side-effect
      evidence.
- [ ] AOA-11 and AOA-12 publication/production requirements are accepted.
- [ ] No direct `PR_READY`, direct-to-main delivery, synthetic metric, simulated
      side effect, or evidence override remains.
- [ ] Current known limitations are explicit.
- [ ] The exact phrase “supervised-production-ready stable release” appears
      only after this gate passes.

---

## 8. Phase Dependency Map

```text
R0  Truth reset and immutable baseline
 |
R1  Packaging, version, imports, migrations
 |
R2  Canonical evidence and reviewed delivery
 |
R3  ActionGateway and PR_READY integrity
 |
R4  Durable Loop runtime and lifecycle
 |
R5  Atomic runner/worktree/path coordination
 |
R6  Real Light Swarm
 |
R7  Governed Deep Swarm
 |
R8  Real operational loops and connectors
 |
R9  Observed comparative evaluation
 |
R10 Production hardening and operability
 |
R11 GPU-free demo and public portfolio readiness
 |
R12 Final regression and stable publication
```

R10 security/observability work may begin after R3, but its final acceptance
depends on R4–R9. R11 visual work may begin with a schema prototype after R6,
but published demo evidence must be regenerated after R10.

## 9. Recommended Branch Sequence

```text
audit/v61-truth-reset
fix/v62-package-version-imports
fix/v62-evidence-release-truth
fix/v62-pr-ready-action-gateway
feat/v62-loop-runtime
feat/v62-resource-coordination
feat/v62-light-swarm-runtime
feat/v62-deep-swarm-runtime
feat/v62-operational-loops
test/v62-observed-evaluation
hardening/v62-production-readiness
docs/v62-demo-portfolio
release/v6.2.0
```

Do not create all branches at once. Each branch starts from the reviewed merge
of its predecessor.

## 10. Final Compliance Scorecard

| Area | Mandatory proof | Stable requirement |
| --- | --- | --- |
| Release truth | Validator-generated final manifest downloaded from release | `ACCEPTED` |
| Delivery | Reviewed PR, merge, protected main, exact-head CI | No direct-main substitute |
| Versioning | One version across packages, CLI, docs, tag, assets | Exact match |
| Imports/install | Clean wheel install and independent import matrix | Windows and Linux pass |
| `PR_READY` | Typed evidence, independent checker, pre-PR gate | One transition only |
| Safety | All mutation kinds cross ActionGateway | Zero bypasses |
| Loop runtime | Cron/interval/manual/external, restart, cascade kill | Durable E2E pass |
| Resources | Atomic runner/path leases, fencing, renewal, deadlock handling | Concurrent pass |
| Light Swarm | Real governed worker attempts and artifacts | Controlled E2E accepted |
| Deep Swarm | Governed dynamic nodes and recovery | Experimental unless measured |
| Operational loops | Real controlled issue/CI/review workflows | Three contracts pass |
| Benchmark | Persisted same-corpus observations | No synthetic values |
| Security | Threat model, auth, scans, secret redaction, adversarial tests | Blocking gates pass |
| Operability | Metrics, logs, health, backup, recovery, failure injection | Runbook verified |
| Demo | CPU-only evidence replay, video, static interactive path | No GPU/install needed |
| Publication | Secret/history/license review and owner approval | Public claims truthful |

## 11. Explicit Non-Goals

- Auto-merge or unattended deployment.
- Unlimited agent spawning or unbounded graph expansion.
- Self-modifying LocalForge.
- Claiming autonomous conflict resolution.
- Building a custom terminal or renderer.
- Adding providers solely for marketing breadth.
- Requiring a GPU for core operation or demonstration.
- Hiding missing measurements by substituting zero.
- Weakening tests, gates, or evidence requirements to preserve the V6.1 claim.
- Rewriting or moving the historical `v6.1.0` tag.
- Treating a green unit-test suite as proof of unexecuted external side effects.
