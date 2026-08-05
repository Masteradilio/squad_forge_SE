import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Iterator

from localforge.control_plane.contracts import ControlPlaneState, utc_iso


class RevisionConflict(RuntimeError):
    """Raised when a stale worker attempts to overwrite control-plane state."""


@contextmanager
def _process_lock(path: Path) -> Iterator[None]:
    """Serialize writers across threads and local processes on Windows/Linux."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            flock = getattr(fcntl, "flock")
            flock(handle.fileno(), getattr(fcntl, "LOCK_EX"))
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                flock = getattr(fcntl, "flock")
                flock(handle.fileno(), getattr(fcntl, "LOCK_UN"))


# Public alias for small control-plane indexes that need the same cross-process
# lock without becoming another source of task state.
process_lock = _process_lock


class ControlPlaneStore:
    """Schema-versioned atomic state journal for one bounded ForgeOS run."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.events_path = self.path.with_suffix(".events.jsonl")

    def read(self) -> ControlPlaneState | None:
        with _process_lock(self.lock_path):
            return self._read_unlocked()

    def update(
        self,
        mutate: Callable[[ControlPlaneState | None], ControlPlaneState],
        *,
        expected_revision: int | None = None,
        operation_id: str | None = None,
    ) -> ControlPlaneState:
        with _process_lock(self.lock_path):
            current = self._read_unlocked()
            if (
                expected_revision is not None
                and current is not None
                and current.revision != expected_revision
            ):
                raise RevisionConflict(
                    f"expected revision {expected_revision}, found {current.revision}"
                )
            if current is not None and operation_id:
                if operation_id in current.applied_operations:
                    return current
            original = current.model_copy(deep=True) if current is not None else None
            updated = mutate(current)
            if original is not None and self._equivalent_ignoring_clocks(original, updated):
                return original
            if original is not None:
                updated.revision = original.revision + 1
            if operation_id:
                updated.applied_operations[operation_id] = updated.revision
            updated.goal.updated_at = utc_iso()
            self._write_unlocked(updated)
            self._append_event_unlocked(updated, operation_id)
            return updated

    @staticmethod
    def _equivalent_ignoring_clocks(
        left: ControlPlaneState, right: ControlPlaneState
    ) -> bool:
        """Avoid journal growth when a scheduler only reprojects unchanged state."""
        left_data = left.model_dump(mode="json")
        right_data = right.model_dump(mode="json")
        left_data.get("goal", {}).pop("updated_at", None)
        right_data.get("goal", {}).pop("updated_at", None)
        for data in (left_data, right_data):
            for todo in data.get("todos", []):
                if isinstance(todo, dict):
                    todo.pop("updated_at", None)
        return left_data == right_data

    def replay(self) -> ControlPlaneState | None:
        """Return the latest state after validating the journal hash chain."""
        with _process_lock(self.lock_path):
            if not self.events_path.exists():
                return None
            latest: ControlPlaneState | None = None
            previous_hash: str | None = None
            try:
                for line in self.events_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    state_payload = record["state"]
                    canonical = json.dumps(
                        state_payload, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                    if record.get("state_hash") != hashlib.sha256(canonical).hexdigest():
                        raise RuntimeError("control-plane event state hash mismatch")
                    recorded_previous = record.get("previous_hash")
                    if recorded_previous is not None and recorded_previous != previous_hash:
                        raise RuntimeError("control-plane event hash chain mismatch")
                    latest = ControlPlaneState.model_validate(record["state"])
                    previous_hash = hashlib.sha256(line.rstrip().encode("utf-8")).hexdigest()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise RuntimeError(
                    f"Invalid control-plane event journal at {self.events_path}: {exc}"
                ) from exc
            return latest

    def verify_replay(self) -> bool:
        """Verify that the append-only journal agrees with the live snapshot."""
        try:
            current = self.read()
            replayed = self.replay()
        except RuntimeError:
            return False
        if current is None or replayed is None:
            return current is None and replayed is None
        return current.model_dump(mode="json") == replayed.model_dump(mode="json")

    def event_records(self) -> list[dict[str, object]]:
        """Read journal metadata without exposing a second mutable state store."""
        with _process_lock(self.lock_path):
            if not self.events_path.exists():
                return []
            records: list[dict[str, object]] = []
            for line in self.events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        records.append(
                            {
                                key: value[key]
                                for key in (
                                    "event_id",
                                    "revision",
                                    "operation_id",
                                    "event_type",
                                    "state_hash",
                                    "previous_hash",
                                    "created_at",
                                )
                                if key in value
                            }
                        )
            return records

    def _read_unlocked(self) -> ControlPlaneState | None:
        if not self.path.exists():
            return None
        try:
            return ControlPlaneState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Invalid control-plane state at {self.path}: {exc}") from exc

    def _write_unlocked(self, state: ControlPlaneState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = state.model_dump_json(indent=2)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.path.parent), delete=False
        ) as handle:
            handle.write(payload)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(self.path)

    def _append_event_unlocked(
        self, state: ControlPlaneState, operation_id: str | None
    ) -> None:
        state_payload = state.model_dump(mode="json")
        canonical = json.dumps(
            state_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        record = {
            "schema_version": 1,
            "event_id": f"event-{uuid.uuid4().hex}",
            "revision": state.revision,
            "operation_id": operation_id,
            "event_type": (operation_id or "state_update").split(":", 1)[0],
            "state_hash": hashlib.sha256(canonical).hexdigest(),
            "previous_hash": self._last_event_hash_unlocked(),
            "created_at": utc_iso(),
            "state": state_payload,
        }
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _last_event_hash_unlocked(self) -> str | None:
        if not self.events_path.exists():
            return None
        lines = self.events_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if line.strip():
                return hashlib.sha256(line.rstrip().encode("utf-8")).hexdigest()
        return None
