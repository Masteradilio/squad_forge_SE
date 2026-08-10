from datetime import UTC, datetime

import pytest

from localforge.compliance.ci_pr_simulator import LocalCIState, build_signed_headers


def test_ci_pr_requires_signed_ordered_ci_and_human_review():
    now = datetime.now(UTC)
    secret = "test-secret"
    policy = {"external_triggers": {"local-ci": {"secret": secret}}}
    state = LocalCIState(provider="local-ci", commit_sha="sha-1")
    payload = {"commit_sha": "sha-1", "sequence": 1, "status": "PASS"}
    headers = build_signed_headers(secret=secret, event_id="event-1", timestamp=now, payload=payload)

    assert state.ingest(headers=headers, payload=payload, safety_policy=policy, now=now)["status"] == "PASS"
    assert state.pr_ready()["status"] == "BLOCKED"
    assert state.register_human_review("reviewer")["status"] == "APPROVED"
    assert state.pr_ready() == {
        "status": "PR_READY",
        "ci_status": "PASS",
        "review_actor": "reviewer",
        "merge_available": False,
        "reason": None,
    }

    with pytest.raises(ValueError, match="out of order"):
        state.ingest(
            headers=build_signed_headers(secret=secret, event_id="event-old", timestamp=now, payload=payload),
            payload=payload,
            safety_policy=policy,
            now=now,
        )

