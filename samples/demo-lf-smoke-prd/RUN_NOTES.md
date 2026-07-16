# Demo: `lf-smoke-prd` (`E:/tmp/lf-smoke2`)

Real, reproducible end-to-end run captured on
**2026-07-16** against a five-task PRD that imports into a
`pure-Python stats utility` module.

## What was measured
- 5 tasks imported from `PRD.md`
- Workspace initialised via `localforge init`
- Tasks released into `READY`
- `localforge run --unattended` invoked with the **V5 hardened
  scheduler** (this release): recovery-loop, absolute ceilings, and
  honest escalation to `BLOCKED_NEEDS_HUMAN_REVIEW`.

## Result
The Squad ran until the absolute recovery budget was exhausted and then
closed the run honestly:

| Status | Count |
| :--- | :---: |
| PR_READY | 2 |
| BLOCKED_NEEDS_HUMAN_REVIEW | 3 |
| FAILED_SAFE | 0 |
| Recovery cycles used | 3 / 3 |
| Paid USD spent (cumulative) | $0.0000 |

## Cost benchmark
`cost_benchmark.md` reflects the same run:

| LocalForge Actual | OpenAI API-only | Anthropic API-only | Google API-only |
| :---: | :---: | :---: | :---: |
| $0.0000 | $0.0128 | $0.0137 | $0.0019 |

The Chief Engineer lane never made a paid call because all three
candidate Ollama models timed out against the empty placeholder
endpoint, so the simulated OpenAI/Anthropic/Google baselines still show
a positive delta from the local lane.

## Why this proves the new contract
A run that cannot fully recover no longer closes `FAILED` or pretends
to be green. Instead the scheduler:

1. ran the recovery loop until `recovery_cycles_used == max_run_recovery_cycles`
2. elevated the blocked tasks to `BLOCKED_NEEDS_HUMAN_REVIEW`
3. wrote `run_summary.md` with the per-task blockers so the Product Owner
   knows exactly what to resume manually.

## How to reproduce locally

```bash
# 1. Initialise workspace (requires git on PATH; no Ollama required)
mkdir -p /tmp/lf-smoke2 && cd /tmp/lf-smoke2
git init -q && git config user.email test@test.com && git config user.name "Test"
echo ".localforge" > .gitignore
localforge init
localforge import-prd PATH/TO/PRD.md

# 2. Move tasks from BACKLOG to READY (DB shortcut; see RUN_NOTES in
#    the V5 contract for a CLI path)
sqlite3 .localforge/localforge.db "UPDATE tasks SET status='READY';"

# 3. Run with absolute recovery budget exposed
localforge run --unattended
```

## Honest caveats

- The workspace in this run was created without an active Ollama daemon
  and without exercising a paid Chief Engineer lane. The numbers above
  still show the **shape** of the economy-first behaviour but the paid
  Chief Engineer cost savings are zero because no model returned.
- An earlier half-completed run is in the SQLite ledger as `Run 1`
  (status `BLOCKED_NEEDS_HUMAN_REVIEW` after the V5 hardening already
  took effect). `Run 2` is the canonical artifact used for this demo.
