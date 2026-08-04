# Phase R15 - HP12C Provider-Routing Retry

**Verdict: `BLOCKED_NEEDS_HUMAN_REVIEW`**

This phase records a real retry after the provider-aware Chief Engineer
routing fix. It is not an HP12C product acceptance claim.

## Observed Evidence

- Workspace: `samples/e2e-hp12c-platinum`.
- Inputs: `docs/PRD.md` and `docs/hp12c_platinum_design_target.png` only.
- Isolated database: `.localforge/retry.db`.
- PRD import: 7 epics and 19 tasks; all 19 were approved as `READY`.
- The Chief route sent `minimaxai/minimax-m3` to NVIDIA; no `auto/*` alias
  was sent to the NVIDIA endpoint.
- NVIDIA model discovery returned HTTP 200. Repair calls then encountered a
  timeout and HTTP 429. The configured OpenRouter fallback was invoked and
  returned HTTP 402 (`Insufficient credits`).
- SQLite recorded 4 failed paid calls, 0 completed task runs, and measured
  `US$0.0012` from the persisted pricing snapshot.
- Final run status: `BLOCKED_NEEDS_HUMAN_REVIEW`; 0 `PR_READY`, 0 generated
  product PRs, and 0 accepted calculator functions.

## Gate Decision

The provider-aware fallback behavior is verified by code tests and by the real
request trace. Product acceptance remains closed because the available paid
routes could not return a Chief Engineer repair plan. A funded and
rate-limit-available rerun from a clean database is required before evaluating
the generated frontend, PRs, visual parity, or ten complex HP12C functions.
