"""Canonical behavioral acceptance for ForgeLedger creation and persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.forge_ledger import LedgerStore, add_entry, list_entries


def test_reference_create_list_and_reopen() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.json"
        store = LedgerStore(path)
        first = add_entry(store, "Design review", 10)
        second = add_entry(store, "Release review", 25)
        assert first["id"] == 1
        assert second["id"] == 2
        assert first["closed"] is False
        assert isinstance(first["created_at"], str) and first["created_at"]
        assert [item["label"] for item in list_entries(store)] == [
            "Design review",
            "Release review",
        ]

        reopened = LedgerStore(path)
        assert [item["id"] for item in list_entries(reopened)] == [1, 2]
