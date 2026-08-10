"""Local CI/PR boundary simulator for PA-011.

This fixture exercises the same signed external-event validation used by the
runtime, while keeping merge authority outside ForgeOS. It is intentionally
small and deterministic so a compliance run can archive every accepted and
rejected transition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from localforge.services.external_events import (
    validate_external_event_envelope,
)


@dataclass
class LocalCIState:
    provider: str
    commit_sha: str
    status: str = "PENDING"
    last_sequence: int = 0
    review_actor: str | None = None
    seen_event_ids: set[str] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)

    def ingest(
        self,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        safety_policy: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        envelope = validate_external_event_envelope(
            loop_id=1,
            provider=self.provider,
            headers=headers,
            payload=payload,
            safety_policy=safety_policy,
            now=now,
        )
        sequence = int(payload.get("sequence", 0))
        if sequence <= self.last_sequence:
            if envelope.event_id in self.seen_event_ids:
                return {"status": "DUPLICATE", "event_id": envelope.event_id}
            raise ValueError("CI event sequence is out of order")
        if payload.get("commit_sha") != self.commit_sha:
            raise ValueError("CI event commit does not match the PR head")
        status = str(payload.get("status", "")).upper()
        if status not in {"PASS", "FAIL", "TIMEOUT"}:
            raise ValueError("CI status is invalid")
        self.last_sequence = sequence
        self.status = status
        self.seen_event_ids.add(envelope.event_id)
        record = {
            "event_id": envelope.event_id,
            "sequence": sequence,
            "status": status,
            "commit_sha": self.commit_sha,
            "verified": True,
        }
        self.events.append(record)
        return record

    def register_human_review(self, actor: str) -> dict[str, str]:
        if not actor.strip():
            raise ValueError("human review actor is required")
        self.review_actor = actor.strip()
        return {"actor": self.review_actor, "status": "APPROVED"}

    def pr_ready(self) -> dict[str, Any]:
        allowed = self.status == "PASS" and self.review_actor is not None
        return {
            "status": "PR_READY" if allowed else "BLOCKED",
            "ci_status": self.status,
            "review_actor": self.review_actor,
            "merge_available": False,
            "reason": None if allowed else "CI PASS and human review are required",
        }


def build_signed_headers(*, secret: str, event_id: str, timestamp: datetime, payload: dict[str, Any]) -> dict[str, str]:
    from localforge.services.external_events import sign_external_event

    return {
        "x-localforge-event-id": event_id,
        "x-localforge-timestamp": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "x-localforge-signature": sign_external_event(
            secret=secret,
            timestamp=timestamp,
            payload=payload,
        ),
    }

