# ForgeOS

ForgeOS is a local-first, supervised software-engineering control plane. It
turns a Markdown PRD into bounded task contracts, isolated worktree changes,
tests, reviews, risk and cost evidence, and a human-reviewable `PR_READY`
result.

It is not a claim of infallible autonomous coding, automatic deployment, or
production multi-tenancy. The Scheduler, ActionGateway, Safety Kernel,
validators, and release policy remain authoritative over model proposals.
Human product acceptance remains the final step even when release promotion is
configured for full access.

## The reference contract

The repository-level claims below are designed to be auditable. The canonical
reference run is the small ForgeLedger PRD:

- PRD: [`docs/PRD_REFERENCE_FORGEOS.md`](docs/PRD_REFERENCE_FORGEOS.md)
- runner: [`scripts/run_benchmark_reference_forgeos.py`](scripts/run_benchmark_reference_forgeos.py)
- report: [`docs/e2e/reference/forgeos_reference_report.md`](docs/e2e/reference/forgeos_reference_report.md)
- metrics: [`docs/e2e/reference/forgeos_reference_metrics.json`](docs/e2e/reference/forgeos_reference_metrics.json)
- manifest: [`docs/e2e/reference/manifest.json`](docs/e2e/reference/manifest.json)
- feature audit: [`docs/REFERENCE_FEATURE_AUDIT.md`](docs/REFERENCE_FEATURE_AUDIT.md)

The benchmark is `ACCEPTED` only when all imported tasks are `PR_READY`, the
run and lifetime goal are `COMPLETED`, all independent product and canonical
fixture tests pass, all model calls use OmniRoute, and the report can trace
each claim to SQLite, control-plane, Harness, safety, skill, and artifact
evidence. The generated product is created only inside a benchmark worktree by
ForgeOS and the configured LLM; the runner never patches product source or
tests after execution.

Run it from PowerShell after configuring a reachable OmniRoute gateway:

```powershell
$env:DEEPEVAL_DISABLE_DOTENV = "1"
$env:PYTHONPATH = "backend"
$env:LOCALFORGE_OMNIROUTE_STRUCTURED_TIMEOUT = "45"
$env:LOCALFORGE_BENCHMARK_RUN_TIMEOUT = "1800"
python scripts/run_benchmark_reference_forgeos.py
```

The reference command uses a shorter primary-route timeout so a slow upstream
falls through the finite OmniRoute ladder, and a longer bounded run budget for
the five-task recovery benchmark.

The report distinguishes a real `ACCEPTED` run from a provider-blocked or
partially completed run. `PR_READY` remains review evidence, not merge
permission. The stable files above are refreshed only after an accepted run;
each accepted execution also keeps an immutable timestamped evidence directory.

### Full trace and module-usage benchmark

For a complete, timestamped audit of the README contract, run:

```powershell
python scripts/run_benchmark_readme_trace.py
```

This benchmark records the PRD intake, pre-approved planning, real CLI
execution, OmniRoute calls, Harness/control-plane artifacts, SQLite
postconditions, DeepCode continuity gates, Context7, security, frontend,
Docker/Kubernetes/Redis/Helm probes, and a redacted ordered JSONL trace. It
also profiles Python imports/calls under `backend/localforge` and `scripts`,
classifying each tracked path as `USED`, `PARTIAL`, `BROKEN`, or `UNUSED` with
a recommendation. Results are written to
`.localforge/artifacts/readme-trace-benchmark/run-<timestamp>/`, including
`manifest.json`, `run_trace.jsonl`, `readme_compliance_report.md`, and
`module_inventory_report.md`.

Latest accepted evidence: `run-20260809T001429Z`, with 12/12 required README
claims and 9/9 DeepCode continuity claims passing.

The benchmark is intentionally pre-approved and unattended for audit
repeatability; that setting does not convert a blocked task into a successful
product run. Optional Kubernetes profile application and Helm checks remain
`NOT_PROVEN` unless those tools/services are explicitly available.

### HP12C benchmark readiness

The HP12C Platinum sample is a stress benchmark for autonomous delivery, not a
proof that every PRD is already delivered autonomously. The two long runs
reported by the Product Owner consumed approximately 25 hours and 17 hours;
repository evidence also records provider/Chief Engineer timeouts, missing
materialized visual tests, SQLite heartbeat contention, post-merge visual and
security failures, and incomplete repair routing.

Do not repeat the full benchmark until the prioritized readiness backlog in
[docs/pendencias_correcoes.md](docs/pendencias_correcoes.md) is complete. The release bar is deliberately
stricter than PR_READY: full_access must merge every task, run independent
Security Auditor and interface-level Tester/Product Acceptance gates, return
non-compliant work to the correct correction stage, and preserve a complete
trace from PRD intake through the final product.

## What ForgeOS provides

### Model gateway and economy controls

- Runtime model traffic uses an explicit provider lane configured in
  `.localforge/config.yaml` or `.env`: the local OmniRoute-compatible gateway
  remains the economy-first route for ordinary agents, while OpenRouter and
  NVIDIA are supported direct API lanes.
- `OPENROUTER_PAID_MODEL` plus `OPENROUTER_API_KEY` select the paid OpenRouter
  route as the default for Chief Engineer, critical repair, and final
  validation. `OPENROUTER_FREE_MODEL` and `NVIDIA_LLM_MODEL` are bounded free
  direct-provider fallback lanes. `OPENROUTER_MODEL` remains a compatibility
  alias for the paid model.
- An explicit `LOCALFORGE_CHIEF_PROVIDER` always wins. For example, an
  explicitly selected OmniRoute Chief route can use the paid OpenRouter lane
  and then the configured free routes after transient failures.
- Preflight probes the primary route and, after a transient outage, the
  configured fallback route. Authentication, billing, model-selection, and
  contract errors remain visible instead of being hidden by fallback.
- Provider circuits open after repeated transient failures for a finite
  cooldown, preventing an unavailable route from consuming the entire Run.
  Every selected provider, fallback decision, retry, and estimated cost is
  recorded in the model-call ledger.
- Structured Chief Engineer calls have a configurable bounded timeout through
  `LOCALFORGE_OMNIROUTE_STRUCTURED_TIMEOUT` (30-600 seconds; default 120).

### PRD-to-PR evidence pipeline

The real pipeline is:

`PRD -> dependency-aware tasks -> frozen contracts -> worktree -> bounded agent turn -> tests -> repair/review -> artifacts -> PR_READY`

Task contracts can constrain allowed files, required APIs, canonical test
commands, acceptance behaviors, dependencies, seniority, risk, and required
release artifacts. The domain database owns projects, tasks, runs, artifacts,
costs, and pull-request evidence.

### Release promotion modes

ForgeOS separates task completion from release promotion. `PR_READY` means that
the branch has reviewable engineering evidence; it does not by itself merge or
publish the product.

The default mode pauses after every task reaches `PR_READY` and creates a
durable approval request:

```yaml
release:
  promotion_mode: human_approval
  target_branch: main
  post_merge_agents: [Tester, SafetyAuditor]
```

The operator can inspect and approve the release with:

```powershell
localforge release status
localforge release approve --run-id <id> --approver-id <human-id>
```

The opt-in `full_access` mode merges the `PR_READY` task branches into a clean
local target branch, then runs the Tester and SafetyAuditor commands through
the Safety Kernel. A merge conflict, dirty target, failed test, or security
finding stops the release and preserves evidence for human review:

```yaml
release:
  promotion_mode: full_access
  target_branch: main
  post_merge_agents: [Tester, SafetyAuditor]
```

This mode automates repository promotion and technical gates only. It does not
claim that a human has accepted the product, deployed it, or verified its UX.

### Typed Agent Harness

`AgentHarness` is shared by built-in roles, the legacy runtime, Chief Engineer
repair calls, and persisted user-created skill/agent profiles. It provides:

- typed method contracts with deterministic `predict` and bounded `code_act`
  strategies;
- required and optional context blocks with priority-based compaction;
- schema validation and a finite retry budget;
- parent/root spans, lifecycle events, tool-call hooks, and call evidence;
- model output as an observation or proposal until ForgeOS validators accept it.

The Harness is inspired by Prime Agent's durable harness state and NVIDIA's
typed object-oriented agent methods, but retains ForgeOS's local safety and
authority boundaries.

### Durable Harness State and subagents

Project-scoped Harness State stores supplemental prompts, memories, skill
manifests, and subagent specifications in locked atomic JSON with rollback
snapshots and refinement events. Base/system prompts are protected from
refinement. Subagents have explicit parentage, depth, turns, token budgets,
allowed actions, terminal states, and durable lifecycle records.

This gives ForgeOS recoverable context across turns without importing an
untrusted entrypoint or relying on chat history as the source of truth.

### Engineering continuity and reference-driven execution

The ForgeOS continuity layer makes the engineering lifecycle durable across
API, CLI, and UI sessions:

- `EngineeringSession`, `EngineeringGoal`, and immutable ordered
  `EngineeringTurn` records survive process restarts and preserve idempotency;
- pause, resume, cancel, steer, goal revision, turn budgets, and
  `ExecutionProfile` snapshots are audited and tenant-scoped;
- model discovery and probes are recorded through the OmniRoute gateway, with
  sanitized failures and capabilities instead of silent fallback;
- Skills are bound to admitted Turns by canonical manifest digest, version,
  origin, and frozen snapshot, so replay does not resolve mutable “latest” data;
- Automations reuse the engineering runtime and persist trigger, goal/profile,
  budget, idempotency, approval, and evidence state;
- Markdown/text references become redacted, hashed, section/line-addressable
  chunks. Lexical CodeRAG returns citations, quarantines prompt-injection
  sources, records a `ReferenceDecision`, and can freeze a cited
  `ProductBlueprint` before PRD compilation;
- local process cancellation records the active Windows/POSIX tree strategy
  and explicitly reports `PROVEN` or `NOT_PROVEN` isolation evidence.

The continuity contract and its document-to-product benchmark are defined in
[`docs/plano_deepcode.md`](docs/plano_deepcode.md). The benchmark is designed
to prove these additions without making ForgeOS depend on DeepCode or on a
second scheduler/provider path.

### Long-running control plane

The LoopX-inspired control plane is a separate deterministic kernel for:

- stable project-lifetime goals and reconnectable state paths;
- server-owned todo frontier, claims, leases, pause/resume, and bounded worker
  ticks;
- typed receipts with changed files, checks, content hashes, and idempotency
  keys;
- quota for turns, attempts, cost, and wall time;
- human gates, provider/CI/review/host/quota signals, repair handoffs, and
  review-packet projections.

The control plane decides whether a bounded turn may run. It never executes a
model, shell command, or file write and is not a second task database.

### Skills and engineering workflow

ForgeOS skills are declarative, project-scoped manifests selected from task
context. Built-ins include Python/FastAPI/React guidance, security and E2E
release testing, plus native equivalents of three high-value engineering
workflows from Matt Pocock's public skills repository:

- `grill-with-docs`: identify ambiguity, shared terminology, and ADR-ready
  decisions before implementation;
- `to-tickets`: compile an approved specification into dependency-aware,
  bounded tracer-bullet tasks;
- `tdd`: require observable acceptance behavior and preserve assertions through
  repair.

User-created skills can persist strategy, context budget, retry budget,
permissions, dependencies, and expected artifacts. Python entrypoints are
validated as manifests and are not imported automatically; execution still
requires an allowlisted ForgeOS handler and the Safety Kernel.

### Safety, memory, and observability

- ActionGateway and Safety Kernel enforce role, path, command, network, Git,
  protected-file, and human-approval rules.
- Worktree and path leases bound concurrent edits and preserve isolation.
- Graphify builds a deterministic local AST/file graph; MemPalace stores
  project-scoped JSON memory; RuleSynthesizer accepts sanitized,
  evidence-backed instruction updates.
- Context7 MCP discovery, Redis cache/pub-sub/lock primitives, OpenTelemetry
  timeline events, HITL approvals, and Helm templates are available as
  optional integration surfaces. They are not silently treated as live
  dependencies of the reference benchmark.
- The frontend exposes a single portfolio-oriented Chat + Pipeline workspace:
  document upload and Scrum Master response sit below a five-lane delivery view
  (Backlog, execution/correction, PR_READY/Merge, Security Auditor, and final
  Tester). Post-merge lifecycle traces are visible in the same workspace, and
  non-compliant work can return to correction. Skills, memory, safety, review,
  and detailed telemetry remain available as secondary surfaces; a frontend build
  or hosted deployment is a separate release gate.

### Reintegrated reliability and operations

The current pipeline also exposes the formerly disconnected high-value
capabilities through the same governed boundaries:

- Validation failures receive normalized error fingerprints, attempt-progress
  signals, circuit-breaker evidence, and line-precise TypeScript compiler
  feedback. Repeated failures remain fail-closed and are available to the
  existing Scrum Master/Chief Engineer recovery loop.
- Light Swarm has governed dispatch, typed worker handoffs, evidence-only
  aggregation into the mechanical PR gate, restart recovery, and resource
  release. The API surfaces are `/swarms/{run_id}/dispatch`,
  `/swarms/{run_id}/nodes/{node_id}/typed-worker`,
  `/swarms/{run_id}/aggregate`, and `/swarms/{run_id}/recover`.
- Production observability emits structured JSON records and the
  `/operations/status` endpoint reports live workers, leases, queue depth,
  open circuit breakers, and model cost from the database rather than fixed
  placeholder values.
- Release promotion can optionally require the tracked-tree audit and the
  Chief Engineer semantic final review after deterministic task evidence and
  before merge. These gates are opt-in and never replace ContractVerifier,
  Tester, or SafetyAuditor.
- The full-coverage profile also runs governed CI/PR compliance, frontend
  lint/typecheck/tests/build, browser, security, recovery, and bounded load
  evidence when the corresponding local tools and cluster services exist.
- Preflight model discovery and the visual normalizer/gates remain reusable
  capabilities for selecting a verified route and validating visual work;
  neither is silently promoted to a live external dependency.
- Optional operational profiles are available through
  `/capabilities/operational-profiles` and can be selected in the release
  snapshot with `release.operational_profiles` or
  `LOCALFORGE_RELEASE_OPERATIONAL_PROFILES`. The `full_coverage` and `saas`
  profiles govern Context7, Redis, Kubernetes/Helm, GitHub draft PRs,
  tenant-scoped BYOK, security and load probes. External services are not
  started implicitly and are never reported as healthy without evidence.

The recoverable legacy archive is under [`archive/legacy/`](archive/legacy/).
It contains superseded classifiers, duplicate validators, unsafe/incomplete
preview helpers, orphaned Deep Swarm helpers, and historical benchmark/demo
scripts. The active reference, readme-trace, full-coverage, and V7 mini
acceptance paths remain in `scripts/`.

## Five reference repositories

The clean-room adoption map, implementation boundaries, and evidence paths are
in [`docs/REFERENCE_FEATURE_AUDIT.md`](docs/REFERENCE_FEATURE_AUDIT.md).

- [OmniRoute](https://github.com/diegosouzapw/OmniRoute): one local gateway and
  live route discovery.
- [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent): durable
  Harness context, refinement, and bounded subagent ideas.
- [NVIDIA OO Agents](https://github.com/NVIDIA-NeMo/labs-OO-Agents): typed
  method contracts and predictable agent strategies.
- [LoopX](https://github.com/huangruiteng/loopx): durable goals, leases,
  evidence, quota, signals, and handoffs.
- [Matt Pocock skills](https://github.com/mattpocock/skills): requirement
  grilling, ticket decomposition, and observable TDD workflow guidance.

No reference repository is a runtime dependency, and no source code is copied
from those projects.

## Local setup

```powershell
Copy-Item .env.example .env
# Edit .env and set local credentials; never commit .env.
python -m localforge.cli.main init
python -m localforge.cli.main doctor
```

For the optional Compose deployment, set local values for
`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `LOCALFORGE_API_TOKEN` before:

```powershell
docker compose config
docker compose up --build
```

Default local surfaces are the frontend at `http://localhost:5173`, backend at
`http://localhost:8000`, and OmniRoute at `http://127.0.0.1:20128/v1`.

## Validation

```powershell
$env:DEEPEVAL_DISABLE_DOTENV = "1"
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
python scripts/check_release_truth.py
python scripts/check_security_scans.py
```

The reference benchmark is the authoritative proof for a current real model
run. Unit tests prove repository behavior; they do not prove upstream model
availability, Docker health, tenant isolation, Kubernetes readiness, or human
approval.

## Project status and governance

ForgeOS is source-available and actively evolving. Check
[`CHANGELOG.md`](CHANGELOG.md), [`docs/MASTER_BACKLOG.md`](docs/MASTER_BACKLOG.md),
and [`docs/MASTER_BACKLOG_V9_LOOPX_LIKE.md`](docs/MASTER_BACKLOG_V9_LOOPX_LIKE.md)
for current implementation and remaining gates. Human review remains required
before merge, deploy, publication, or any irreversible external action.
