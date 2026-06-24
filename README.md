# LocalForge OS

LocalForge OS is an API-led, economy-first AI software engineering harness. It
turns a PRD into a sprint backlog, routes work across an agent squad, executes
tasks in isolated worktrees, validates outputs with deterministic gates, attempts
bounded self-healing, and prepares pull requests for human review.

The current V3 product direction is documented in
`docs/MASTER_BACKLOG_V3.md`.

## Product Thesis

LocalForge is no longer designed as a purely local-first autonomous coder. The
HP 12C validation showed that local models are useful for scoped, cheap,
verifiable work, but they are not reliable as the primary engine for large UI
rewrites, architecture decisions, cross-file semantic consistency, and hard
recovery loops.

The V3 architecture is:

```text
API-led, economy-first AI Software Engineering Squad.
```

The user acts as Product Owner. A large API model acts as Chief Engineer and
Scrum Master for complex work. Local models remain part of the squad, but only
for bounded work that the harness can verify cheaply and deterministically.

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

The V3 change is not weaker safety. It is more realistic routing: expensive
model intelligence is used where it is needed, while deterministic gates and
local agents keep cost under control.

## Quick Setup

### Prerequisites

- Python 3.11 or 3.12+
- Node.js LTS
- Git
- Optional: Ollama for local model lanes
- Optional: OpenRouter-compatible credentials for Chief Engineer API lanes

### Backend

```powershell
./scripts/setup_backend.ps1
```

or:

```bash
./scripts/setup_backend.sh
```

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

## Key Documents

- `docs/LocalForge_OS_PRD.md` - product requirements
- `docs/MASTER_BACKLOG.md` - V1 implementation phases
- `docs/MASTER_BACKLOG_V2.md` - hybrid Chief Engineer lessons and phases
- `docs/MASTER_BACKLOG_V3.md` - API-led, economy-first architecture backlog
- `docs/e2e/HP12C_PRODUCT_VALIDATION_REPORT.md` - HP 12C validation evidence
- `CHANGELOG.md` - implementation history

## Current Direction

The next strategic work is to implement V3 phases 46-63:

- product reframe and squad workflow;
- seniority-based routing;
- Chief Engineer execution lane;
- permanent pricing source registry;
- token and cost ledger;
- per-PR cost benchmark artifact;
- project-level cost rollup;
- API-only simulation mode;
- HP 12C recovery trial under V3 routing;
- medium PRD pilot only after credible HP 12C evidence.
