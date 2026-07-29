# Phase R11 Candidate Acceptance Report

Status: EVIDENCE_READY

Phase R11 adds a deterministic CPU-only demo path intended for quick technical
verification without provider credentials, GPU, or paid API calls.

Implemented controls:

- Added `localforge demo --scenario ci-regression --deterministic`.
- The demo creates a disposable local Git repository, reproduces a failing
  pytest test, creates a real Git worktree, applies a deterministic patch,
  reruns the test successfully, captures the diff, and generates a draft PR
  artifact.
- The exported `demo_run.json` is schema-versioned, sanitized, checksum-backed,
  and labels worker output as `deterministic_replay_not_live_model`.
- The exported `demo_replay.html` is static and renders from the same sanitized
  replay payload without backend, model provider, GPU, or API key.
- Runtime `repo/` and `worktrees/` directories are removed after evidence
  export so only sanitized artifacts remain versionable.

Validation commands:

```powershell
python -m pytest backend/tests/test_phase_r11_demo.py backend/tests/test_cli.py::test_cli_deterministic_demo_exports_replay -q
python -m mypy backend/localforge/demo.py backend/localforge/cli/demo.py backend/localforge/cli/main.py backend/tests/test_phase_r11_demo.py backend/tests/test_cli.py
python -m ruff check backend/localforge/demo.py backend/localforge/cli/demo.py backend/localforge/cli/main.py backend/tests/test_phase_r11_demo.py backend/tests/test_cli.py
```

Observed results:

- `2 passed in 2.47s`
- `Success: no issues found in 5 source files`
- `All checks passed!`

