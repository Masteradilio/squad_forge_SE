from __future__ import annotations

from scripts.run_kubernetes_recovery_compliance import RUN_ID_RE, WORKER_SCRIPT


def test_recovery_profile_is_dns_safe_and_durable():
    assert RUN_ID_RE.fullmatch("20260807-235900")
    assert not RUN_ID_RE.fullmatch("bad/namespace")
    assert "/state/recovery.json" in WORKER_SCRIPT
    assert "receipt_count" in WORKER_SCRIPT

