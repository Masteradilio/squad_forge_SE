"""Acceptance fixture for the real Tiny Ledger summary function."""

from app.tiny_ledger import add_entry, settle_entry, summarize


def test_summary_is_deterministic_and_non_mutating() -> None:
    store: list[dict[str, object]] = []
    first = add_entry(store, "One", 10)
    second = add_entry(store, "Two", 20)
    settle_entry(store, first["id"])
    before = [dict(entry) for entry in store]
    assert summarize(store) == {"total": 30, "settled": 10, "pending": 20}
    assert store == before
    assert second["status"] == "pending"
