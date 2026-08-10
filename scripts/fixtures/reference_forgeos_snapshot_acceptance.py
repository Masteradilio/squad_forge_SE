"""Canonical behavioral acceptance for ForgeLedger release snapshots."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from app.forge_ledger import LedgerStore, add_entry, close_entry, export_snapshot


def test_reference_snapshot_contains_real_entries_and_summary_without_writes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.json"
        store = LedgerStore(path)
        first = add_entry(store, "First", 5)
        add_entry(store, "Second", 7)
        close_entry(store, first["id"])
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot = export_snapshot(store)
        assert list(snapshot) == ["entries", "summary"]
        assert [item["label"] for item in snapshot["entries"]] == ["First", "Second"]
        assert snapshot["summary"]["closed_entries"] == 1
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
