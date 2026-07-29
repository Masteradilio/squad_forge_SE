# LocalForge OS V6.2 Phase R2 Canonical Evidence Report

## Verdict

`EVIDENCE_READY`

Phase R2 hardens the evidence validator so release truth cannot be produced from
ad hoc manifests, candidate manifests masquerading as final acceptance, direct
main delivery, self-review, synthetic observations, or unchecked JSON content.

This is candidate evidence only. Final `ACCEPTED` evidence still requires
post-merge GitHub state, owner-approved release tag, downloadable release
assets, and the final manifest schema.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Canonical V6.2 schemas | Only `localforge.v6_2.candidate_manifest.v1` and `localforge.v6_2.final_manifest.v1` are accepted as V6.2 evidence schemas. |
| Candidate/final separation | A manifest using the candidate schema cannot become `ACCEPTED`, even if it includes PR and CI fields. |
| Deterministic checksums | `canonical_json_bytes` and `manifest_sha256` provide stable SHA-256 checksums while excluding checksum fields from the hash input. |
| Trusted GitHub metadata contract | `ACCEPTED` requires consistent `github_metadata` for PR number, head commit, merge commit, CI URL/conclusion, release tag, human review, and direct-main status. |
| Self-review and direct-main rejection | Validator tests reject direct-to-main implementation evidence and self-review evidence. |
| Backlog completion gate | Final `ACCEPTED` evidence requires a `backlog_path`, and the referenced backlog must contain no unresolved `- [ ]` mandatory checkboxes. |
| Real manifest validation | Current V6.2 candidate manifests under `docs/e2e/v6_2_compliance/phase_R*/candidate_manifest.json` validate as `EVIDENCE_READY`. |
| CI candidate evidence validation | `scripts/check_candidate_evidence.py` validates every committed V6.2 candidate manifest and `.github/workflows/ci.yml` uploads the JSON validator output for compliance PR heads. |

## Validation Commands

```text
python -m pytest backend/tests/test_compliance_evidence.py -q
17 passed in 1.74s

python scripts/check_candidate_evidence.py
exit code 0

python -m mypy scripts/check_candidate_evidence.py
Success: no issues found

python -m ruff check scripts/check_candidate_evidence.py
All checks passed!
```

## Remote CI Context

The previous R1 push for PR #14 passed GitHub Actions at:

```text
https://github.com/Masteradilio/local_forge_os/actions/runs/30419175869
```

R2 changes still require their own exact-head remote CI after this candidate
evidence is pushed.

## Remaining Acceptance Requirements

- Querying live GitHub metadata through a release workflow is not implemented
  in this phase; R2 currently consumes trusted metadata supplied to the final
  manifest.
- Branch protection/ruleset enforcement is documented as mandatory but not
  mechanically configured from this private repository context.
- Final release asset upload, re-download, checksum verification, and immutable
  artifact publication remain R12 responsibilities.
