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
        data = {
            "entries": {str(k): v for k, v in self._entries.items()},
            "next_id": self._next_id,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_entry(self, label: str, amount: float) -> Dict[str, Any]:
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
        return [self._entries[k] for k in sorted(self._entries)]

    def close_entry(self, entry_id: int) -> Dict[str, Any]:
        if entry_id not in self._entries:
            raise KeyError(f"Entry not found: {entry_id}")
        self._entries[entry_id]["closed"] = True
        self._save()
        return self._entries[entry_id]

    def summarize(self) -> Dict[str, Any]:
        total = sum(e["amount"] for e in self._entries.values() if not e["closed"])
        return {
            "total_open": total,
            "count_open": sum(1 for e in self._entries.values() if not e["closed"]),
            "count_closed": sum(1 for e in self._entries.values() if e["closed"]),
        }

    def export_snapshot(self) -> str:
        return json.dumps({"entries": self.list_entries()}, indent=2)


def add_entry(store: LedgerStore, label: str, amount: float) -> Dict[str, Any]:
    return store.add_entry(label, amount)


def list_entries(store: LedgerStore) -> List[Dict[str, Any]]:
    return store.list_entries()


def close_entry(store: LedgerStore, entry_id: int) -> Dict[str, Any]:
    return store.close_entry(entry_id)


def summarize(store: LedgerStore) -> Dict[str, Any]:
    return store.summarize()


def export_snapshot(store: LedgerStore) -> str:
    return store.export_snapshot()
