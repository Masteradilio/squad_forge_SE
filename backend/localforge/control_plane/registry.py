"""Project-level index for reconnecting durable ForgeOS goals.

The registry stores locations and authority metadata only. The control-plane
state and event journal remain the source of truth for execution decisions.
"""

from __future__ import annotations

import json
import builtins
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from localforge.control_plane.store import process_lock


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


class GoalRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_id: str
    workspace: str
    state_path: str
    source_revision: str | None = None
    authority: dict[str, str] = Field(default_factory=dict)
    active: bool = True
    created_at: str = Field(default_factory=_utc_iso)
    updated_at: str = Field(default_factory=_utc_iso)


class GoalRegistry:
    """Atomic project index used to reconnect a goal after process restart."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def list(self) -> builtins.list[GoalRegistryEntry]:
        with process_lock(self.lock_path):
            return self._read_unlocked()

    def get(self, goal_id: str) -> GoalRegistryEntry | None:
        return next((item for item in self.list() if item.goal_id == goal_id), None)

    def connect(
        self,
        *,
        goal_id: str,
        workspace: str | Path,
        state_path: str | Path,
        source_revision: str | None = None,
        authority: dict[str, str] | None = None,
    ) -> GoalRegistryEntry:
        """Create or refresh one goal location without changing task state."""

        with process_lock(self.lock_path):
            entries = self._read_unlocked()
            now = _utc_iso()
            existing = next((item for item in entries if item.goal_id == goal_id), None)
            if existing is None:
                existing = GoalRegistryEntry(
                    goal_id=goal_id,
                    workspace=str(Path(workspace).resolve()),
                    state_path=str(Path(state_path).resolve()),
                    source_revision=source_revision,
                    authority=dict(authority or {}),
                    updated_at=now,
                )
                entries.append(existing)
            else:
                existing.workspace = str(Path(workspace).resolve())
                existing.state_path = str(Path(state_path).resolve())
                existing.source_revision = source_revision
                existing.authority = dict(authority or existing.authority)
                existing.active = True
                existing.updated_at = now
            self._write_unlocked(entries)
            return existing

    def deactivate(self, goal_id: str) -> GoalRegistryEntry | None:
        with process_lock(self.lock_path):
            entries = self._read_unlocked()
            entry = next((item for item in entries if item.goal_id == goal_id), None)
            if entry is None:
                return None
            entry.active = False
            entry.updated_at = _utc_iso()
            self._write_unlocked(entries)
            return entry

    def _read_unlocked(self) -> builtins.list[GoalRegistryEntry]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw.get("goals", []) if isinstance(raw, dict) else raw
            if not isinstance(entries, list):
                raise ValueError("goals must be a list")
            return [GoalRegistryEntry.model_validate(item) for item in entries]
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid ForgeOS goal registry at {self.path}: {exc}") from exc

    def _write_unlocked(self, entries: builtins.list[GoalRegistryEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"schema_version": 1, "goals": [item.model_dump(mode="json") for item in entries]}
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.path.parent), delete=False
        ) as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            temporary = Path(handle.name)
        temporary.replace(self.path)
