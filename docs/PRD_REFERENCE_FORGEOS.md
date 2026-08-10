# PRD - ForgeLedger reference product

## Purpose

Build a small, dependency-free Python library that demonstrates the complete
ForgeOS reference path: a PRD becomes bounded contracts, real behavioral tests,
durable product behavior, repair/review evidence, and a release manifest.

The product is intentionally small so the benchmark measures ForgeOS
governance and delivery evidence rather than framework installation.

## Product API

Create `app/forge_ledger.py` with this public API:

```python
class LedgerStore:
    def __init__(self, path: str | pathlib.Path): ...

def add_entry(store: LedgerStore, label: str, amount: int) -> dict: ...
def list_entries(store: LedgerStore) -> list[dict]: ...
def close_entry(store: LedgerStore, entry_id: int | str) -> dict: ...
def summarize(store: LedgerStore) -> dict: ...
def export_snapshot(store: LedgerStore) -> dict: ...
```

The JSON file is the product's durable store. No third-party runtime
dependency is required.

## Functional requirements

1. **Create and list entries**
   - `add_entry` rejects a blank label and creates a record with a positive,
     stable integer `id`, the supplied label and amount, `closed=False`, and a
     non-empty ISO-8601 `created_at` string.
   - IDs start at 1, preserve creation order, and remain stable after opening
     the same JSON file again.
   - `list_entries` returns records in creation order.

2. **Validate and close entries**
   - The amount must be a positive integer; booleans and non-integers are
     invalid.
   - `close_entry` changes only the selected entry and returns the updated
     record.
   - An unknown identifier, including a non-numeric value such as `"missing"`,
     raises `KeyError`, never a leaked conversion error.
   - Closing remains durable after reopening the store.

3. **Summarize without mutation**
   - `summarize` returns deterministic `total_entries`, `open_entries`,
     `closed_entries`, and `total_amount` values.
   - Calling it does not rewrite the JSON file.

4. **Export a release snapshot**
   - `export_snapshot` returns a JSON-serializable object containing the ordered
     entries and the summary, without mutating the store.
   - The release documentation identifies the public module and the canonical
     test command.

## Acceptance contract

- Production code is limited to `app/forge_ledger.py`.
- Canonical tests are:
  `tests/test_forge_ledger_create.py`,
  `tests/test_forge_ledger_validation.py`,
  `tests/test_forge_ledger_summary.py`, and
  `tests/test_forge_ledger_snapshot.py`.
- Acceptance tests must import and execute the real product API. Source-string
  checks and duplicated algorithms are not evidence.
- The full release worktree must pass `python -m pytest tests -q`.
- The scheduler must produce plan, diff, test, review, risk, cost, and PR
  evidence for the task contracts.
- The control plane completes only when all tasks are `PR_READY`.
- Human review remains required; no merge or deploy is part of this PRD.

## Workflow markers

The task contracts deliberately select the ForgeOS-native `grill-with-docs`,
`to-tickets`, and `tdd` skills. Their selection and manifests are recorded in
the conformance report; they do not authorize bypassing the Safety Kernel.
