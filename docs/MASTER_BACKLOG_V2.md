# LocalForge OS - MASTER_BACKLOG_V2.md

> Version: 0.2
> Status: Architecture recovery backlog after HP 12C E2E failure analysis
> Companion documents: `LocalForge_OS_PRD.md`, `MASTER_BACKLOG.md`,
> `docs/e2e/HP12C_E2E_RUN_REPORT.md`
> Required root document: `CHANGELOG.md`
> Runtime model strategy: API Chief Engineer for high-complexity supervision,
> local models for bounded low/medium-risk execution.

---

## 0. Why This Backlog Exists

The V1 implementation proved that LocalForge can run unattended, create tasks,
route local models, isolate worktrees, write artifacts, validate tests, fail
safe, and expose review surfaces. The HP 12C E2E also proved that the current
architecture does not reliably complete a medium 31-task project with only local
small/medium models.

The repeated failure pattern was not one missing helper. It was architectural:

- agents invented incompatible module names and package layouts;
- generated tests and production code disagreed on public APIs;
- syntax debris survived model generation and repair;
- local repair attempts could not reliably fix semantic failures;
- more retries increased cost/time without convergence;
- more deterministic alias shims did not converge and sometimes worsened the
  distribution;
- PR readiness gates became honest, but the coding loop did not become good
  enough.

V2 changes LocalForge from a swarm of mostly independent creative agents into a
contract-first engineering harness supervised by a paid large-model Chief
Engineer and executed by cheaper local workers under deterministic gates.

---

## 1. Operating Principles

### 1.1 Chief Engineer Is Expensive and Scarce

The Chief Engineer is the OpenRouter model configured through:

- `OPENROUTER_MODEL`
- `OPENROUTER_API_KEY`

Current intended model: `minimax/minimax-m3`.

The Chief Engineer must be used only when the task requires global reasoning,
architectural consistency, hard debugging, or final review. It must not be used
as a bulk code generator for simple file edits.

### 1.2 Economy-First API Policy

Every paid API call must have:

- a reason code;
- a maximum token budget;
- a compact input bundle;
- a required structured output schema;
- an audit event with estimated input/output tokens and cost;
- a deterministic fallback or safe terminal state when budget is exhausted.

Default rule: local deterministic checks and local models run first; paid API is
called only after the harness proves the decision is above local-model grade.

### 1.3 Contract-First Execution

No task should start from an unconstrained prompt like "implement this feature".
Every task must receive:

- allowed file scope;
- expected public APIs;
- forbidden imports/dependencies;
- canonical test command;
- dependency contracts;
- acceptance criteria;
- reviewer checklist.

If a task needs a new module/API outside the contract, it must produce a contract
change request for Chief Engineer approval before writing implementation code.

### 1.4 Local Models Are Workers, Not Architects

Local models may implement bounded changes, generate simple docs, summarize
logs, or perform mechanical fixes. They must not invent architecture, public
module layout, dependency graph, or cross-task test strategy.

### 1.5 Verifiers Are Deterministic

Correctness gates must not depend on model opinion. The harness must use tests,
syntax checks, import graph checks, public API checks, dependency policy, visual
checks, and diff checks before asking any model to judge readiness.

---

## 2. Target Role Model

| Role | Primary model tier | Responsibilities | Must not do |
| --- | --- | --- | --- |
| Chief Engineer | OpenRouter API large model | PRD interpretation, architecture, contracts, task slicing, hard failure triage, final review, escalation decisions | Bulk simple coding, repeated log summarization, formatting |
| Architect | Chief Engineer | System design, module boundaries, dependency graph, interface freeze | Write feature code directly unless needed for canonical scaffold |
| Planner | Chief Engineer for first plan, local for trivial replans | Split PRD into tasks with dependencies and risk classes | Invent implementation APIs after contract freeze |
| Specifier | Chief Engineer for high-risk tasks, local for low-risk | Produce per-task contract packets | Expand scope beyond task contract |
| Coder | Local medium model by default; Chief Engineer only for high-risk patches | Implement within allowed files and APIs | Change public contract without approval |
| Tester | Local medium model plus deterministic gates | Write/maintain task tests when permitted | Rewrite canonical tests during repair |
| Fixer | Local first, Chief Engineer for classified hard failures | Repair production code according to failure class | Blind rewrite of tests or architecture |
| Reviewer | Chief Engineer for PR_READY gate | Review diff against contract, safety, tests, maintainability | Approve without deterministic evidence |
| PRWriter | Local small model | Summaries, changelog snippets, PR descriptions | Decide correctness |
| Safety Auditor | Local deterministic + local small model summaries | Policy checks, command/file risk summaries | Override Safety Kernel |

---

## 3. Model Routing Policy

### 3.1 Complexity Classes

| Complexity | Examples | Default model |
| --- | --- | --- |
| Critical | PRD architecture, public API contract, failing integration repair, final PR review | Chief Engineer via OpenRouter |
| High | financial algorithms, cross-module refactor, visual fidelity strategy, dependency redesign | Chief Engineer, with optional local draft |
| Medium | single-module implementation under frozen API, focused tests, fixture cleanup | `granite4.1:8b` or configured local medium model |
| Low | docs, summaries, changelog draft, task labels, simple mechanical edits | `nemotron-3-nano:4b` or configured local small model |
| Local exploratory | cheap draft before paid call | local model only, output treated as untrusted draft |

### 3.2 API Call Reason Codes

Every Chief Engineer call must use one reason code:

- `ARCHITECTURE_PLAN`
- `CONTRACT_FREEZE`
- `TASK_RISK_CLASSIFICATION`
- `CONTRACT_CHANGE_REVIEW`
- `HARD_FAILURE_TRIAGE`
- `SEMANTIC_REPAIR_PLAN`
- `FINAL_PR_REVIEW`
- `E2E_RETROSPECTIVE`

Calls without one of these reason codes are rejected.

### 3.3 Paid Call Input Limits

Default bundle limits:

- PRD summary: 2,000 tokens;
- contract excerpt: 2,000 tokens;
- current diff summary: 2,000 tokens;
- failing output excerpt: 1,500 tokens;
- relevant file snippets: maximum 5 files, 1,200 tokens each;
- previous attempts summary: 1,000 tokens.

The harness may send larger context only when the reason code is
`ARCHITECTURE_PLAN`, `CONTRACT_FREEZE`, or `E2E_RETROSPECTIVE`, and it must
record why the larger context is necessary.

---

## 4. Backlog Index

| Phase | Title | Primary Outcome |
| --- | --- | --- |
| 31 | OpenRouter Chief Engineer Provider | Secure API model access with economy controls |
| 32 | Cost Ledger and Token Budgeting | Every paid call is budgeted, audited, and capped |
| 33 | Contract-First PRD Compiler V2 | PRD imports produce frozen architecture contracts |
| 34 | Chief Engineer Planning Gate | Large model approves architecture before tasks run |
| 35 | Task Contract Packets | Every task receives allowed files, APIs, tests, and risk |
| 36 | Local Worker Capability Router | Local models execute only tasks within capability class |
| 37 | Deterministic Contract Verifier | Syntax, imports, APIs, deps, tests, and diff gates |
| 38 | Failure Classifier and Repair Playbooks | Repairs route by failure class instead of generic retry |
| 39 | Contract Change Request Workflow | Agents cannot invent architecture silently |
| 40 | Integration Branch Validator | PRs are tested individually and as an accumulated stack |
| 41 | Chief Engineer Final PR Review | PR_READY requires deterministic evidence plus large-model review |
| 42 | Visual Fidelity Gate | UI tasks require snapshot/reference validation |
| 43 | E2E Benchmark Harness V2 | Repeatable scoring for autonomy, cost, quality, and recovery |
| 44 | HP 12C E2E Rebuild Under V2 | Re-run the acceptance project with contract-first architecture |
| 45 | Production Readiness and Policy Defaults | Safe defaults for real paid/local hybrid unattended use |

---

## Phase 31 - OpenRouter Chief Engineer Provider

### Goal

Add a first-class provider for OpenRouter-backed large models and expose it as a
special Chief Engineer execution tier.

### Deliverables

- `OpenRouterProvider` using OpenAI-compatible API semantics.
- `.env` loading for `OPENROUTER_MODEL` and `OPENROUTER_API_KEY`.
- Config section for `chief_engineer`.
- Model route support for Chief Engineer roles.
- Tests using mocked HTTP responses; never require real credits in unit tests.

### Acceptance Criteria

- API key is never logged or written to artifacts.
- Missing key fails with a clear setup error only when Chief Engineer is needed.
- Local-only workflows still run without OpenRouter credentials.
- Provider supports request timeout, retry policy, and structured JSON output.

---

## Phase 32 - Cost Ledger and Token Budgeting

### Goal

Make paid model usage measurable, capped, and reviewable.

### Deliverables

- Persistent `model_call_ledger` table.
- Per-run and per-task token/cost budgets.
- Budget enforcement before paid calls.
- CLI/API views for estimated spend.
- Redaction-safe audit artifacts for paid calls.

### Acceptance Criteria

- Every Chief Engineer call records reason code, model, prompt size estimate,
  output size estimate, duration, success/failure, and estimated cost.
- A run can be configured with `max_paid_calls`, `max_paid_input_tokens`,
  `max_paid_output_tokens`, and `max_paid_usd`.
- Budget exhaustion causes a safe terminal state with actionable summary.

---

## Phase 33 - Contract-First PRD Compiler V2

### Goal

Replace task-only PRD import with architecture-aware PRD compilation.

### Deliverables

- Architecture contract document generated from PRD.
- Module map with approved packages/files.
- Public API registry.
- Dependency graph.
- Canonical test strategy.
- Risk classification per task.

### Acceptance Criteria

- A medium PRD import produces both tasks and a project contract.
- Tasks reference contract IDs, not free-form invented APIs.
- The compiler marks ambiguous architecture as needing Chief Engineer review
  before execution.

---

## Phase 34 - Chief Engineer Planning Gate

### Goal

Use the large model once early to prevent downstream local-model divergence.

### Deliverables

- `ARCHITECTURE_PLAN` prompt template.
- Compact PRD summary builder.
- Chief Engineer architecture approval artifact.
- Contract freeze command.
- Rejection path that asks for smaller task slices or clearer APIs.

### Acceptance Criteria

- No unattended run can start medium/high-risk tasks without a frozen contract.
- Chief Engineer output is strict JSON plus a short human-readable summary.
- The model is instructed to minimize output and avoid implementation details
  unless they define public contracts.

---

## Phase 35 - Task Contract Packets

### Goal

Give each worker a small, exact packet instead of broad context.

### Deliverables

- Per-task packet renderer.
- Allowed file list.
- Required exports/imports.
- Forbidden dependencies.
- Test commands.
- Repair boundaries.
- Definition of done.

### Acceptance Criteria

- Local models never receive the whole PRD by default.
- Each packet fits within the configured token budget.
- Attempts to write outside allowed files are blocked or escalated as contract
  change requests.

---

## Phase 36 - Local Worker Capability Router

### Goal

Route work to local models only when the task is inside their proven capability
class.

### Deliverables

- Capability matrix for local models.
- Risk score based on task type, dependency count, file count, and previous
  failure class.
- Automatic escalation rules to Chief Engineer.
- Local draft mode for cheap first-pass ideas.

### Acceptance Criteria

- High-risk architecture, cross-module, visual fidelity, and semantic repair
  tasks do not default to local models.
- Low-risk tasks can complete without paid API calls.
- Routing decisions are logged with explicit rationale.

---

## Phase 37 - Deterministic Contract Verifier

### Goal

Catch the failure classes observed in the HP 12C E2E before PR readiness.

### Deliverables

- Python syntax verifier.
- Import graph verifier.
- Public API/export verifier.
- Forbidden dependency verifier.
- Test command verifier.
- Diff/file-scope verifier.
- Contract drift verifier.

### Acceptance Criteria

- Missing imports are diagnosed against the approved module map.
- API mismatches report exact missing symbol/signature.
- Forbidden packages such as undeclared SciPy fail before repair.
- Verifier output is structured by failure class.

---

## Phase 38 - Failure Classifier and Repair Playbooks

### Goal

Replace generic repair prompts with targeted repair strategies.

### Deliverables

- Failure classes:
  - `SYNTAX_ERROR`
  - `MISSING_IMPORT`
  - `PUBLIC_API_MISMATCH`
  - `FORBIDDEN_DEPENDENCY`
  - `SEMANTIC_TEST_FAILURE`
  - `VISUAL_MISMATCH`
  - `TIMEOUT`
  - `EMPTY_DIFF`
  - `CONTRACT_DRIFT`
- Deterministic repair playbooks for simple classes.
- Chief Engineer escalation for hard semantic and architecture classes.

### Acceptance Criteria

- A missing import first checks the contract, not the LLM.
- A forbidden dependency produces a dependency-free repair request.
- Repeated failures escalate with a compact evidence bundle instead of another
  blind retry.

---

## Phase 39 - Contract Change Request Workflow

### Goal

Prevent agents from silently inventing architecture.

### Deliverables

- Contract change request artifact type.
- Chief Engineer approval/rejection path.
- CLI/API review surface for pending contract changes.
- Automatic task blocking while contract change is unresolved.

### Acceptance Criteria

- New modules, new public exports, new dependencies, and test strategy changes
  require approval.
- Approved changes update the contract and downstream task packets.
- Rejected changes produce repair guidance.

---

## Phase 40 - Integration Branch Validator

### Goal

Validate that independently ready PRs work together.

### Deliverables

- Temporary integration branch/worktree.
- Ordered application of PR_READY task branches.
- Accumulated test run.
- Conflict and regression reporting.

### Acceptance Criteria

- A task can be individually green but blocked from final review if it breaks
  integration.
- Integration failures are classified and routed to repair.
- Integration branch is disposable and never merged automatically.

---

## Phase 41 - Chief Engineer Final PR Review

### Goal

Require high-quality review before a task becomes truly PR_READY.

### Deliverables

- `FINAL_PR_REVIEW` Chief Engineer prompt.
- Minimal review bundle builder:
  - task contract;
  - diff summary;
  - deterministic verifier results;
  - test output summary;
  - risk notes.
- Review outcome schema.

### Acceptance Criteria

- PR_READY requires deterministic gates plus Chief Engineer approval for
  medium/high-risk tasks.
- Low-risk docs-only tasks may use local review if policy allows.
- Review output is short, structured, and auditable.

---

## Phase 42 - Visual Fidelity Gate

### Goal

Make UI fidelity objectively testable instead of relying on textual claims.

### Deliverables

- Reference image attachment handling.
- Screenshot/render command configuration.
- Pixel/layout similarity metrics where practical.
- Chief Engineer visual review only after deterministic screenshot evidence.
- Artifact storage for before/after/reference images.

### Acceptance Criteria

- Visual tasks cannot be PR_READY without rendered evidence.
- The Chief Engineer receives images or compact visual metrics, not vague
  descriptions.
- Visual mismatch is a first-class failure class.

---

## Phase 43 - E2E Benchmark Harness V2

### Goal

Score autonomy and quality repeatably.

### Deliverables

- Benchmark run manifest.
- Metrics:
  - task count;
  - PR_READY count;
  - FAILED_SAFE count;
  - human interventions;
  - paid calls;
  - estimated cost;
  - repair attempts;
  - failure classes;
  - wall-clock time;
  - integration pass/fail.
- Report generator.

### Acceptance Criteria

- `Funciona bem` requires all acceptance scenarios and benchmark thresholds.
- Cost is part of the score.
- Regression reports compare against prior runs.

---

## Phase 44 - HP 12C E2E Rebuild Under V2

### Goal

Re-run the HP 12C Platinum acceptance test using the new hybrid architecture.

### Deliverables

- Recompiled PRD under contract-first compiler.
- Chief Engineer architecture contract.
- Frozen task packets.
- Local worker execution under routing policy.
- Integration validation.
- Visual fidelity evidence.
- Updated `docs/e2e/HP12C_E2E_RUN_REPORT.md`.

### Acceptance Criteria

- Around 30 tasks execute without manual intervention.
- No task invents unapproved architecture.
- PR artifacts are reviewable.
- Integration branch passes canonical tests.
- Visual task has rendered evidence against the reference image.
- Final rating can only be `Funciona bem` if all five scenarios in
  `docs/E2E_ACCEPTANCE_PLAN.md` pass.

---

## Phase 45 - Production Readiness and Policy Defaults

### Goal

Make hybrid paid/local autonomy safe enough for real project trials.

### Deliverables

- Default economy-first policy.
- Spending caps in sample config.
- `.env.example` without secrets.
- OpenRouter troubleshooting docs.
- Safe fallback behavior when paid API is unavailable.
- Frontend cost/Chief Engineer visibility.

### Acceptance Criteria

- New users can enable OpenRouter without exposing secrets.
- The UI shows paid-call usage and remaining run budget.
- A run cannot accidentally spend unbounded credits.
- Local-only mode remains available.

---

## 5. Revised Definition of "Funciona Bem"

LocalForge V2 is **Funciona bem** only when:

- the PRD is compiled into a frozen architecture contract;
- Chief Engineer approves the contract;
- local workers execute only bounded task packets;
- deterministic contract gates pass;
- repair playbooks resolve ordinary failures without human intervention;
- hard failures escalate to Chief Engineer with compact evidence;
- final PRs are reviewed by deterministic gates and Chief Engineer;
- integration branch validates the accumulated work;
- paid usage stays within configured budget;
- artifacts let a human understand exactly what changed, what passed, what
  failed, and what it cost.

---

## 6. Non-Goals

- Do not make cloud models the default for every action.
- Do not allow unbounded OpenRouter spending.
- Do not trust LLM review without deterministic evidence.
- Do not let local models invent architecture.
- Do not hide failed tasks behind PR_READY artifacts.
- Do not optimize for passing the HP 12C E2E through hardcoded project-specific
  shims. The HP 12C E2E should validate the architecture, not become the
  architecture.

