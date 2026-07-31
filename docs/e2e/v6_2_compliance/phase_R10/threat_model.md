# LocalForge OS — Production Threat Model & Security Controls (V61C-1000)

## 1. Executive Summary & Boundaries

This document defines the threat model, security boundaries, trusted/untrusted actors, and risk mitigation strategies for LocalForge OS version 6.2.0 in both local-first and supervised production deployments.

---

## 2. Actor Classification & Trust Boundaries

| Actor Class | Trust Level | Description | Access Rights |
| --- | --- | --- | --- |
| **System Operator / Developer** | `TRUSTED` | Local user or platform admin operating the system. | Full administrative API access, workspace management, secret configuration. |
| **Governed Subagent / Worker** | `SEMI-TRUSTED` | Bounded model execution worker running in isolated worktrees. | Least-privilege file mutation within assigned `PathLease` workspace only. |
| **External Repository / Event Source** | `UNTRUSTED` | Remote GitHub/GitLab issues, PRs, comments, and CI logs. | Read-only input through `sanitize_external_text()` and ActionGateway. |
| **Malicious External Prompt / Payload** | `ADVERSARIAL` | Adversarial injection attempts embedded in issues or review threads. | Strict neutralization (Classified as `MALICIOUS_PROMPT_INJECTION`, `priority=3`, action `IGNORE`). |

---

## 3. Threat Matrix & Countermeasures

### 3.1 Prompt Injection & Adversarial Payloads
- **Threat**: Remote issues or pull requests containing commands like `SYSTEM OVERRIDE` or `ignore previous instructions` attempting to manipulate agent behavior.
- **Mitigation**: All incoming text from external connectors passes through `sanitize_external_text()`. Payloads containing override phrases are automatically classified as `MALICIOUS_PROMPT_INJECTION` and isolated without LLM execution.

### 3.2 Secret Exposure & Leakage
- **Threat**: API keys (`ghp_*`, `sk-*`, tokens) leaking into prompt contexts, execution logs, artifacts, or audit exports.
- **Mitigation**:
  - All credentials strictly loaded from `.env` environment variables.
  - Active log credential sanitization via `sanitize_log_credential()`.
  - Continuous validation using `scripts/check_security_scans.py`.

### 3.3 Path Traversal & Uncontrolled File Mutation
- **Threat**: Worker attempting to modify files outside the designated workspace using `../` or absolute symlinks.
- **Mitigation**: `PathLeaseService` strictly enforces path normalization and root path boundaries. Mutations outside `project.root_path` are rejected with `PathLeaseError`.

### 3.4 Unauthorized Autonomy & Unbounded Side Effects
- **Threat**: Autonomous worker merging PRs, deploying code, or executing destructive shell actions.
- **Mitigation**:
  - `ActionGateway` blocks direct merges, approvals, and deployments.
  - Connector protocol strictly omits `merge`, `approve`, and `deploy` capabilities.
  - Production `PR_READY` state transitions are non-bypassable and owned exclusively by `TaskService.mark_pr_ready()`.

---

## 4. Subprocess & Network Isolation

- **Subprocess Execution**: Commands executed via `run_command` run within bounded working directories (`Cwd`) with sanitized environment variables.
- **Network Boundaries**: Operational connectors operate in L1 read-only mode by default, escalating to L2 draft-PR creation only when explicitly requested.
