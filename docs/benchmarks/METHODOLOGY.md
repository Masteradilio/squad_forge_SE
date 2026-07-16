# LocalForge Benchmark Methodology

## Purpose

Benchmarks determine whether LocalForge improves cost without lowering deliverable quality.
They are not product demos and must not contain runtime shortcuts for the evaluated domain.

## Required lanes

Run the same unseen task and repository state through:

1. frontier API model only;
2. economy API model only;
3. local model only;
4. LocalForge hybrid routing.

All lanes use the same PRD, starting commit, network policy, time budget, acceptance tests,
and human-review rubric.

## Required measurements

- final acceptance-test result;
- tasks completed and rejected;
- elapsed time and retries;
- model/provider calls, tokens, and actual cost;
- local inference duration and hardware;
- files and lines changed;
- safety blocks and human interventions;
- independent human acceptance result.

`PR_READY` is pipeline state, not proof of product quality. A lane is successful only when
the external acceptance suite and human review pass.

## Evidence manifest

Every published result must include:

- LocalForge commit and dirty-worktree state;
- input repository commit and PRD SHA-256;
- exact command and sanitized configuration;
- operating system, Python/Node versions, hardware, and model identifiers;
- acceptance-test command and exit code;
- hashes of metrics, report, and final diff;
- explicit list of missing/disposable evidence.

Never publish API keys, `.env`, private source, raw prompts containing private code, or runtime
databases that may contain sensitive content.

## Lane manifest collection

Run each lane independently, then collect its evidence without re-running the lane or
inventing a cost estimate:

```bash
python scripts/collect_benchmark_evidence.py \
  --lane hybrid \
  --workspace /path/to/evaluated-repository \
  --prd /path/to/unseen-prd.md \
  --metrics /path/to/hybrid-metrics.json \
  --acceptance-command "python -m pytest acceptance_tests -q" \
  --output docs/benchmarks/hybrid-manifest.json
```

The metrics JSON must record `acceptance_passed`, `elapsed_seconds`, `retries`,
`human_interventions`, `model_calls`, `paid_cost_usd`, and `local_inference_seconds`.
The generated manifest is evidence collection, not an acceptance result. A comparative
claim still requires the four lanes and independent review. It stores input names and hashes,
not local absolute paths.

## Claim levels

- **Historical**: a previous run is documented, but current reproduction evidence is absent.
- **Reproducible**: a third party can recreate the run from the manifest and public inputs.
- **Comparative**: all required lanes ran under the same contract.
- **Validated advantage**: hybrid quality is non-inferior and the declared cost/time target passes.

Only the final level supports public savings or quality-parity claims.

## Hardening Runtime sample (V5.1)

The V5.1 contract proves an additional invariant on top of the four
lanes: the **scheduler can close a run without ever pretending a partial
outcome was green**. A captured end-to-end run against a five-task PRD
(`samples/demo-lf-smoke-prd/PRD.md`) on a workspace with no active
Ollama daemon and no cleared paid-cache ran the recovery loop until the
absolute ceiling was reached and exited honestly:

- `samples/demo-lf-smoke-prd/run_summary.md` shows
  `BLOCKED_NEEDS_HUMAN_REVIEW` with `recovery_cycles_used = 3/3`,
  `paid_usd_spent_cached = $0.0000`, 2 `PR_READY` tasks and 3 tasks
  awaiting human review.
- `samples/demo-lf-smoke-prd/cost_benchmark.md` records the cost ledger
  snapshot produced by `CostBenchmarkService.calculate_benchmarks`.
- `classify_benchmark_status` on the resulting
  `task_statuses = {PR_READY: 2, BLOCKED_NEEDS_HUMAN_REVIEW: 3}` returns
  `PARTIAL` with an explicit `BLOCKED_NEEDS_HUMAN_REVIEW` blocker
  (consistent with the `test_v4_benchmark_marks_blocked_needs_human_review_as_partial`
  regression test added in `backend/tests/test_v3_phases.py`).

To reproduce the workspace end-to-end:

```bash
mkdir -p /tmp/lf-smoke2 && cd /tmp/lf-smoke2
git init -q && git config user.email test@example.com && git config user.name "Test"
localforge init
localforge import-prd samples/demo-lf-smoke-prd/PRD.md
sqlite3 .localforge/localforge.db "UPDATE tasks SET status='READY';"
localforge run --unattended
```
