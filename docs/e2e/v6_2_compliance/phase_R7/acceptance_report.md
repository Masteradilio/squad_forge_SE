# LocalForge OS V6.2 Phase R7 Deep Swarm Mutation Gate Report

## Verdict

`EVIDENCE_READY`

Phase R7 candidate hardening requires every agent-proposed Deep Swarm graph
mutation to reference a registered `decision_contract_id` in its payload. The
service validates that the active Deep Swarm run owns the graph, is enabled for
expansion, has remaining budgets, and that the contract ID is present in
`run.policy.registered_decision_contract_ids`.

This is candidate evidence only. Final R7 acceptance still requires real
dynamic-node execution through `GovernedExecution`, per-node RunnerPool,
worktree, PathLease, ActionGateway, and typed dependency evidence.

## Implemented Controls

| Control | Evidence |
| --- | --- |
| Registered decision contract required | Agent mutations under Deep Swarm now fail if `payload.decision_contract_id` is missing. |
| Unregistered contract rejected | Agent mutations fail if the supplied contract ID is not registered in the run policy. |
| Stale mutation rejection preserved | Existing regression verifies `expected_graph_version` mismatch is rejected. |
| Experimental gating preserved | Deep Swarm remains disabled by default and requires explicit opt-in plus decision evidence. |

## Validation Commands

```text
python -m pytest backend/tests/test_phase9_task_graph.py -q
26 passed in 0.67s

python -m mypy backend/localforge/services/task_graph.py backend/tests/test_phase9_task_graph.py
Success: no issues found in 2 source files

python -m ruff check backend/localforge/services/task_graph.py backend/tests/test_phase9_task_graph.py
All checks passed!
```

## Remaining Acceptance Requirements

- Dynamic ready nodes are not yet dispatched through `GovernedExecution`.
- RunnerPool, worktree, PathLease, budget, and ActionGateway ownership is not
  yet persisted for every dynamic attempt.
- Typed dependency evidence is not yet required before a dynamic node becomes
  ready.
- Crash recovery does not yet reconcile graph version, queue, attempts, leases,
  artifacts, and external action state as one ownership set.
- Deep Swarm remains experimental and cannot be promoted before an accepted R9
  benchmark gate.
