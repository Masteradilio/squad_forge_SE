# LocalForge OS - MASTER_BACKLOG_V3.md

> Version: 0.3
> Status: API-led, economy-first commercial viability backlog
> Date: 2026-06-24
> Continues: `MASTER_BACKLOG.md` phases 1-30 and `MASTER_BACKLOG_V2.md`
> phases 31-45
> Companion documents: `LocalForge_OS_PRD.md`, `MASTER_BACKLOG.md`,
> `MASTER_BACKLOG_V2.md`, `CHANGELOG.md`

---

## 0. Why This Backlog Exists

V1 proved that LocalForge can compile PRDs into tasks, run agents, isolate
worktrees, execute validation, fail safe, and prepare PR artifacts.

V2 proved that a mostly local-model autonomous harness is not enough for
realistic software engineering work. The HP 12C validation exposed the critical
failure pattern: local models can be useful, but they are not reliable as the
primary cognitive engine for architecture, large UI rewrites, cross-file
semantic consistency, and hard recovery loops.

V3 changes the product thesis:

```text
LocalForge OS is an API-led, economy-first AI Software Engineering Squad.
```

The system uses a large API model as the Chief Engineer and Scrum Master for
high-complexity work, while local models act as scoped squad members for cheap,
bounded, verifiable work. The user is the Product Owner: they provide the PRD,
review pull requests, and accept or reject product outcomes.

This is not API-only and not local-first. It is API-led and cost-aware.

---

## 1. Product Thesis

### 1.1 Positioning

LocalForge is a software factory that turns PRDs into reviewable pull requests.
It competes economically with always-cloud agent workflows by routing only the
work that genuinely needs expensive model intelligence to the API tier.

The target promise is:

```text
Given a PRD, LocalForge plans a sprint backlog, routes tasks by complexity,
executes work in isolated worktrees, validates deterministically, attempts
bounded self-healing, and emits PRs with evidence, risk notes, and cost
benchmarks.
```

### 1.2 Commercial Value Proposition

Every run and PR should answer:

- How much did LocalForge spend on API calls?
- How many tokens were handled locally for near-zero marginal API cost?
- What would the same token workload have cost under API-only baselines?
- Which tasks were worth escalating to the Chief Engineer?
- Which local tasks actually saved money without lowering quality?

### 1.3 Non-Goals

LocalForge must not claim:

- zero human review;
- replacement of professional engineers;
- guaranteed product correctness from model output alone;
- that local models can perform arbitrary senior engineering work;
- exact cost parity with proprietary products whose internal model usage is not
  public.

Benchmarks are API-token baselines, not claims about internal billing for Codex,
Antigravity, Claude Code, Cursor, or any proprietary IDE agent.

---

## 2. Squad Architecture

| Squad concept | LocalForge role | Model tier | Responsibility |
| --- | --- | --- | --- |
| Product Owner | Human user | Human | Supplies PRD, accepts/rejects PRs, resolves product tradeoffs |
| Scrum Master + Staff Engineer | Chief Engineer | API large model | Plans sprint, freezes contracts, performs hard implementation, triages failures, reviews final PR readiness |
| Senior Developer | Coder high-risk lane | API large/medium model | Implements complex UI, architecture, cross-file changes, large rewrites |
| Developer | Coder bounded lane | Local medium model | Implements narrow files under frozen contracts |
| QA Engineer | Tester | Local medium or deterministic | Writes/runs focused tests only within allowed files |
| Bug Fixer | Fixer | Local for simple, API for hard | Repairs syntax/import/simple failures locally; escalates semantic/visual/context failures |
| Reviewer | Reviewer | API for final, local for draft | Performs final contract-aware PR review after deterministic gates |
| Release/PR Writer | PRWriter | Local small | Writes summaries, changelog drafts, PR body text |
| Safety Auditor | Safety Kernel + local small | Deterministic/local | Enforces file, command, dependency, budget, and policy constraints |

The Chief Engineer may both orchestrate and execute. This mirrors real software
squads where a senior engineer or tech lead coordinates work and also takes the
hardest tickets.

---

## 3. API-Led Economy Policy

### 3.1 Routing Principle

Use the cheapest tier that is empirically capable of the task.

The router must not assume capability from model size alone. It must use:

- historical success/failure records;
- task complexity;
- file size;
- required context;
- required visual or semantic fidelity;
- prior truncation/timeouts;
- failure class.

### 3.2 Task Seniority Classes

| Class | Default owner | Examples | Escalation rule |
| --- | --- | --- | --- |
| Chief-only | Chief Engineer API | architecture, PRD ambiguity, contract freeze, cross-module design, large UI rewrite, visual parity, hard semantic repair | Always API |
| Chief-led | Chief Engineer + local support | complex task with substeps that can be delegated | API plans/critical edits; local handles bounded subtasks |
| Local-assisted | Local medium | single-file code under frozen API, focused tests, fixture cleanup | Escalate after one hard failure or any truncation |
| Local-only | Local small/medium | summaries, changelog drafts, simple docs, mechanical changes | Fail safe if validation fails repeatedly |
| Deterministic-only | Harness | syntax, import, dependency, file scope, cost calculation, visual diff, test commands | Never ask model to decide correctness |

### 3.3 Anti-Loop Policy

A local model is immediately disqualified from continuing a task when it:

- writes placeholders like "omitted for brevity";
- truncates required files;
- times out on the same step twice;
- increases visual or test failure severity;
- changes tests to hide failures;
- edits files outside the contract;
- introduces public APIs not approved by the contract;
- produces invalid JSON/action payload twice.

After disqualification, the next attempt is Chief Engineer or safe blocker.

---

## 4. Permanent Cost Benchmark System

### 4.1 Benchmark Purpose

The benchmark system estimates what LocalForge saved compared with hypothetical
API-only execution using three provider families:

- OpenAI / Codex-style API baseline;
- Google / Antigravity-style API baseline;
- Anthropic / Claude Code-style API baseline.

These are benchmark labels only. LocalForge must not depend on Codex,
Antigravity, Claude Code, Cursor, or their internal runtimes.

### 4.2 Official Pricing Sources

The pricing registry must store source URLs and retrieval metadata.

Initial official sources:

- OpenAI API pricing: `https://openai.com/api/pricing/`
- Anthropic Claude pricing: `https://platform.claude.com/docs/en/about-claude/pricing`
- Google Gemini API pricing: `https://ai.google.dev/gemini-api/docs/pricing`

Prices change. The registry must record:

- source URL;
- retrieved_at timestamp;
- provider;
- model name;
- input price per million tokens;
- output price per million tokens;
- cache/read/write prices when applicable;
- notes about context thresholds;
- whether the value is manually entered or refreshed by scraper.

### 4.3 Initial Benchmark Model Triads

Initial values are a pricing snapshot and must be refreshable.

| Provider baseline | Large / Chief benchmark | Medium benchmark | Small benchmark |
| --- | --- | --- | --- |
| OpenAI | GPT-5.5: $5.00 input / $30.00 output per 1M tokens | GPT-5.4: $2.50 input / $15.00 output per 1M tokens | GPT-5.4 mini: $0.75 input / $4.50 output per 1M tokens |
| Anthropic | Claude Opus 4.8: $5.00 input / $25.00 output per 1M tokens | Claude Sonnet 4.6: $3.00 input / $15.00 output per 1M tokens | Claude Haiku 4.5: $1.00 input / $5.00 output per 1M tokens |
| Google | Gemini 2.5 Pro: $1.25 input / $10.00 output per 1M tokens | Gemini 2.5 Flash: $0.30 input / $2.50 output per 1M tokens | Gemini 2.5 Flash-Lite: $0.10 input / $0.40 output per 1M tokens |

### 4.4 LocalForge Actual Cost

Actual cost must include:

- paid Chief Engineer API input/output tokens;
- paid API retries;
- provider fees when available;
- optional storage/cache/search/tool costs if used;
- zero or configured amortized cost for local model calls;
- local execution wall-clock and hardware notes separately from API cost.

Local model usage should be reported as:

```text
local_model_tokens_estimated
local_model_marginal_api_cost_usd = 0
optional_local_compute_cost_usd = configurable
```

### 4.5 Per-PR Benchmark Report

Every PR artifact must include a cost table:

| Metric | LocalForge actual | OpenAI API-only | Google API-only | Anthropic API-only |
| --- | ---: | ---: | ---: | ---: |
| Large-tier equivalent cost | | | | |
| Medium-tier equivalent cost | | | | |
| Small-tier equivalent cost | | | | |
| Actual paid API calls | | | | |
| Local calls avoided | | | | |
| Estimated savings vs large | | | | |

The report must explain that API-only baselines are hypothetical token-cost
comparisons, not exact invoices for proprietary IDE agents.

### 4.6 Project-Level Cost Rollup

At product completion, LocalForge must produce:

- total LocalForge API cost;
- total local model token estimate;
- cost by role;
- cost by task;
- cost by PR;
- cost by failure/retry class;
- projected API-only cost for OpenAI, Google, Anthropic;
- savings amount and savings percentage;
- notes about benchmark source versions.

---

## 5. Backlog Index

| Phase | Title | Primary Outcome |
| --- | --- | --- |
| 46 | V3 Product Reframe | LocalForge becomes API-led AI Software Engineering Squad |
| 47 | Squad Role Model and Workflow | PO/Scrum Master/squad roles become first-class domain concepts |
| 48 | Seniority-Based Routing Engine | Tasks route by capability, not local-first ideology |
| 49 | Model Capability Registry V3 | Local and API models get empirical capability records |
| 50 | Anti-Loop Escalation Policy | Repeated local failure escalates early or blocks safely |
| 51 | Chief Engineer Execution Lane | API model implements complex tasks, not only reviews |
| 52 | Cost Source Registry | Official pricing sources are stored and refreshable |
| 53 | Competitor Benchmark Triads | OpenAI, Google, Anthropic large/medium/small baselines |
| 54 | Unified Token and Cost Ledger V3 | Actual and hypothetical costs share one accounting model |
| 55 | Per-PR Cost Benchmark Artifact | Every PR reports LocalForge cost vs API-only baselines |
| 56 | Project Cost Rollup Dashboard | Final product report shows total spend and savings |
| 57 | Economy-First Prompt Bundler | API calls get minimal context bundles with evidence |
| 58 | Local Work Delegation Contracts | Local agents receive only bounded, validated subtasks |
| 59 | API-Only Simulation Mode | Estimate what the same run would cost with no local models |
| 60 | V3 Benchmark Acceptance Harness | Repeatable test proving API-led/economy-first value |
| 61 | Commercial Readiness Narrative | Docs and UI explain value without overclaiming autonomy |
| 62 | HP 12C V3 Recovery Trial | Re-run HP 12C using V3 routing and cost reporting |
| 63 | Medium PRD V3 Pilot | Run a human-approved medium PRD only after HP 12C V3 evidence |

---

## Phase 46 - V3 Product Reframe

### Goal

Reframe LocalForge from local-first harness to API-led, economy-first AI
Software Engineering Squad.

### Deliverables

- Update architecture docs with squad metaphor.
- Define user as Product Owner.
- Define Chief Engineer as Scrum Master + Staff Engineer.
- Define local agents as scoped squad members.
- Add glossary for Sprint, PRD, backlog, task, PR, acceptance, cost benchmark.

### Acceptance Criteria

- Docs no longer present local-first as the dominant execution rule.
- Runtime still supports local-only operation for simple workflows.
- No runtime dependency is introduced on Codex, Antigravity, Claude Code, or
  Cursor.

---

## Phase 47 - Squad Role Model and Workflow

### Goal

Make squad roles explicit in storage, API, CLI, and frontend.

### Deliverables

- Domain model additions for `SquadRole`, `SeniorityClass`, and `Responsibility`.
- Mapping from existing roles to squad metaphor.
- Sprint board states for PRD-to-PR execution.
- PO review state for human acceptance/rejection.

### Acceptance Criteria

- Existing tasks continue to run after migration.
- API exposes role assignments and seniority class.
- Frontend can display squad composition for a run.

---

## Phase 48 - Seniority-Based Routing Engine

### Goal

Route tasks based on required seniority and empirical model capability.

### Deliverables

- `TaskSeniorityClassifier`.
- Complexity features: file count, file size, visual requirement, API risk,
  integration risk, ambiguity, prior failures.
- Routing decisions: `chief_only`, `chief_led`, `local_assisted`,
  `local_only`, `deterministic_only`.
- Audit event for every routing decision.

### Acceptance Criteria

- Large UI rewrites and visual parity tasks do not start with small local
  models.
- Simple docs and summaries do not spend API credits by default.
- Routing can be explained in PR artifacts.

---

## Phase 49 - Model Capability Registry V3

### Goal

Track what each configured model has actually proven capable of doing.

### Deliverables

- Persistent model capability records.
- Success/failure counters by task class.
- Disqualification markers for truncation, timeout, bad JSON, syntax debris,
  visual degradation, and contract drift.
- CLI/API views for model capability.

### Acceptance Criteria

- A model that truncates large HTML is blocked from future large HTML tasks.
- A model can regain eligibility only through a configured benchmark pass.
- Local model capability is evidence-based, not assumed.

---

## Phase 50 - Anti-Loop Escalation Policy

### Goal

Stop wasting time and credits on repeated unproductive attempts.

### Deliverables

- Attempt policy per task class.
- Hard failure triggers for immediate escalation.
- Safe blocker state with exact evidence when API budget is unavailable.
- Run summary that distinguishes "needs Chief Engineer" from generic failure.

### Acceptance Criteria

- Local retry loops cannot exceed configured limits.
- Truncation immediately escalates or blocks.
- Test-hiding behavior is rejected.

---

## Phase 51 - Chief Engineer Execution Lane

### Goal

Allow the Chief Engineer to implement complex tasks directly under strict
contracts.

### Deliverables

- Chief Engineer implementation action schema.
- Complete-file rewrite support for large files with anti-truncation checks.
- Patch-size and file-scope constraints.
- Mandatory deterministic validation after Chief Engineer changes.

### Acceptance Criteria

- Chief Engineer can be assigned as Coder for `chief_only` tasks.
- Large file outputs are rejected if they contain omissions or placeholders.
- Paid calls are recorded in the cost ledger with task and PR linkage.

---

## Phase 52 - Cost Source Registry

### Goal

Store official model pricing sources as first-class benchmark data.

### Deliverables

- `pricing_sources` table.
- `model_pricing_snapshots` table.
- Source URL, retrieval timestamp, model name, input/output prices.
- Manual seed data for OpenAI, Anthropic, and Google.
- CLI command: `localforge costs sources list`.

### Acceptance Criteria

- Pricing source records include official URLs.
- Snapshots are immutable once used by a run.
- A run references the pricing snapshot used for its benchmark.

---

## Phase 53 - Competitor Benchmark Triads

### Goal

Define large/medium/small benchmark model triads for OpenAI, Google, and
Anthropic.

### Deliverables

- `benchmark_provider_profiles` config.
- OpenAI profile: large, medium, small.
- Google profile: large, medium, small.
- Anthropic profile: large, medium, small.
- Ability to mark profiles stale when pricing source changes.

### Acceptance Criteria

- PR cost reports can calculate all three provider baselines.
- Profiles are editable without code changes.
- Docs clearly state that baselines are hypothetical API token benchmarks.

---

## Phase 54 - Unified Token and Cost Ledger V3

### Goal

Unify actual spend, local token estimates, and hypothetical benchmark costs.

### Deliverables

- Extend `model_call_ledger`.
- Add local model token estimates.
- Add benchmark-cost calculation service.
- Track input, cached input, output, retry, and failure tokens.
- Add cost attribution to task, run, PR artifact, and role.

### Acceptance Criteria

- Every model interaction has a cost classification.
- Local model calls contribute to savings calculations.
- Missing token counts are estimated with a visible confidence flag.

---

## Phase 55 - Per-PR Cost Benchmark Artifact

### Goal

Every generated PR shows LocalForge cost and API-only benchmark alternatives.

### Deliverables

- `cost_benchmark.md` artifact.
- PR body cost table.
- Savings vs OpenAI, Google, Anthropic profiles.
- Actual paid calls, local calls, retries, and failure overhead.

### Acceptance Criteria

- PR_READY requires a cost benchmark artifact.
- Human reviewer can see whether a PR was economy-efficient.
- Cost report includes source snapshot IDs.

---

## Phase 56 - Project Cost Rollup Dashboard

### Goal

Show total product cost and savings after all PRs are produced.

### Deliverables

- Backend aggregation endpoint.
- CLI: `localforge costs report`.
- Frontend dashboard panel.
- Exportable Markdown/JSON cost report.

### Acceptance Criteria

- Report includes actual LocalForge spend.
- Report includes API-only baseline projections.
- Report includes savings percentage by provider and tier.
- Report separates API cost from local hardware/runtime cost.

---

## Phase 57 - Economy-First Prompt Bundler

### Goal

Make API calls small, sufficient, and auditable.

### Deliverables

- Context bundle builder per reason code.
- Token budget previews before paid calls.
- File snippet selection by relevance.
- Diff and error compression with hashes.
- Redaction checks before sending API context.

### Acceptance Criteria

- Chief Engineer calls do not receive the whole repo by default.
- Bundle includes enough context for correctness.
- Bundle metadata is stored without secrets.

---

## Phase 58 - Local Work Delegation Contracts

### Goal

Use local models only for tasks that are safe and bounded.

### Deliverables

- Local task contract schema.
- Maximum file size and output size by local model.
- Allowed action types per local role.
- Deterministic validation after local work.

### Acceptance Criteria

- Local models cannot receive tasks outside capability limits.
- Local outputs cannot alter architecture contracts.
- Local tasks produce measurable savings when successful.

---

## Phase 59 - API-Only Simulation Mode

### Goal

Estimate what a run would cost if all model work used API baselines.

### Deliverables

- Simulation service using actual token ledger.
- Provider/tier selection.
- Per-role simulation.
- Per-run and per-project comparison.

### Acceptance Criteria

- User can compare LocalForge hybrid vs OpenAI-only, Google-only,
  Anthropic-only baselines.
- Simulation explains assumptions and missing data.
- No external API call is required to run simulation.

---

## Phase 60 - V3 Benchmark Acceptance Harness

### Goal

Create repeatable evidence that API-led/economy-first routing is operationally
better than local-first and cheaper than API-only.

### Deliverables

- Benchmark projects:
  - small CLI/library project;
  - UI-heavy project;
  - medium full-stack project.
- Metrics:
  - PR_READY count;
  - human rejection count;
  - failed-safe count;
  - actual API spend;
  - projected API-only spend;
  - wall-clock time;
  - intervention count;
  - acceptance pass rate.

### Acceptance Criteria

- Benchmark report separates harness success from product acceptance.
- Runs can be reproduced with fixed seeds/config snapshots.
- Cost savings claims are backed by ledger data.

---

## Phase 61 - Commercial Readiness Narrative

### Goal

Make the product understandable and credible to users.

### Deliverables

- README positioning update.
- Cost benchmark explanation page.
- "How LocalForge differs from IDE agents" doc.
- Honest limitations page.
- Demo script showing PRD-to-PR with cost report.

### Acceptance Criteria

- No overclaiming full autonomy.
- Cost claims cite pricing source snapshots.
- User understands that PR review remains mandatory.

---

## Phase 62 - HP 12C V3 Recovery Trial

### Goal

Re-run the HP 12C validation under V3 routing and cost reporting.

### Deliverables

- Reset `LF-PRD-004` under V3 routing.
- Chief-led or deterministic visual correction path.
- Per-PR cost benchmark artifact.
- Product rollup cost report.
- Updated visual similarity evidence.

### Acceptance Criteria

- Local models are not allowed to truncate or rewrite the full HTML.
- Visual score must improve over `0.826`.
- PR_READY is allowed only when the visual contract passes or the human Product
  Owner explicitly lowers/changes the visual acceptance threshold.

---

## Phase 63 - Medium PRD V3 Pilot

### Goal

Attempt a medium-complexity PRD only after HP 12C V3 produces credible evidence.

### Deliverables

- Human-selected PRD.
- V3 squad plan.
- Cost budget approval before execution.
- PR-by-PR benchmark reports.
- Final cost rollup.
- Human product acceptance report.

### Acceptance Criteria

- The pilot is not started until Phase 62 has a documented outcome.
- The user approves the API budget before execution.
- Final report says what worked, what failed, and whether the economics justify
  continuing.

---

## 6. V3 Definition of Done

V3 is complete only when:

- task routing is API-led and evidence-based;
- local models are constrained by empirical capability;
- Chief Engineer can both orchestrate and implement complex tasks;
- every paid call is budgeted and audited;
- every PR includes a cost benchmark;
- project-level reports compare LocalForge actual spend against API-only
  baselines;
- commercial docs explain the value honestly;
- HP 12C or a replacement acceptance project demonstrates measurable progress
  without local-first failure loops.

