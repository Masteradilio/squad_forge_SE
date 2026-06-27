# LocalForge OS - V3-Only Acceptance Benchmark Plan

> Status: ready for execution
> Purpose: validate whether the current V3 architecture can deliver a small
> functional software product end-to-end with real LocalForge execution,
> reviewable PR artifacts, cost evidence, and human acceptance.

---

## 1. Benchmark Objective

This benchmark no longer compares V3 against V2.

The previous V2 vs V3 benchmark is blocked because there is no executable V2
baseline branch or tag in the current repository history. Comparing V3 against a
fabricated or non-runnable V2 would produce misleading evidence.

The benchmark now answers one practical question:

```text
Can LocalForge V3 autonomously transform a small PRD into a working, tested,
reviewable product with coherent PR artifacts and cost/audit reports?
```

Passing LocalForge's own backend tests is not enough. The benchmark must prove
product-building behavior through a real run, real workspace artifacts, real
tests, and a human-reviewable output.

---

## 2. Benchmark Product

### Selected Product: SprintBoard Lite

Use the existing PRD:

```text
docs/PRD_SPRINTBOARD_LITE.md
```

SprintBoard Lite is the right V3 acceptance target because it is:

- simpler than HP 12C;
- more meaningful than a health-check endpoint;
- small enough for repeated local execution;
- rich enough to exercise backend rules, frontend behavior, tests, state
  transitions, artifacts, and cost reporting;
- easy for a human to validate in minutes.

---

## 3. V3 Architecture Under Test

The run must use the current LocalForge V3 architecture:

- squad roles active;
- seniority routing active;
- Chief Engineer lane available when the task requires it;
- local delegation contracts active;
- anti-loop escalation active;
- pricing snapshots and cost ledger active;
- per-task or per-PR cost benchmark artifacts;
- PR factory artifacts for human review;
- safety kernel and sandbox policy active;
- no fabricated metrics.

Local models may be used only if the V3 router selects them under the current
policy. If a task is too complex for local models, V3 should escalate rather
than loop.

For this benchmark, at least one complex SprintBoard Lite task must be routed to
the Chief Engineer lane and recorded in `model_call_ledger` with provider
`openrouter`. A run with zero OpenRouter calls does not exercise the V3
API-led/economy-first architecture and must be classified as `REJECTED` or
`BLOCKED`, even if some local tasks produce artifacts.

---

## 4. Environment Pre-flight

The benchmark must stop with status `BLOCKED` if any mandatory pre-flight check
fails.

### Required Checks

- Docker is available, or LocalForge is explicitly configured for approved
  restricted local/dev sandbox mode.
- Ollama is reachable when local models are configured.
- The configured local model exists. Do not require `llama3` unless it is
  actually installed.
- Model fallback order is:
  - `LOCALFORGE_MODEL`;
  - configured `.localforge/config.yaml` default model;
  - `gemma4:12b`;
  - `granite4.1:8b`;
  - `nemotron-3-nano:4b`.
- OpenRouter credentials are not printed or copied to artifacts.
- `OPENROUTER_MODEL` and `OPENROUTER_API_KEY` are configured for the Chief
  Engineer lane.
- `docs/PRD_SPRINTBOARD_LITE.md` exists.
- The PRD import produces the expected task count, or the report explains the
  actual task count produced by the compiler.

### Non-blocking Checks

Do not require any V2 branch, tag, or baseline.

---

## 5. Required Execution

Create one isolated V3 workspace:

```text
benchmarks/workspaces/sprintboard-v3-only
```

Run LocalForge V3 from that workspace using real CLI commands, not direct DB
seeding or simulated records.

Minimum command sequence:

```powershell
python -m localforge.cli.main init
python -m localforge.cli.main import-prd <absolute path to docs/PRD_SPRINTBOARD_LITE.md>
python -m localforge.cli.main plan --approve-all
python -m localforge.cli.main run --unattended
python -m localforge.cli.main prs
python -m localforge.cli.main costs report
python -m localforge.cli.main costs simulate
python -m localforge.cli.main benchmark report
python -m localforge.cli.main squad composition
```

If a command name differs in the current CLI, use the real available command
and record the substitution in the report.

---

## 6. Product Acceptance Criteria

The generated SprintBoard Lite product is accepted only if a human can verify
these behaviors from the produced files or app:

- Create a work item with title, description, priority, and status.
- Reject empty title.
- List work items.
- Edit title, description, priority, and status.
- Delete a work item.
- Render four board columns: `backlog`, `in_progress`, `review`, `done`.
- Move an item through valid transitions:
  - `backlog -> in_progress`;
  - `in_progress -> review`;
  - `review -> done`;
  - `review -> in_progress`.
- Reject invalid transitions, especially `done -> backlog`.
- Filter by status.
- Filter by priority.
- Export active items as JSON with expected fields.

The product must not be accepted if it is only a static mockup with no working
behavior.

---

## 7. Engineering Acceptance Criteria

The V3 run is accepted only if:

- at least one Chief Engineer/OpenRouter call is recorded in
  `model_call_ledger`;
- the benchmark reports actual paid API cost and simulated full-API baseline
  costs;

- at least one reviewable PR artifact is generated;
- artifacts map to real changed files;
- generated `diff.patch` artifacts are not placeholders;
- generated `tests.md` artifacts reference real commands and results;
- backend or product tests cover:
  - empty title rejection;
  - valid state transitions;
  - invalid state transitions;
  - CRUD behavior;
  - JSON export;
- frontend build or static validation passes when frontend files exist;
- no generated source contains:
  - `omitted for brevity`;
  - `rest of code unchanged`;
  - placeholder comments replacing required implementation;
  - fake test output;
- PR_READY is counted only from task status, not artifact count;
- FAILED_SAFE and BLOCKED tasks are reported honestly.

---

## 8. Cost and Audit Acceptance Criteria

The V3 run must produce a cost/audit report with:

- run id;
- task ids and final statuses;
- model routing decisions when available;
- local model attempts;
- Chief Engineer attempts;
- paid API calls and estimated cost;
- pricing snapshot ids or pricing source ids;
- simulated OpenAI API-only cost;
- simulated Anthropic API-only cost;
- simulated Google API-only cost;
- estimated LocalForge savings if the run succeeds;
- explicit statement when no paid API call occurred.

Cost savings must not be claimed unless the product is accepted.

---

## 9. Metrics to Collect

Produce both Markdown and JSON reports.

### Delivery Metrics

- total tasks imported;
- total tasks planned;
- `PR_READY` count;
- `FAILED_SAFE` count;
- `BLOCKED` or remaining `READY/BACKLOG` count;
- run terminal status;
- run duration;
- artifact count;
- PR artifact paths;
- changed files;
- accepted product files.

### Quality Metrics

- product tests passing;
- generated test count;
- backend tests passing, if executed;
- frontend build/static validation status;
- acceptance checklist score;
- reviewer defects found.

### Autonomy Metrics

- human interventions;
- repair attempts;
- local model attempts;
- Chief Engineer attempts;
- timeout incidents;
- truncation incidents;
- placeholder incidents;
- contract drift incidents.

### Cost Metrics

- paid input tokens;
- paid output tokens;
- actual API cost;
- local calls;
- simulated competitor costs;
- cost per PR_READY;
- cost per human-accepted task;
- cost per accepted product.

---

## 10. Required Artifacts

Update or create these tracked artifacts:

```text
docs/e2e/V3_ONLY_BENCHMARK_REPORT.md
docs/e2e/v3_only_benchmark_metrics.json
docs/e2e/sprintboard_lite_human_acceptance.md
```

The existing comparative files may remain as historical blocked evidence, but
the new V3-only files are the source of truth for this benchmark.

Runtime artifacts must remain untracked:

```text
benchmarks/workspaces/
.localforge/
*.db
*.db-journal
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
debug.log
.env
```

---

## 11. V3-Only Result Classification

Use exactly one final status.

### ACCEPTED

Use `ACCEPTED` only when:

- run completes;
- product works according to the checklist;
- tests/build evidence is real;
- PR artifacts are reviewable;
- cost/audit report is coherent.

### PARTIAL

Use `PARTIAL` when:

- run executes but some tasks fail;
- product is incomplete;
- PR artifacts exist but are not sufficient;
- tests fail but failure evidence is useful.

### BLOCKED

Use `BLOCKED` when:

- pre-flight fails;
- required model/sandbox/API is unavailable;
- LocalForge cannot start;
- execution cannot begin safely.

### REJECTED

Use `REJECTED` when:

- run claims success with fake evidence;
- artifacts are placeholders;
- product is only a mockup;
- reports disagree with the SQLite/task state.

---

## 12. Interpretation

If the result is `ACCEPTED`, V3 is ready for a medium PRD pilot.

If the result is `PARTIAL`, V3 is operational but not yet reliable; the report
must identify the highest-value fixes before another benchmark run.

If the result is `BLOCKED`, solve infrastructure/configuration first.

If the result is `REJECTED`, fix benchmark integrity before testing product
capability again.

Do not claim that V3 is commercially validated from a single SprintBoard Lite
run. At most, an accepted run proves that V3 can complete a small functional
software product with auditable evidence under the current machine setup.
