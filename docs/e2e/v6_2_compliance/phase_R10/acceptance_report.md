# Phase R10 Candidate Acceptance Report

Status: EVIDENCE_READY

Phase R10 adds baseline production hardening controls for local/hosted API
operation without changing the default local developer flow.

Implemented controls:

- Optional API bearer-token authentication through `LOCALFORGE_API_TOKEN`.
- Request payload-size enforcement through `LOCALFORGE_MAX_BODY_BYTES`.
- Public health/readiness endpoints with security policy diagnostics.
- Correlation ID response propagation for request-level tracing.
- Central secret redaction for environment-backed secrets, bearer tokens,
  generic key/token/password assignments, and OpenAI-style `sk-...` keys.
- Root-constrained path validation helper for path traversal prevention.
- Regression coverage for authentication negative cases, oversized payloads,
  secret redaction, and path traversal rejection.

Validation commands:

```powershell
python -m pytest backend/tests/test_phase_r10_operability.py backend/tests/test_api_server.py -q
python -m mypy backend/localforge/services/security_controls.py backend/localforge/services/audit.py backend/localforge/api/app.py backend/tests/test_phase_r10_operability.py
python -m ruff check backend/localforge/services/security_controls.py backend/localforge/services/audit.py backend/localforge/api/app.py backend/tests/test_phase_r10_operability.py
```

Observed results:

- `14 passed in 3.31s`
- `Success: no issues found in 4 source files`
- `All checks passed!`

