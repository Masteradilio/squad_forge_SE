# LocalForge OS V6.2 Release Identity and Tag Convention

## Status

`EVIDENCE_READY`

This document defines the release identity used by the V6.2 compliance
remediation. It is not owner approval for publication and does not authorize
creating or pushing any release tag.

## Historical Tag Policy

- `v6.1.0` is immutable historical state.
- The `v6.1.0` tag must not be moved, deleted, overwritten, force-pushed, or
  reused for V6.2 remediation.
- Historical V6.1 artifacts may be referenced for traceability, but they are
  disputed compliance evidence and cannot be converted into V6.2 acceptance.

## Candidate Identity

- Product version: `6.2.0`
- Candidate release tag string in candidate manifests: `v6.2.0`
- Candidate evidence schema: `localforge.v6_2.candidate_manifest.v1`
- Candidate branch pattern: `codex/v62-*` for remediation work and
  `release/v6.2.0` only for an owner-approved release branch.
- Candidate evidence verdict: `EVIDENCE_READY`

Candidate manifests may use `release_tag: "v6.2.0"` to prove version/tag
consistency before the real Git tag exists. That field is a proposed release
identity, not a published tag claim.

## Stable Release Convention

A stable V6.2 release exists only after all of the following are true:

1. Every mandatory task in `docs/compliance_backlog_V6-1.md` is closed.
2. Every phase R0 through R12 has validator-confirmed final evidence.
3. The release branch is created from reviewed `origin/main`.
4. The owner explicitly approves creating the annotated tag.
5. The annotated tag `v6.2.0` is created at the accepted merge commit.
6. The GitHub Release is created from that tag.
7. Release assets are downloaded in a clean checkout and revalidated by the
   canonical validator.

Only that state may use the final stable-release wording reserved by
`docs/compliance_backlog_V6-1.md`.

## Forbidden States

- Moving or replacing `v6.1.0`.
- Publishing an unreviewed or direct-to-main stable release.
- Treating candidate evidence as `ACCEPTED`.
- Treating green local tests or green CI alone as release acceptance.
- Creating a GitHub Release before owner approval and final validator
  acceptance.
