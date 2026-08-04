import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class OperationalIdempotencyStore:
    """Small durable idempotency store for operational loop decisions."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path: Path | None
        if path is not None:
            self.path = Path(path)
        else:
            configured_path = os.getenv("LOCALFORGE_OPERATIONAL_STATE_PATH")
            # Tests retain isolated in-memory state unless they explicitly opt
            # into a file. Production loop decisions must survive restarts.
            if configured_path:
                self.path = Path(configured_path)
            elif "PYTEST_CURRENT_TEST" not in os.environ:
                self.path = Path(".localforge") / "operational_state.json"
            else:
                self.path = None
        self._memory: dict[str, Any] = {}

    def get(self, namespace: str, key: str) -> Any | None:
        data = self._read()
        namespace_data = data.get(namespace, {})
        if not isinstance(namespace_data, dict):
            return None
        return namespace_data.get(key)

    def set(self, namespace: str, key: str, value: Any) -> None:
        data = self._read()
        namespace_data = data.setdefault(namespace, {})
        if not isinstance(namespace_data, dict):
            namespace_data = {}
            data[namespace] = namespace_data
        namespace_data[key] = value
        self._write(data)

    def increment(self, namespace: str, key: str) -> int:
        current = self.get(namespace, key)
        value = int(current or 0) + 1
        self.set(namespace, key, value)
        return value

    def _read(self) -> dict[str, Any]:
        if self.path is None:
            return dict(self._memory)
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        if self.path is None:
            self._memory = dict(data)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.path.parent),
            delete=False,
        ) as handle:
            json.dump(data, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self.path)
