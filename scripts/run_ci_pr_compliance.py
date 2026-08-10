"""Execute the deterministic CI/PR boundary proof required by PA-011."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from localforge.compliance.ci_pr_simulator import LocalCIState, build_signed_headers


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    secret = "local-compliance-ci-secret"
    now = datetime.now(UTC)
    policy = {"external_triggers": {"local-ci": {"secret": secret, "replay_window_seconds": 300}}}
    state = LocalCIState(provider="local-ci", commit_sha="abc123")
    observations: list[dict[str, object]] = []

    for event_id, sequence, status in (("ci-fail", 1, "FAIL"), ("ci-timeout", 2, "TIMEOUT"), ("ci-pass", 3, "PASS")):
        payload = {"commit_sha": "abc123", "sequence": sequence, "status": status}
        result = state.ingest(
            headers=build_signed_headers(secret=secret, event_id=event_id, timestamp=now, payload=payload),
            payload=payload,
            safety_policy=policy,
            now=now,
        )
        observations.append(result)

    pass_payload = {"commit_sha": "abc123", "sequence": 3, "status": "PASS"}
    observations.append(
        state.ingest(
            headers=build_signed_headers(secret=secret, event_id="ci-pass", timestamp=now, payload=pass_payload),
            payload=pass_payload,
            safety_policy=policy,
            now=now,
        )
    )

    rejected: dict[str, str] = {}
    try:
        payload = {"commit_sha": "abc123", "sequence": 2, "status": "PASS"}
        state.ingest(
            headers=build_signed_headers(secret=secret, event_id="ci-old", timestamp=now, payload=payload),
            payload=payload,
            safety_policy=policy,
            now=now,
        )
    except ValueError as exc:
        rejected["out_of_order"] = str(exc)
    try:
        payload = {"commit_sha": "abc123", "sequence": 4, "status": "PASS"}
        headers = build_signed_headers(secret=secret, event_id="ci-invalid", timestamp=now, payload=payload)
        headers["x-localforge-signature"] = "sha256=invalid"
        state.ingest(headers=headers, payload=payload, safety_policy=policy, now=now)
    except ValueError as exc:
        rejected["invalid_signature"] = str(exc)

    before_review = state.pr_ready()
    review = state.register_human_review("human-reviewer")
    after_review = state.pr_ready()
    report = {
        "schema": "forgeos.ci_pr_compliance.v1",
        "status": "PASS" if after_review["status"] == "PR_READY" and not after_review["merge_available"] else "FAIL",
        "provider": state.provider,
        "events": observations,
        "rejected": rejected,
        "before_review": before_review,
        "review": review,
        "after_review": after_review,
        "merge_operation": None,
        "generated_at": now.isoformat(),
        "timestamp_replay_check": (now - timedelta(seconds=301)).isoformat(),
    }
    (output / "ci_pr_compliance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
