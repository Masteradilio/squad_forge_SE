"""Durable, redacted trace and Python module profile helpers for full runs."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

_SECRET_KEY = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|secret|private[_-]?key)")
_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_ASSIGNMENT = re.compile(r"(?i)(\b(?:[a-z0-9_]*(?:api[_-]?key|token|password|secret)|authorization)\b\s*[:=]\s*)([\"']?)[^\s,;\"']+")
_URL_CREDENTIAL = re.compile(r"(?i)(://[^:/\s]+:)([^@/\s]+)(@)")


def redact_text(value: str, *, limit: int = 4000) -> str:
    """Redact credential-shaped strings before they reach trace artifacts."""

    text = _URL_CREDENTIAL.sub(r"\1[REDACTED]\3", str(value))
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _ASSIGNMENT.sub(r"\1[REDACTED]", text)
    return text[:limit] + ("…" if len(text) > limit else "")


def redact(value: Any, *, limit: int = 4000) -> Any:
    """Recursively redact mapping keys and text values for JSON-safe evidence."""

    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item, limit=limit) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(item, limit=limit) for item in value]
    if isinstance(value, str):
        return redact_text(value, limit=limit)
    if isinstance(value, (Path, bytes)):
        return redact_text(str(value), limit=limit)
    return value


class RunTraceRecorder:
    """Append ordered lifecycle events to a redacted JSONL trace."""

    def __init__(self, path: Path, *, run_id: str, root: Path | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.root = Path(root or Path.cwd()).resolve()
        self._sequence = 0
        self._lock = Lock()
        self._started = time.perf_counter()

    def emit(
        self,
        stage: str,
        event: str,
        *,
        status: str = "INFO",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            item = {
                "schema": "forgeos.run_trace.v1",
                "sequence": self._sequence,
                "run_id": self.run_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "elapsed_ms": round((time.perf_counter() - self._started) * 1000, 2),
                "pid": os.getpid(),
                "stage": stage,
                "event": event,
                "status": status,
                "payload": redact(payload or {}),
            }
            try:
                with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            except OSError:
                # Observability must not make the product run fail closed.
                pass
            return item

    @contextmanager
    def span(self, stage: str, name: str, *, payload: dict[str, Any] | None = None) -> Iterator[None]:
        started = time.perf_counter()
        self.emit(stage, f"{name}.start", payload=payload)
        try:
            yield
        except Exception as exc:
            self.emit(
                stage,
                f"{name}.end",
                status="FAIL",
                payload={"error_type": type(exc).__name__, "error": str(exc)},
            )
            raise
        else:
            self.emit(
                stage,
                f"{name}.end",
                status="PASS",
                payload={"duration_ms": round((time.perf_counter() - started) * 1000, 2)},
            )

    def write_json(self, path: Path, value: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(redact(value), indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass


class ModuleProfileCollector:
    """Profile imported and called repository Python files in one process."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self._previous = None
        self._records: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "functions": defaultdict(int), "unhandled": []})
        self._unhandled: list[dict[str, Any]] = []
        self._old_excepthook = sys.excepthook

    def _relative(self, filename: str | None) -> str | None:
        if not filename or filename.startswith("<"):
            return None
        try:
            return str(Path(filename).resolve().relative_to(self.root)).replace("\\", "/")
        except (OSError, ValueError):
            return None

    def _profile(self, frame: Any, event: str, _arg: Any) -> None:
        if event != "call":
            return
        relative = self._relative(frame.f_code.co_filename)
        if relative is None or not relative.endswith(".py"):
            return
        record = self._records[relative]
        record["calls"] += 1
        record["functions"][frame.f_code.co_qualname] += 1

    def _excepthook(self, exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        current = tb
        files: list[str] = []
        while current is not None:
            relative = self._relative(current.tb_frame.f_code.co_filename)
            if relative is not None:
                files.append(relative)
            current = current.tb_next
        item = {
            "type": exc_type.__name__,
            "message": redact_text(str(exc)),
            "files": files,
        }
        self._unhandled.append(item)
        self._old_excepthook(exc_type, exc, tb)

    def start(self) -> ModuleProfileCollector:
        self._previous = sys.getprofile()
        sys.setprofile(self._profile)
        sys.excepthook = self._excepthook
        return self

    def stop(self) -> dict[str, Any]:
        sys.setprofile(self._previous)
        sys.excepthook = self._old_excepthook
        imported: set[str] = set()
        for module in list(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            relative = self._relative(filename)
            if relative is not None and relative.endswith(".py"):
                imported.add(relative)
                self._records[relative]
        records: list[dict[str, Any]] = []
        for relative in sorted(self._records):
            raw = self._records[relative]
            records.append(
                {
                    "path": relative,
                    "imported": relative in imported,
                    "calls": int(raw["calls"]),
                    "functions": dict(sorted(raw["functions"].items())),
                    "unhandled_exceptions": list(raw["unhandled"]),
                }
            )
        return {
            "schema": "forgeos.module_profile.v1",
            "root": str(self.root),
            "records": records,
            "unhandled_exceptions": list(self._unhandled),
        }

    def write(self, path: Path) -> dict[str, Any]:
        result = self.stop()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(redact(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return result


def install_child_profile_hook(path: Path) -> None:
    """Install a sitecustomize hook for child Python processes."""

    source = r"""
import atexit, json, os, sys
from collections import defaultdict
from pathlib import Path

root = Path(os.environ.get("FORGEOS_TRACE_PROFILE_ROOT", ".")).resolve()
root_prefix = str(root).replace("\\", "/").rstrip("/").lower() + "/"
output = Path(os.environ.get("FORGEOS_TRACE_PROFILE_DIR", "."))
records = defaultdict(lambda: {"calls": 0, "functions": defaultdict(int)})
unhandled_exceptions = []

def relative(filename):
    if not filename or filename.startswith("<"):
        return None
    normalized = str(filename).replace("\\", "/")
    if not normalized.lower().startswith(root_prefix):
        return None
    return normalized[len(root_prefix):]

def profile(frame, event, _arg):
    if event != "call":
        return
    rel = relative(frame.f_code.co_filename)
    if rel and rel.endswith(".py"):
        records[rel]["calls"] += 1
        records[rel]["functions"][frame.f_code.co_qualname] += 1

def excepthook(exc_type, exc, tb):
    files = []
    current = tb
    while current is not None:
        rel = relative(current.tb_frame.f_code.co_filename)
        if rel:
            files.append(rel)
        current = current.tb_next
    unhandled_exceptions.append({"type": exc_type.__name__, "message": str(exc)[:4000], "files": files})
    sys.__excepthook__(exc_type, exc, tb)

def dump():
    imported = set()
    for module in list(sys.modules.values()):
        rel = relative(getattr(module, "__file__", None))
        if rel and rel.endswith(".py"):
            imported.add(rel)
            records[rel]
    payload = {
        "schema": "forgeos.module_profile.v1",
        "pid": os.getpid(),
        "unhandled_exceptions": unhandled_exceptions,
        "records": [
            {
                "path": rel,
                "imported": rel in imported,
                "calls": int(raw["calls"]),
                "functions": dict(raw["functions"]),
                "unhandled_exceptions": [],
            }
            for rel, raw in sorted(records.items())
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / f"process-{os.getpid()}.json").write_text(json.dumps(payload), encoding="utf-8")

sys.setprofile(profile)
sys.excepthook = excepthook
atexit.register(dump)
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.strip() + "\n", encoding="utf-8")
