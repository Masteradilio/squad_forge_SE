"""Acceptance fixture for real Tiny Ledger creation and listing."""

from app.tiny_ledger import add_entry, list_entries


def test_add_and_list_entry() -> None:
    store: list[dict[str, object]] = []
    entry = add_entry(store, "Design", 120)
    assert entry["label"] == "Design"
    assert entry["amount"] == 120
    assert entry["status"] == "pending"
    assert list_entries(store) == [entry]
