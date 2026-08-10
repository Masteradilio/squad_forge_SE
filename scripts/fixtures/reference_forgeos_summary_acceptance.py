"""Canonical behavioral acceptance for ForgeLedger summaries."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from app.forge_ledger import LedgerStore, add_entry, close_entry, summarize


def test_reference_summary_is_deterministic_and_non_mutating() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.json"
        store = LedgerStore(path)
        first = add_entry(store, "Open", 10)
        add_entry(store, "Closed", 20)
        close_entry(store, first["id"])
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = {
            "total_entries": 2,
            "open_entries": 1,
            "closed_entries": 1,
            "total_amount": 30,
        }
        assert summarize(store) == expected
        assert summarize(store) == expected
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
