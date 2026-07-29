# Phase R12 Candidate Acceptance Report

Status: EVIDENCE_READY

Phase R12 adds release-candidate audit tooling and candidate evidence. It does
not claim final release acceptance because clean-clone validation, reviewed
merge, owner-approved tag, GitHub Release assets, and final `ACCEPTED` manifest
cannot exist before PR review and merge.

Implemented controls:

- Added `ReleaseTreeAuditor` for tracked-file inventory, SHA-256 checksums,
  forbidden runtime artifact detection, secret-pattern detection, and personal
  local path detection.
- Added `scripts/check_release_tree.py` to generate JSON audit reports without
  deleting or modifying release files.
- Generated
  `docs/e2e/v6_2_compliance/phase_R12/release_tree_report.json` for the
  V6.2 compliance evidence scope.
- Added regression tests proving clean scopes pass and tracked secrets,
  personal paths, and runtime databases are rejected.

Validation commands:

```powershell
python -m pytest backend/tests/test_phase_r12_release_audit.py -q
python -m mypy backend/localforge/services/release_audit.py scripts/check_release_tree.py backend/tests/test_phase_r12_release_audit.py
python -m ruff check backend/localforge/services/release_audit.py scripts/check_release_tree.py backend/tests/test_phase_r12_release_audit.py
python scripts/check_release_tree.py --root . --scope docs/e2e/v6_2_compliance --output docs/e2e/v6_2_compliance/phase_R12/release_tree_report.json
```

Observed results:

- `2 passed in 0.58s`
- `Success: no issues found in 3 source files`
- `All checks passed!`
- Release-tree report generation completed with exit code 0 for the compliance
  evidence scope.

