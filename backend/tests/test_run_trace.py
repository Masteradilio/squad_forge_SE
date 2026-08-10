from __future__ import annotations

import json
import sys
from pathlib import Path

from localforge.observability.run_trace import ModuleProfileCollector, RunTraceRecorder, redact


def test_trace_is_ordered_and_redacts_credentials(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    recorder = RunTraceRecorder(path, run_id="run-test", root=tmp_path)
    recorder.emit("stage", "start", payload={"api_key": "secret-value", "message": "Bearer abc123"})
    recorder.emit("stage", "end", status="PASS", payload={"authorization": "Bearer token-value"})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[0]["payload"]["api_key"] == "[REDACTED]"
    assert "abc123" not in json.dumps(rows)


def test_redact_recurses_through_nested_values() -> None:
    payload = redact({"nested": [{"password": "pw"}], "url": "http://u:p@localhost:1"})
    assert payload["nested"][0]["password"] == "[REDACTED]"
    assert "p@" not in payload["url"]


def test_module_profile_records_imported_and_called_files(tmp_path: Path) -> None:
    module_file = tmp_path / "observed.py"
    module_file.write_text("def invoked():\n    return 1\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    collector = ModuleProfileCollector(tmp_path).start()
    try:
        import observed  # type: ignore[import-not-found]

        assert observed.invoked() == 1
    finally:
        profile = collector.stop()
        sys.path.remove(str(tmp_path))
        sys.modules.pop("observed", None)
    item = next(record for record in profile["records"] if record["path"] == "observed.py")
    assert item["imported"] is True
    assert item["calls"] >= 1
