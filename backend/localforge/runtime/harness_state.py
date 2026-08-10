"""Durable, local-first state for the bounded agent harness.

The harness state is intentionally data-only.  It stores prompts, memory,
skills, and subagent metadata, but it never imports or executes an entrypoint.
Every mutation is serialized with a process lock and writes a rollback
snapshot before replacing the live JSON document.
"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator, Literal

from pydantic import BaseModel, Field, model_validator


HarnessEntryKind = Literal["prompt", "memory", "skill", "subagent"]
HarnessScope = Literal["local", "project", "global"]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


@contextmanager
def _process_lock(path: Path) -> Iterator[None]:
    """Serialize state reads and writes across local processes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class HarnessEntry(BaseModel):
    """One durable harness entry.

    ``supplemental`` distinguishes additive harness context from a base
    entry.  System prompts are explicitly marked and are always treated as
    non-supplemental, so refinement cannot overwrite them.
    """

    id: str = Field(min_length=1)
    kind: HarnessEntryKind
    scope: HarnessScope
    content: Any = ""
    supplemental: bool = True
    is_system_prompt: bool = False
    is_base: bool = False
    source: str = "manual"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_field_names(cls, value: Any) -> Any:
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return value
        values = dict(value)
        if "id" not in values and "entry_id" in values:
            values["id"] = values["entry_id"]
        if "content" not in values and "value" in values:
            values["content"] = values["value"]
        if "supplemental" not in values and "is_supplemental" in values:
            values["supplemental"] = values["is_supplemental"]
        if "is_base" not in values and "base" in values:
            values["is_base"] = values["base"]
        if "is_system_prompt" not in values:
            if "is_system" in values:
                values["is_system_prompt"] = values["is_system"]
            elif isinstance(values.get("system_prompt"), bool):
                values["is_system_prompt"] = values["system_prompt"]
            elif isinstance(values.get("system_prompt"), str):
                values.setdefault("content", values["system_prompt"])
                values["is_system_prompt"] = True
        if values.get("is_system_prompt") and "supplemental" not in values:
            values["supplemental"] = False
        if (
            values.get("kind") == "prompt"
            and "supplemental" not in values
            and "is_system_prompt" not in values
        ):
            values["supplemental"] = False
            values["is_system_prompt"] = True
        return values

    @model_validator(mode="after")
    def _validate_protection_flags(self) -> "HarnessEntry":
        if not self.id.strip():
            raise ValueError("harness entry id must not be blank")
        if (self.is_system_prompt or self.is_base) and self.supplemental:
            self.supplemental = False
        return self

    @property
    def entry_id(self) -> str:
        """Compatibility alias for callers that use the descriptive name."""

        return self.id

    @property
    def value(self) -> Any:
        """Compatibility alias for the JSON value held by the entry."""

        return self.content

    @property
    def is_supplemental(self) -> bool:
        return self.supplemental

    @property
    def system_prompt(self) -> bool:
        return self.is_system_prompt


class RefinementEvent(BaseModel):
    """Evidence and changes recorded by one harness refinement."""

    id: str = Field(default_factory=lambda: _new_id("refinement"), min_length=1)
    entry_id: str = Field(min_length=1)
    evidence: dict[str, Any]
    changes: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now)


class HarnessStateDocument(BaseModel):
    """On-disk schema for ``harness_state.json``."""

    schema_version: int = 1
    revision: int = Field(default=0, ge=0)
    entries: list[HarnessEntry] = Field(default_factory=list)
    refinements: list[RefinementEvent] = Field(default_factory=list)
    snapshot_files: list[str] = Field(default_factory=list)


class HarnessState:
    """CRUD store for durable, project-scoped harness state."""

    _REFINABLE_FIELDS = {"content", "metadata", "source"}

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.harness_dir = self._within_root(self.project_root / ".localforge" / "harness")
        self.state_path = self._within_root(self.harness_dir / "harness_state.json")
        self.lock_path = self._within_root(self.harness_dir / "harness_state.lock")
        self.snapshot_dir = self._within_root(self.harness_dir / "snapshots")
        self.snapshot_path = self._within_root(self.harness_dir / "harness_state.json.bak")

    @property
    def path(self) -> Path:
        """Compatibility alias for the durable state path."""

        return self.state_path

    def list(
        self,
        *,
        kind: HarnessEntryKind | None = None,
        scope: HarnessScope | None = None,
    ) -> list[HarnessEntry]:
        with _process_lock(self.lock_path):
            document = self._read_unlocked()
            return [
                entry.model_copy(deep=True)
                for entry in document.entries
                if (kind is None or entry.kind == kind)
                and (scope is None or entry.scope == scope)
            ]

    def list_entries(
        self,
        *,
        kind: HarnessEntryKind | None = None,
        scope: HarnessScope | None = None,
    ) -> list[HarnessEntry]:
        return self.list(kind=kind, scope=scope)

    def get(self, entry_id: str) -> HarnessEntry | None:
        with _process_lock(self.lock_path):
            document = self._read_unlocked()
            for entry in document.entries:
                if entry.id == entry_id:
                    return entry.model_copy(deep=True)
        return None

    def upsert(self, entry: HarnessEntry | dict[str, Any]) -> HarnessEntry:
        candidate = HarnessEntry.model_validate(entry)
        with _process_lock(self.lock_path):
            current = self._read_unlocked()
            snapshot_name = self._snapshot_unlocked(current)
            existing_index = next(
                (index for index, item in enumerate(current.entries) if item.id == candidate.id),
                None,
            )
            if existing_index is not None:
                existing = current.entries[existing_index]
                candidate.created_at = existing.created_at
            candidate.updated_at = _utc_now()
            updated = current.model_copy(deep=True)
            if existing_index is None:
                updated.entries.append(candidate)
            else:
                updated.entries[existing_index] = candidate
            self._commit_unlocked(current, updated, snapshot_name)
        return candidate.model_copy(deep=True)

    def delete(self, entry_id: str) -> bool:
        with _process_lock(self.lock_path):
            current = self._read_unlocked()
            existing_index = next(
                (index for index, item in enumerate(current.entries) if item.id == entry_id),
                None,
            )
            if existing_index is None:
                return False
            snapshot_name = self._snapshot_unlocked(current)
            updated = current.model_copy(deep=True)
            del updated.entries[existing_index]
            self._commit_unlocked(current, updated, snapshot_name)
        return True

    def refine(
        self,
        entry_id: str | HarnessEntry,
        evidence: dict[str, Any],
        updates: dict[str, Any] | None = None,
        *,
        content: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RefinementEvent:
        """Record evidence and optionally update one supplemental entry.

        Refinement is intentionally narrow: it can change only additive
        content, metadata, and source fields on a supplemental entry.  Base
        and system-prompt entries are rejected before any snapshot or write.
        """

        if not isinstance(evidence, dict):
            raise TypeError("refinement evidence must be a dictionary")
        resolved_id = entry_id.id if isinstance(entry_id, HarnessEntry) else entry_id
        if not isinstance(updates, (dict, type(None))):
            raise TypeError("refinement updates must be a dictionary")
        changes = dict(updates or {})
        if content is not None:
            changes["content"] = content
        if metadata is not None:
            changes["metadata"] = metadata
        if "value" in changes and "content" not in changes:
            changes["content"] = changes.pop("value")
        unknown = set(changes) - self._REFINABLE_FIELDS
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"refinement cannot mutate protected or unknown fields: {names}")

        with _process_lock(self.lock_path):
            current = self._read_unlocked()
            existing_index = next(
                (index for index, item in enumerate(current.entries) if item.id == resolved_id),
                None,
            )
            if existing_index is None:
                raise KeyError(f"harness entry not found: {resolved_id}")
            existing = current.entries[existing_index]
            if not existing.supplemental or existing.is_system_prompt or existing.is_base:
                raise ValueError("only supplemental harness entries may be refined")

            effective_changes = dict(changes)
            if "metadata" in effective_changes:
                if not isinstance(effective_changes["metadata"], dict):
                    raise TypeError("refinement metadata must be a dictionary")
                effective_changes["metadata"] = {
                    **existing.metadata,
                    **effective_changes["metadata"],
                }
            refined = HarnessEntry.model_validate(
                {
                    **existing.model_dump(mode="json"),
                    **effective_changes,
                    "updated_at": _utc_now(),
                }
            )
            event = RefinementEvent(
                entry_id=resolved_id,
                evidence=evidence,
                changes=effective_changes,
            )
            snapshot_name = self._snapshot_unlocked(current)
            updated = current.model_copy(deep=True)
            updated.entries[existing_index] = refined
            updated.refinements.append(event)
            self._commit_unlocked(current, updated, snapshot_name)
        return event.model_copy(deep=True)

    def list_refinements(self, entry_id: str | None = None) -> list[RefinementEvent]:
        with _process_lock(self.lock_path):
            document = self._read_unlocked()
            return [
                event.model_copy(deep=True)
                for event in document.refinements
                if entry_id is None or event.entry_id == entry_id
            ]

    def list_snapshots(self) -> list[Path]:
        with _process_lock(self.lock_path):
            if not self.snapshot_dir.is_dir():
                return []
            return sorted(self.snapshot_dir.glob("snapshot-*.json"))

    def _read_unlocked(self) -> HarnessStateDocument:
        if not self.state_path.exists():
            return HarnessStateDocument()
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return HarnessStateDocument(entries=raw)
        if not isinstance(raw, dict):
            raise ValueError(f"invalid harness state document at {self.state_path}")
        return HarnessStateDocument.model_validate(raw)

    def _snapshot_unlocked(self, document: HarnessStateDocument) -> str:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        existing_numbers = [
            int(path.stem.removeprefix("snapshot-"))
            for path in self.snapshot_dir.glob("snapshot-*.json")
            if path.stem.removeprefix("snapshot-").isdigit()
        ]
        number = max(existing_numbers, default=0) + 1
        name = f"snapshot-{number:06d}.json"
        payload = document.model_dump(mode="json")
        self._atomic_write_json(self.snapshot_dir / name, payload)
        self._atomic_write_json(self.snapshot_path, payload)
        return name

    def _commit_unlocked(
        self,
        current: HarnessStateDocument,
        updated: HarnessStateDocument,
        snapshot_name: str,
    ) -> None:
        updated.revision = current.revision + 1
        updated.snapshot_files = [*current.snapshot_files, snapshot_name]
        self._atomic_write_json(self.state_path, updated.model_dump(mode="json"))

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path = self._within_root(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _within_root(self, candidate: Path) -> Path:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"harness state path escapes project root: {candidate}") from exc
        return resolved


__all__ = [
    "HarnessEntry",
    "HarnessEntryKind",
    "HarnessScope",
    "HarnessState",
    "HarnessStateDocument",
    "RefinementEvent",
]
