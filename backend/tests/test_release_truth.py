import json
import subprocess
from pathlib import Path
from typing import Any, cast

import scripts.check_release_truth as release_truth


def test_release_truth_script_passes_current_repository() -> None:
    report = release_truth.build_report(Path.cwd())
    historical_manifest = cast(dict[str, Any], report["historical_v61_manifest"])
    backlog = cast(dict[str, Any], report["backlog"])

    assert report["passed"] is True
    assert historical_manifest["verdict"] == "INVALID"
    assert backlog["unresolved_checkbox_count"] > 0
    assert report["accepted_final_manifests"] == []


def test_release_truth_detects_stable_claim_leak(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "claim.md").write_text(
        "This is a supervised-production-ready stable release.\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "docs/claim.md")
    _git(tmp_path, "commit", "-m", "claim")

    leaks = release_truth.stable_claim_leaks(tmp_path)

    assert leaks == [{"path": "docs/claim.md", "line": 1}]


def test_release_truth_detects_accepted_final_manifest_with_open_backlog(tmp_path: Path) -> None:
    (tmp_path / "docs" / "e2e" / "release").mkdir(parents=True)
    manifest_path = tmp_path / "docs" / "e2e" / "release" / "final_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "localforge.v6_2.final_manifest.v1",
                "verdict": "ACCEPTED",
            }
        ),
        encoding="utf-8",
    )

    accepted = release_truth.accepted_final_manifests(tmp_path)

    assert accepted == [{"path": "docs/e2e/release/final_manifest.json"}]


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.local")
    _git(path, "config", "user.name", "Test User")


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
