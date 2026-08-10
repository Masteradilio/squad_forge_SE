"""Acceptance fixture for Tiny Ledger validation and settlement."""

import pytest

from app.tiny_ledger import add_entry, settle_entry


def test_validate_and_settle_entry() -> None:
    store: list[dict[str, object]] = []
    with pytest.raises(ValueError):
        add_entry(store, "", 5)
    entry = add_entry(store, "Build", 30)
    settled = settle_entry(store, entry["id"])
    assert settled["status"] == "settled"
    with pytest.raises(KeyError):
        settle_entry(store, "missing")
