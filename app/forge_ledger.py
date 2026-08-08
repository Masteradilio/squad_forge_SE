import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


class LedgerStore:
    """A persistent JSON-backed ledger for financial entries."""

    def __init__(self, path: str = "ledger.json") -> None:
        self.path = path
        self._entries: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        """Load entries from JSON if the file exists."""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries", {})
            self._entries = {int(k): v for k, v in entries.items()}
            self._next_id = data.get("next_id", (max(self._entries, default=0) + 1))
        else:
            self._entries = {}
            self._next_id = 1

    def _save(self) -> None:
        """Persist entries and next_id to JSON."""
        data = {
            "entries": {str(k): v for k, v in self._entries.items()},
            "next_id": self._next_id,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_entry(self, label: str, amount: float) -> Dict[str, Any]:
        """Add a new open entry and persist it."""
        if not label or not label.strip():
            raise ValueError("Label cannot be blank")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("Amount must be a positive number")
        entry_id = self._next_id
        self._next_id += 1
        created_at = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": entry_id,
            "label": label,
            "amount": amount,
            "closed": False,
            "created_at": created_at,
        }
        self._entries[entry_id] = entry
        self._save()
        return entry

    def list_entries(self) -> List[Dict[str, Any]]:
        """Return entries sorted by id."""
        return [self._entries[k] for k in sorted(self._entries)]

    def close_entry(self, entry_id: int) -> Dict[str, Any]:
        """Close an existing entry by id."""
        if entry_id not in self._entries:
            raise KeyError(f"Entry not found: {entry_id}")
        self._entries[entry_id]["closed"] = True
        self._save()
        return self._entries[entry_id]

    def summarize(self) -> Dict[str, Any]:
        """Return deterministic summary without mutating JSON."""
        all_entries = list(self._entries.values())
        total_amount = sum(entry["amount"] for entry in all_entries)
        open_entries = sum(1 for entry in all_entries if not entry["closed"])
        closed_entries = sum(1 for entry in all_entries if entry["closed"])
        return {
            "total_entries": len(all_entries),
            "open_entries": open_entries,
            "closed_entries": closed_entries,
            "total_amount": total_amount,
        }


def add_entry(store: LedgerStore, label: str, amount: float) -> Dict[str, Any]:
    """Add an entry to the store and return it."""
    return store.add_entry(label, amount)


def list_entries(store: LedgerStore) -> List[Dict[str, Any]]:
    """Return entries from the store sorted by id."""
    return store.list_entries()


def close_entry(store: LedgerStore, entry_id: int) -> Dict[str, Any]:
    """Close an entry in the store by id."""
    return store.close_entry(entry_id)


def summarize(store: LedgerStore) -> Dict[str, Any]:
    """Return summary from the store."""
    return store.summarize()


def export_snapshot(store: LedgerStore) -> Dict[str, Any]:
    """Export a snapshot with ordered entries and summary without writing to disk."""
    return {
        "entries": store.list_entries(),
        "summary": store.summarize(),
    }
