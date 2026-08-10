from __future__ import annotations

import scripts.run_benchmark_full_coverage as coverage_runner

from scripts.run_benchmark_full_coverage import (
    GateResult,
    _redact,
    _render_report,
    _artifact_status,
)


def test_full_coverage_report_keeps_missing_evidence_explicit() -> None:
    report = _render_report(
        run_id="test-run",
        gates=[
            GateResult("PA-001", "PASS", ["matrix.json"], "matrix ok"),
            GateResult("PA-007", "NOT_PROVEN", [], "browser evidence missing"),
        ],
        commands=[],
    )

    assert "**PARTIAL**" in report
    assert "PA-007" in report
    assert "NOT_PROVEN" in report
    assert "ACCEPTED" in report


def test_full_coverage_report_accepts_only_all_pass() -> None:
    report = _render_report(
        run_id="accepted-run",
        gates=[GateResult("PA-001", "PASS", ["matrix.json"], "ok")],
        commands=[],
    )

    assert "Veredito: **ACCEPTED**" in report


def test_full_coverage_redacts_runtime_secrets() -> None:
    import os

    previous = os.environ.get("CONTEXT7_API_KEY")
    os.environ["CONTEXT7_API_KEY"] = "ctx7-test-secret"
    try:
        assert "ctx7-test-secret" not in _redact("Authorization ctx7-test-secret")
        assert "[REDACTED]" in _redact("Authorization ctx7-test-secret")
    finally:
        if previous is None:
            os.environ.pop("CONTEXT7_API_KEY", None)
        else:
            os.environ["CONTEXT7_API_KEY"] = previous


def test_full_coverage_accepts_windows_utf8_bom_evidence(tmp_path) -> None:
    evidence = tmp_path / "helm-evidence.json"
    evidence.write_text('{"status": "PASS"}\n', encoding="utf-8-sig")

    assert _artifact_status(evidence) == "PASS"


def test_tool_resolves_npm_and_npx_cmd_wrappers_on_windows(monkeypatch) -> None:
    calls: list[str] = []

    def fake_which(name: str) -> str | None:
        calls.append(name)
        return f"C:/node/{name}" if name.endswith(".cmd") else None

    monkeypatch.setattr(coverage_runner.sys, "platform", "win32")
    monkeypatch.setattr(coverage_runner.shutil, "which", fake_which)

    assert coverage_runner._tool("npm") == "C:/node/npm.cmd"
    assert coverage_runner._tool("npx") == "C:/node/npx.cmd"
    assert calls == ["npm.cmd", "npx.cmd"]
