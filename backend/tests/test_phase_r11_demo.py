import hashlib
import json
from pathlib import Path

from localforge.demo import run_ci_regression_demo


def test_deterministic_demo_exports_sanitized_replay_with_valid_checksums(tmp_path: Path) -> None:
    output = tmp_path / "demo"

    demo = run_ci_regression_demo(output)

    assert demo.status == "PR_READY"
    payload = json.loads((output / "demo_run.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "localforge.v6_2.demo_run.v1"
    assert payload["model_calls"] == 0
    assert payload["paid_api_calls"] == 0
    assert payload["worker_output_mode"] == "deterministic_replay_not_live_model"
    assert (output / "demo_replay.html").is_file()
    assert not (output / "repo").exists()
    assert not (output / "worktrees").exists()

    serialized = json.dumps(payload, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "OPENROUTER_API_KEY" not in serialized

    for relative_path, expected_hash in payload["checksums"].items():
        actual_hash = hashlib.sha256((output / relative_path).read_bytes()).hexdigest()
        assert actual_hash == expected_hash

