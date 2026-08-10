import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.build_readme_claim_matrix import build_matrix, render_report, validate_matrix


def test_readme_matrix_has_stable_claims_and_evidence():
    matrix = build_matrix()

    validate_matrix(matrix)

    claims = matrix["claims"]
    assert len(claims) >= 15
    assert [claim["id"] for claim in claims] == [f"README-{index:03d}" for index in range(1, len(claims) + 1)]
    assert {claim["classification"] for claim in claims} == {
        "LIVE",
        "STRUCTURAL",
        "OPTIONAL",
        "NOT_PROVEN",
    }
    assert all(claim["evidence"] for claim in claims)
    assert "Claim-to-evidence matrix" in render_report(matrix)


def test_readme_matrix_rejects_missing_evidence():
    matrix = build_matrix()
    matrix["claims"][0]["evidence"] = []

    with pytest.raises(ValueError, match="evidence"):
        validate_matrix(matrix)


def test_readme_matrix_cli_writes_json_and_report(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_readme_claim_matrix.py",
            "--output-dir",
            str(tmp_path),
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    matrix = json.loads((tmp_path / "readme_claim_matrix.json").read_text(encoding="utf-8"))
    assert matrix["schema"] == "forgeos.readme_claim_matrix.v1"
    assert (tmp_path / "readme_claim_report.md").is_file()
