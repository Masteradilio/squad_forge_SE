# Phase R9 Candidate Acceptance Report

Status: EVIDENCE_READY

Phase R9 replaces strategy-comparison claims derived from hardcoded constants
with an observed, versioned corpus loaded from
`docs/e2e/v6_2_compliance/phase_R9/observed_corpus.json`.

Implemented controls:

- The evaluation corpus now records event difficulty, fixture path,
  acceptance test, holdout flag, license, provenance, and content hash.
- Strategy observations now include strategy, task-run binding, artifact IDs,
  provider/model, prompt-context revision, target commit, environment
  fingerprint, budget, timeout, timestamps, tokens, cost, duration, safety
  events, and human outcome.
- Strategy comparisons validate that each strategy was measured on the same
  corpus and equivalent budget/environment/timeout/target-commit envelope.
- Metrics keep unavailable measurements as `UNKNOWN` instead of replacing them
  with synthetic values.
- PR-ready rate includes a Wilson confidence interval, and duration variance is
  reported where repeated observations exist.

Validation commands:

```powershell
python -m pytest backend/tests/test_phase11_operational_loops.py -q
python -m mypy backend/localforge/services/eval_corpus.py backend/localforge/services/strategy_comparator.py backend/tests/test_phase11_operational_loops.py
python -m ruff check backend/localforge/services/eval_corpus.py backend/localforge/services/strategy_comparator.py backend/tests/test_phase11_operational_loops.py
```

Observed results:

- `16 passed in 0.08s`
- `Success: no issues found in 3 source files`
- `All checks passed!`

