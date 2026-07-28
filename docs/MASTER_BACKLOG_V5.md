# LocalForge OS — Open Source Readiness Backlog

> Version: 0.5
> Status: In progress
> Date: 2026-07-12
> Continues: `MASTER_BACKLOG.md` and V2–V4 backlogs

## Objective

Prepare LocalForge OS for credible public use as an open-source, economy-aware
software-engineering control plane. The release must not depend on benchmark-specific
runtime behavior or unverifiable product claims.

## Release contract

The V5 release is complete only when:

- the runtime contains no HP 12C, Pomodoro, or SprintBoard implementation logic;
- benchmark preflight checks inspect real local services;
- V4 acceptance requires persisted routing contracts and reproducible evidence;
- provider fallback distinguishes availability failures from configuration/auth failures;
- the PRD, README, changelog, and active backlog describe one current architecture;
- the Python package installs with a `localforge` console entry point;
- contributor, security, support, and conduct policies exist;
- backend and frontend responsibilities have documented modular boundaries;
- targeted tests for changed contracts pass before a release candidate is tagged.

## Phases

### Phase 70 — Runtime and benchmark integrity

- Remove benchmark-domain scaffolds and compatibility code from the pipeline.
- Remove obsolete tests that assert benchmark-specific runtime behavior.
- Replace simulated Docker/Ollama preflight checks with real diagnostics.
- Persist and report routing-contract evidence.
- Reject V4 acceptance when routing evidence is absent.

### Phase 71 — Provider reliability and routing evidence

- Fall back only on timeout, connection, rate-limit, and provider-server failures.
- Surface authentication, billing, validation, and configuration failures directly.
- Test provider attribution and fallback decisions.
- Keep local/API calls visible in the cost ledger.

### Phase 72 — Product contract and documentation alignment

- Declare V5 as the active product direction.
- Reconcile local-first privacy with API-led economy routing.
- Distinguish verified evidence, historical evidence, and future targets.
- Document architecture boundaries and benchmark methodology.

### Phase 73 — Packaging and first-run experience

- Add standards-based Python package metadata and console entry point.
- Provide installation, quickstart, development, and troubleshooting paths.
- Add a non-destructive smoke command that does not require paid credentials.

### Phase 74 — Open-source governance

- Add contributing, security, code-of-conduct, support, and roadmap documents.
- Define issue/PR expectations and evidence requirements.
- Keep secrets, generated workspaces, and runtime databases out of source control.

### Phase 75 — Modular maintainability

- Extract provider construction and routing policy from the pipeline engine.
- Split API route groups without changing public endpoints.
- Split the frontend shell into navigation, project state, and feature views.
- Add frontend unit-test infrastructure for extracted behavior.

### Phase 76 — Reproducible comparative evaluation

- Run unseen tasks against frontier-only, economy-API-only, local-only, and hybrid lanes.
- Use identical acceptance tests and record cost, time, retries, and human intervention.
- Publish manifests and hashes without committing disposable worktrees or secrets.
- Do not claim savings or quality parity until the comparative gate passes.

### Phase 77 — Open-source release candidate

- Run targeted tests, then the nearest backend/frontend suites.
- Require explicit approval before a full regression suite.
- Verify package build/install in a clean environment.
- Produce release notes with honest limitations and deferred work.
