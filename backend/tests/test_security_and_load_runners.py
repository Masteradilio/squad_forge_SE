from __future__ import annotations

from scripts.run_load_benchmark import run_probe


def test_load_probe_rejects_invalid_bounds_without_network() -> None:
    payload = run_probe("http://127.0.0.1:1/ready", requests=2, concurrency=1, timeout=0.01)
    assert payload["requests"] == 2
    assert payload["status"] == "PARTIAL"
    assert payload["successful_responses"] == 0
