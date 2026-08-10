from __future__ import annotations

import json

from scripts.run_security_runtime_probe import POD_PROBE, run_probe


def test_security_runtime_probe_is_redacted_and_fail_closed_without_kubectl(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.run_security_runtime_probe.shutil.which", lambda _: None)
    output = tmp_path / "runtime.json"
    assert run_probe(output) == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "NOT_PROVEN"
    assert "LOCALFORGE_API_TOKEN" not in json.dumps(payload)


def test_security_probe_does_not_embed_secret_values():
    assert "print(token)" not in POD_PROBE
    assert "LOCALFORGE_API_TOKEN" in POD_PROBE
