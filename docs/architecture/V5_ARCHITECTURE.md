# LocalForge V5 Architecture

## Product boundary

LocalForge is a software-engineering control plane. Models propose work; deterministic
services own state transitions, permissions, budgets, Git isolation, validation, and audit.

```text
PRD -> compiler -> task contracts -> deterministic scheduler
                                      |-> local worker lane
                                      |-> OmniRoute economy lane
                                      |-> direct free-provider fallbacks
                                      |-> paid API critical lane / fallback
                                      |-> deterministic validation
                                  evidence -> human-reviewed PR
```

## Core invariants

- The generic runtime contains no benchmark-domain implementation.
- A model cannot directly mutate task state or bypass the Safety Kernel.
- API calls receive scoped evidence and are budgeted and attributed.
- Provider fallback handles timeout, connection, rate-limit, and server failures,
  not invalid credentials, billing, model selection, or contract errors.
- The paid API critical lane is explicit, budgeted, circuit-protected, and
  visible in the model-call ledger; it is not a guarantee that product gates
  will pass. Direct free-provider fallbacks are bounded and ordered after the
  configured economy route.
- `PR_READY` requires deterministic evidence but is not itself product acceptance.
- Human review remains required before merge.

## Extension boundaries

- **Providers** implement the LLM provider contract and normalized failure types.
- **Runners** implement isolated task execution.
- **Sandboxes** enforce filesystem, command, and network boundaries.
- **Skills** describe role procedures; they do not override policy.
- **Evaluators** live outside the runtime and consume public artifacts/contracts.

## Maintainability direction

The current pipeline, API, and frontend shell predate these boundaries and remain larger than
desired. V5 extracts policy and construction services first, then route groups and feature
views, while preserving public API behavior.
