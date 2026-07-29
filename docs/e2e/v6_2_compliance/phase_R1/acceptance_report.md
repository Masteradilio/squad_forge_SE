# LocalForge OS V6.2 Phase R1 Packaging and Import Hygiene Report

## Verdict

`EVIDENCE_READY`

Phase R1 adds concrete release-integrity checks for the V6.2 remediation branch.
It verifies one canonical product version, clean public imports, wheel
installation without repository `PYTHONPATH`, and explicit SQLite backup,
restore, and legacy schema upgrade behavior.

This is candidate evidence only. It must not be converted to `ACCEPTED` until
the remediation PR is reviewed, merged with remote CI passing, and final
post-merge evidence is generated from GitHub state.

## Scope

- Backlog tasks: `V61C-100`, `V61C-101`, `V61C-102`, `V61C-103`
- Target release: `v6.2.0`
- Branch: `codex/v62-truth-reset-foundation`
- Current PR: `https://github.com/Masteradilio/local_forge_os/pull/14`

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Canonical version source | `backend/localforge/version.py` drives backend/API/CLI, and `scripts/check_version_consistency.py` fails on package or frontend drift. |
| Import hygiene | `localforge.services` and `localforge.storage` now use lazy public boundaries; `scripts/check_import_matrix.py` imports public modules in a clean interpreter. |
| Clean install | `backend/tests/test_phase_r1_release_integrity.py` and `scripts/check_clean_package_install.py` build both sdist and wheel, reject wheels that package backend tests, install the wheel into an isolated venv without repository `PYTHONPATH`, and verify import, CLI version, and CLI help smoke. |
| Demo guide sample path | `docs/demo.md` now references the existing `samples/demo-lf-smoke-prd/` workspace and imports its local `PRD.md`. |
| Migration and backup safety | `backup_sqlite_database`, `restore_sqlite_database`, future-schema rejection, and V5 fixture upgrade preservation are covered for projects, runs, tasks, task runs, audit events, memory facts, graph mutations, path leases, and artifacts. |
| Cross-platform package CI | `.github/workflows/ci.yml` runs package smoke validation on `ubuntu-latest` and `windows-latest` and uploads the JSON result as a workflow artifact. |

## Validation Commands

```text
python -m pytest backend/tests/test_phase_r1_release_integrity.py -q
5 passed in 13.71s

python -m pytest backend/tests/test_phase_r1_release_integrity.py backend/tests/test_compliance_evidence.py backend/tests/test_storage.py backend/tests/test_api_server.py -q
26 passed in 21.11s

python scripts/check_import_matrix.py
exit code 0

python scripts/check_version_consistency.py
exit code 0

python scripts/check_clean_package_install.py
exit code 0

python -m pytest backend/tests/test_release_truth.py::test_demo_guide_references_existing_sample_project -q
1 passed

python -m pytest backend/tests/test_phase_r1_release_integrity.py -q
8 passed in 11.89s

python -m pytest backend/tests/test_phase_r1_release_integrity.py::test_sqlite_backup_restore_and_v5_fixture_upgrade_preserves_legacy_entities -q
1 passed in 0.46s

python -m mypy backend/localforge/storage/bootstrap.py backend/localforge/storage/__init__.py backend/tests/test_phase_r1_release_integrity.py
Success: no issues found in 3 source files

python -m ruff check backend/localforge/storage/bootstrap.py backend/localforge/storage/__init__.py backend/tests/test_phase_r1_release_integrity.py scripts/check_version_consistency.py scripts/check_import_matrix.py
All checks passed!

git diff --check
exit code 0
```

## Remaining Acceptance Requirements

- Remote CI must pass on the exact PR head after these R1 changes are pushed.
- Human review and owner-approved merge are still required.
- Final R1 evidence must be regenerated from the merged commit before any
  release acceptance claim.
