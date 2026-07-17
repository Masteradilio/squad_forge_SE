# LocalForge OS

LocalForge OS is an open-source, economy-aware AI software engineering control plane. It
turns a PRD into a sprint backlog, routes work across an agent squad, executes
tasks in isolated worktrees, validates outputs with deterministic gates, attempts
bounded self-healing, and prepares pull requests for human review.

The active open-source release contract is documented in
`docs/MASTER_BACKLOG_V5.md`. Earlier V2–V4 backlogs remain as architectural history.

## Product Thesis

LocalForge is not a general personal assistant or a purely local autonomous coder. Earlier
validation showed that local models are useful for scoped, cheap,
verifiable work, but they are not reliable as the primary engine for large UI
rewrites, architecture decisions, cross-file semantic consistency, and hard
recovery loops.

The current architecture is:

```text
Contract-first, economy-aware AI software engineering control plane.
```

The user acts as Product Owner. A deterministic orchestrator freezes scope and routes
work. Local models handle bounded tasks when their results can be verified cheaply;
larger API models handle architecture, semantic recovery, and high-risk review. API
lanes receive scoped evidence bundles rather than unrestricted repository context.

## Squad Roles

| Squad role | LocalForge role | Default model tier | Responsibility |
| --- | --- | --- | --- |
| Product Owner | Human user | Human | Provides PRD, reviews pull requests, accepts product outcomes |
| Scrum Master + Staff Engineer | Chief Engineer | API large model | Plans work, freezes contracts, handles hard implementation, triages failures |
| Senior Developer | High-risk Coder | API large/medium model | Complex UI, architecture, large rewrites, multi-file changes |
| Developer | Bounded Coder | Local medium model | Narrow implementation under frozen contracts |
| QA Engineer | Tester | Local/deterministic | Focused tests and validation artifacts |
| Bug Fixer | Fixer | Local first, API when needed | Syntax/import/simple repair locally; semantic or repeated failures escalate |
| Reviewer | Reviewer | API for final review | Contract-aware PR readiness review |
| PR Writer | PR artifact agent | Local small model | Summaries, changelog drafts, PR body text |
| Safety Auditor | Safety Kernel | Deterministic/local | File, command, dependency, budget, and policy enforcement |

## Economy-First Routing

LocalForge routes each task to the cheapest tier that is empirically capable of
doing it correctly. The router considers task complexity, file size, visual or
semantic fidelity requirements, previous failures, truncation, timeout history,
and deterministic validation results.

Typical routing:

- Chief-only: architecture, contract design, hard debugging, large UI rewrites,
  repeated self-healing failures.
- Chief-led: planning and review by the Chief Engineer, narrow implementation by
  local agents.
- Local-assisted: small isolated changes with strong tests and strict file
  contracts.
- Local-only: summaries, simple scaffolds, small test edits, deterministic
  transformations.
- Deterministic-only: validation, diff checks, command safety, cost accounting,
  visual comparison, artifact generation.

## Cost Benchmarking

Every paid model call should be recorded in a cost ledger. Every generated pull
request should include a benchmark table comparing LocalForge actual cost with
hypothetical API-only baselines.

The permanent benchmark sources are:

- OpenAI API pricing: <https://openai.com/api/pricing/>
- Anthropic Claude pricing: <https://platform.claude.com/docs/en/about-claude/pricing>
- Google Gemini API pricing: <https://ai.google.dev/gemini-api/docs/pricing>

The benchmark is not a claim about the internal billing of Codex, Antigravity,
Claude Code, Cursor, or any proprietary IDE agent. It is an API-token cost model
using public pricing pages as refreshable references.

Each PR should eventually report:

| Metric | LocalForge actual | OpenAI API-only | Google API-only | Anthropic API-only |
| --- | --- | --- | --- | --- |
| Paid input tokens | | | | |
| Paid output tokens | | | | |
| Local estimated tokens | | | | |
| Large-tier equivalent cost | | | | |
| Medium-tier equivalent cost | | | | |
| Small-tier equivalent cost | | | | |
| Estimated savings | | | | |

At project completion, LocalForge should consolidate all PR-level measurements
into a final cost rollup showing total API spend, local work handled without API
cost, cost by role, cost by task, cost by PR, retry/failure costs, and estimated
savings against the API-only baselines.

## Safety Model

LocalForge keeps the original safety goals:

- isolated worktrees per task;
- strict file contracts;
- command validation before execution;
- bounded repair loops;
- budget limits for time, tokens, retries, files, and diff size;
- fail-safe states instead of uncontrolled autonomy;
- human review before merge.

This routing model is not weaker safety. It uses expensive
model intelligence is used where it is needed, while deterministic gates and
local agents keep cost under control.

## Run Lifecycle and Self-Healing Promise

The Product Owner hands a PRD to the Scrum Master and waits. The Squad
promises to either deliver all tasks `PR_READY` for human review **or**
escalate the remaining work honestly to `BLOCKED_NEEDS_HUMAN_REVIEW` with
per-task blockers in `run_summary.md`. The runtime never closes a run
silently in a half-finished state.

Concretely, the scheduler runs a `recovery_cycle` whenever any task is in
`FAILED_SAFE` or `BLOCKED`. Each cycle:

1. **Budget check** — `_recovery_budget_remaining` reads the live paid-USD
   ledger and the `recovery_cycles_used` counter. If the absolute USD
   ceiling (`max_paid_usd_absolute = $6.0`) or the per-run cycle ceiling
   (`max_run_recovery_cycles = 3`) is exhausted, the cycle does not run.
2. **Scrum Master unblock** — reopens recoverable tasks with Chief
   Engineer guidance attached to the task contract.
3. **Repair** — the pipeline attempts up to
   `max_repair_attempts = 5` fixer rounds per cycle. Exceeding that
   surfaces a clear `FAILED_SAFE` rather than throwing.
4. **Escalate or close** — when the budget is gone, every remaining
   `FAILED_SAFE` is moved to `BLOCKED_NEEDS_HUMAN_REVIEW` and the run is
   finalized with the per-task blocker detail. The PO can reopen these
   tasks from `READY` later.

Absolute ceilings (defaults; tune in `.localforge/config.yaml`):

| Resource | Default ceiling | Field |
| --- | --- | --- |
| Run wall time | 5400 s (90 min) | `max_run_time` |
| Per-task duration | 900 s | `max_task_duration` |
| Repair rounds per cycle | 5 | `max_repair_attempts` |
| Repair rounds absolute | 10 | `max_repair_attempts_absolute` |
| Scheduler recovery cycles | 3 | `max_run_recovery_cycles` |
| Paid USD per cycle | $4.0 | `max_paid_usd` |
| Paid USD absolute per run | $6.0 | `max_paid_usd_absolute` |
| Worked tree files | 12 | `max_file_count` |
| Diff growth | 4000 chars | `max_diff_growth` |

Even at the defaults the economy-first routing keeps paid spend tight:
on the V4 pilot, ~70 % of model calls were executed on local Ollama
models (`gemma4:12b` → `granite4.1:8b` → `nemotron-3-nano:4b`) and the
remaining 30 % went through the Chief Engineer lane with NVIDIA NIM as
primary and OpenRouter as fallback. See
`scripts/run_benchmark_v4_only.py` for the reproducible harness.
If the Squad cannot produce a fully green run, the resulting
`BLOCKED_NEEDS_HUMAN_REVIEW` count appears in the V4 benchmark verdict
and in any run's `run_summary.md`, so the closure is auditable rather
than disguised.

## Demo: reproduce a 4/5 PR_READY run locally

``samples/demo-lf-smoke-prd/`` records a real end-to-end demo where a
five-task PRD was driven entirely by **local Ollama** (gemma4:12b,
granite4.1:8b, nemotron-3-nano:4b) and the V5.1 hardened scheduler.

- 4/5 tasks reached ``PR_READY`` in ~8 minutes
- 1 task honestly escalated to ``BLOCKED_NEEDS_HUMAN_REVIEW`` after
  the absolute recovery budget was exhausted
- Paid USD = **$0.0000**; OpenAI/Anthropic/Google API-only baselines
  $0.0473–$0.0511
- ``samples/demo-lf-smoke-prd/RUN_NOTES.md`` is the human-facing
  narrative; ``run_summary.md`` and ``cost_benchmark.md`` are the
  machine-verifiable artifacts.
- Reproduce locally with the exact env vars and
  ``scripts/apply_demo_local_first.py`` described in
  ``RUN_NOTES.md``.

## Quick Setup

### Prerequisites

- Python 3.11 or 3.12+
- Node.js LTS
- Git
- Optional: Ollama for local model lanes
- Optional: OpenRouter-compatible credentials for Chief Engineer API lanes

### Install the backend and CLI

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
localforge doctor
```

`localforge --version` is a non-destructive installation smoke check and requires no model
or paid-provider credentials.

PowerShell users can still use `./scripts/setup_backend.ps1` for the contributor setup.

### Frontend

```powershell
./scripts/setup_frontend.ps1
```

or:

```bash
./scripts/setup_frontend.sh
```

## Running LocalForge

Start the backend:

```bash
python manage.py run-backend
```

Start the frontend:

```bash
python manage.py run-frontend
```

Open the frontend at:

```text
http://localhost:5173
```

## Validation

Use targeted validation while developing:

```bash
python -m pytest backend/tests/<target_test_file>.py -q
mypy backend
npm run build --prefix frontend
```

Run broader suites only when a phase is ready for regression validation.

## How LocalForge Differs from IDE Agents

Unlike inline IDE agents (such as Cursor, Copilot, or Claude Code) which focus on interactive chat-driven edits on a single active file, LocalForge OS acts as an autonomous **Software Engineering Squad** in a box:
- **Contract-first architecture**: Before coding, the Chief Engineer designs and freezes a task contract specifying allowed files, public APIs, forbidden dependencies, and canonical test commands.
- **Isolated execution workspaces**: Every task runs inside its own Git worktree and sandboxed container, ensuring clean boundaries.
- **Multi-agent squad logic**: Work is routed automatically based on required seniority—expensive API calls are saved for large refactorings or visual matching, while local models handle simple docs, test stubs, or mechanical updates.

## Honest Limitations

While LocalForge OS strives for economy-first autonomy, users must keep in mind:
- **No Silver Bullet**: Autonomy does not mean zero oversight. A human Product Owner is always required to review final pull requests and visual similarities.
- **Hardware Prerequisites**: Bounded local models (e.g. `granite4.1:8b`) need adequate local hardware VRAM/RAM (minimum 16GB VRAM recommended). Slow inference runs may trigger sandbox timeouts.
- **Cost Benchmarks**: Baselines compare token volume ratios based on public competitor models. Actual proprietary IDE invoices may differ based on provider caching and billing plans.
- **Alpha Evidence**: Historical benchmark reports describe prior executions, but disposable workspaces and credentials are intentionally not committed. Treat a result as reproducible only when its manifest, hashes, commands, and acceptance tests are available.
- **Hybrid Privacy**: Local lanes keep source on the machine. API lanes send scoped task context to the configured provider; users requiring zero source egress must disable API routing.

## Benchmark and evaluation policy

LocalForge separates three kinds of evidence:

- **Verified current evidence**: reproducible from the current checkout.
- **Historical evidence**: produced by a previous run but missing disposable runtime state.
- **Targets**: intended gates that have not yet been demonstrated.

A benchmark is accepted only when real preflight checks pass, every planned task reaches
`PR_READY`, routing contracts and model calls are persisted, PR artifacts exist, and the
product acceptance tests pass. Cost savings or quality parity require an identical-workload
comparison against frontier-only, economy-API-only, local-only, and hybrid lanes.

## Key Documents

- `docs/LocalForge_OS_PRD.md` - product requirements
- `docs/MASTER_BACKLOG_V5.md` - active open-source readiness backlog
- `docs/architecture/V5_ARCHITECTURE.md` - current boundaries and invariants
- `docs/benchmarks/METHODOLOGY.md` - reproducible benchmark contract
- `docs/e2e/README.md` - status of historical and current evaluation evidence
- `CHANGELOG.md` - implementation history
- `CONTRIBUTING.md` - contributor workflow and change contract
- `SECURITY.md` - vulnerability reporting and runtime security boundaries
