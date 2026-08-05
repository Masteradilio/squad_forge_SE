# Mini Control Plane PRD

## Goal

Produce a reviewable three-step work item using a durable goal, a dependency
frontier, bounded turns, typed receipts, and a repair handoff.

## Tasks

1. `MINI-001`: create the product skeleton.
2. `MINI-002`: add deterministic checks after `MINI-001`.
3. `MINI-003`: assemble review evidence after `MINI-002`.

## Non-negotiables

- A task cannot pass without a validated receipt.
- A failed check must produce a blocker and a repair handoff.
- A repaired task must be reopened before the next turn is claimed.
- The final state must remain reviewable after a process restart.
