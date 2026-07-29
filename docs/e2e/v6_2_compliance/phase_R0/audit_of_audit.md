# LocalForge OS V6.2 Phase R0 Audit-of-Audit Matrix

## Scope

This report is the immutable Phase R0 audit baseline for the V6.1 compliance
reset. It maps AOA-01 through AOA-12 to exact repository evidence, reproduction
commands, and observed results. It is candidate evidence only; final production
acceptance still requires the full V6.2 backlog, reviewed PR state, remote CI,
owner approval, release assets, and canonical final validation.

## Baseline

- Audited baseline commit: `e2cc2a32fb0c1bb97dbb8fa54f5c9468398b636e`
- Historical release tag: `v6.1.0`
- Historical evidence manifest: `docs/e2e/v6_1_compliance/manifest.json`
- Historical evidence report: `docs/e2e/v6_1_compliance/acceptance_report.md`
- Remediation backlog: `docs/compliance_backlog_V6-1.md`
- Candidate remediation release: `v6.2.0`
- Release identity convention: `docs/e2e/v6_2_compliance/release_identity.md`

## Reproduction Commands

| Command | Expected result | Observed result |
| --- | --- | --- |
| `python scripts/check_release_truth.py --output artifacts/release-truth-local.json` | Exit 0 while reporting historical V6.1 as `INVALID`, validating release identity conventions, and reporting no forbidden claim leaks | Passed locally; unresolved backlog count was 259, release identity passed, and historical V6.1 rejection reasons were emitted. |
| `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | Exit 0 for all V6.2 candidate phase manifests | Passed locally for 13 candidate manifests. |
| `python -m pytest backend/tests/test_release_truth.py backend/tests/test_compliance_evidence.py -q` | Exit 0 | Passed locally. |
| `python -m mypy scripts/check_release_truth.py backend/tests/test_release_truth.py` | Exit 0 | Passed locally. |
| `git diff --check` | Exit 0 | Passed locally. |

## AOA Findings Matrix

| ID | Audited defect source | Runtime/evidence location | Command evidence | Observed result |
| --- | --- | --- | --- | --- |
| AOA-01 | `docs/compliance_backlog_V6-1.md:70` states that the published V6.1 manifest claimed acceptance while the validator rejected it. | `backend/localforge/services/compliance_evidence.py:66`, `docs/e2e/v6_1_compliance/manifest.json`, `docs/e2e/v6_1_compliance/acceptance_report.md:1` | `python scripts/check_release_truth.py --output artifacts/release-truth-local.json` | Historical V6.1 manifest verdict is `INVALID`; reasons include disputed V6.1 evidence, release version mismatch, tag mismatch, missing immutable source commit, and missing command evidence. |
| AOA-02 | `docs/compliance_backlog_V6-1.md:71` records direct-to-main delivery and unchecked backlog items. | `scripts/check_release_truth.py:197`, `scripts/check_release_truth.py:207`, `backend/localforge/services/compliance_evidence.py:190` | `python scripts/check_release_truth.py --output artifacts/release-truth-local.json` | The report counted 252 unresolved checkboxes and found no final accepted manifests; final acceptance is blocked while backlog items remain open. |
| AOA-03 | `docs/compliance_backlog_V6-1.md:72` records process-local operational loops and simulated side effects. | `docs/e2e/v6_2_compliance/phase_R8/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R8/known_limitations.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R8 remains candidate evidence only; durable loop side-effect proof is not final release evidence. |
| AOA-04 | `docs/compliance_backlog_V6-1.md:73` records synthetic strategy observations. | `backend/localforge/services/compliance_evidence.py:98`, `backend/tests/test_compliance_evidence.py:142`, `docs/e2e/v6_2_compliance/phase_R9/acceptance_report.md` | `python -m pytest backend/tests/test_compliance_evidence.py -q` | Synthetic benchmark observations are rejected by the canonical validator; observed benchmarking remains R9 candidate evidence. |
| AOA-05 | `docs/compliance_backlog_V6-1.md:74` records bypassable `PR_READY` evidence. | `docs/e2e/v6_2_compliance/phase_R3/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R3/known_limitations.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R3 candidate evidence exists, but final acceptance still requires reviewed PR, merge, CI, and final schema evidence. |
| AOA-06 | `docs/compliance_backlog_V6-1.md:75` records swarm graph state that did not dispatch all executable nodes through the governed worker path. | `docs/e2e/v6_2_compliance/phase_R6/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R7/acceptance_report.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R6/R7 manifests validate as candidate evidence; Deep Swarm remains disabled-by-default until accepted benchmark evidence exists. |
| AOA-07 | `docs/compliance_backlog_V6-1.md:76` records missing durable schedule runtime and incomplete kill cascade. | `docs/e2e/v6_2_compliance/phase_R4/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R4/known_limitations.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R4 candidate evidence is tracked; full durable schedule/kill/restart proof is not final release evidence. |
| AOA-08 | `docs/compliance_backlog_V6-1.md:77` records missing lease renewal, bounded waiting, deadlock handling, and race-safe acquisition. | `docs/e2e/v6_2_compliance/phase_R5/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R5/known_limitations.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R5 candidate evidence validates; full multi-process resource proof remains required before final release. |
| AOA-09 | `docs/compliance_backlog_V6-1.md:78` records version mismatch across tag, package, frontend, backend, and CLI. | `backend/localforge/version.py`, `pyproject.toml`, `frontend/package.json`, `docs/e2e/v6_2_compliance/phase_R1/acceptance_report.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R1 candidate evidence records canonical V6.2 identity; final release asset validation remains pending. |
| AOA-10 | `docs/compliance_backlog_V6-1.md:79` records clean-interpreter import failure through circular imports. | `docs/e2e/v6_2_compliance/phase_R1/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R1/known_limitations.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | Candidate import evidence exists; the full import matrix and installed-package verification remain R1/R12 requirements. |
| AOA-11 | `docs/compliance_backlog_V6-1.md:80` records private/public publication mismatch and missing hosted demo/release asset/video path. | `README.md:9`, `docs/e2e/v6_2_compliance/phase_R11/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R11/known_limitations.md` | `python scripts/check_release_truth.py --output artifacts/release-truth-local.json` | Current README status is experimental/disputed; public/demo/recruiter path is still not final accepted evidence. |
| AOA-12 | `docs/compliance_backlog_V6-1.md:81` records missing clean-clone, migration, concurrency, recovery, security, and controlled E2E evidence. | `docs/e2e/v6_2_compliance/phase_R10/acceptance_report.md`, `docs/e2e/v6_2_compliance/phase_R12/release_tree_report.md`, `docs/e2e/v6_2_compliance/phase_R12/known_limitations.md` | `python scripts/check_candidate_evidence.py --output artifacts/candidate-evidence-local.json` | R10/R12 candidate evidence validates; final production acceptance is still blocked by unresolved backlog and final release gates. |

## Canonical Rejection Reasons for V6.1

The current canonical validator rejects the historical V6.1 manifest with these
exact reasons:

- `historical V6.1 evidence is disputed and cannot be ACCEPTED`
- `manifest release version V6.1 does not match canonical version 6.2.0`
- `manifest release_tag v6.1.0 does not match canonical tag v6.2.0`
- `source_commit must be an immutable commit, not HEAD or empty`
- `manifest must include command evidence`

## Product Status Classification

| Area | Status | Evidence |
| --- | --- | --- |
| V6.1 Git tag and release publication | Real historical publication | `docs/e2e/v6_1_compliance/manifest.json`, `docs/e2e/v6_1_compliance/acceptance_report.md` |
| V6.1 production compliance | Disputed, not accepted | `scripts/check_release_truth.py`, `artifacts/release-truth-local.json` when generated |
| V6.2 remediation phases R0-R12 | Candidate evidence ready, not final accepted | `docs/e2e/v6_2_compliance/phase_R*/candidate_manifest.json` |
| Final production release | Not accepted | Blocked by unresolved mandatory backlog items and missing reviewed merge/tag/release asset validation |
