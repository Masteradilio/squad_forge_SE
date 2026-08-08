"""Canonical behavioral acceptance for ForgeLedger validation and closing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.forge_ledger import LedgerStore, add_entry, close_entry, list_entries


def test_reference_validation_close_unknown_id_and_reopen() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.json"
        store = LedgerStore(path)
        with pytest.raises(ValueError):
            add_entry(store, "", 10)
        with pytest.raises(ValueError):
            add_entry(store, "Invalid", 0)
        with pytest.raises(ValueError):
            add_entry(store, "Invalid", True)  # type: ignore[arg-type]

        entry = add_entry(store, "Close me", 12)
        closed = close_entry(store, entry["id"])
        assert closed["closed"] is True
        assert list_entries(store)[0]["closed"] is True
        with pytest.raises(KeyError):
            close_entry(store, "missing")

        reopened = LedgerStore(path)
        assert list_entries(reopened)[0]["closed"] is True
