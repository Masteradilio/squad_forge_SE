"""Exercise approval identity, expiration, idempotency and tenant boundaries."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import localforge.cli.control as control_cli  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from localforge.api.app import create_app  # noqa: E402
from localforge.models import domain  # noqa: E402
from localforge.models.enums import ActionApprovalStatus, ActionKind, AuditEventType  # noqa: E402
from localforge.services.tenant_context import TenantContext, bind_context, reset_context  # noqa: E402
from localforge.storage import UnitOfWork  # noqa: E402
from localforge.storage.bootstrap import bootstrap_database  # noqa: E402
from localforge.storage.database import DatabaseManager  # noqa: E402


async def _seed(manager: DatabaseManager, tenant: str, project_id: int | None = None, *, expired: bool = False) -> tuple[int, int]:
    token = bind_context(TenantContext(tenant_id=tenant, user_id="seed-user"))
    try:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None and uow.safety is not None
            if project_id is None:
                project = await uow.projects.create_project(
                    domain.Project(name=f"{tenant} project", root_path=f"/tmp/{tenant}", default_branch="main")
                )
                project_id = project.id
            approval = await uow.safety.create_approval(
                domain.ActionApproval(
                    project_id=project_id,
                    action_kind=ActionKind.RUN_COMMAND,
                    payload={"command": "pytest"},
                    purpose="run the verified test suite",
                    risk_level="medium",
                    expires_at=datetime.now(UTC) + timedelta(seconds=-1 if expired else 300),
                )
            )
            await uow.commit()
            return project_id, approval.id
    finally:
        reset_context(token)


async def _inspect_decision(
    manager: DatabaseManager,
    tenant: str,
    project_id: int,
    approval_id: int,
    *,
    approver_id: str,
    reason: str,
    idempotency_key: str,
) -> dict[str, object]:
    token = bind_context(TenantContext(tenant_id=tenant, user_id="compliance-reader"))
    try:
        async with UnitOfWork(manager, read_only=True) as uow:
            assert uow.safety is not None and uow.audits is not None
            approval = await uow.safety.get_approval(approval_id)
            events = await uow.audits.list_audit_events_for_project(project_id)
            matching_events = [
                event
                for event in events
                if event.event_type == AuditEventType.SAFETY_DECISION
                and event.payload_redacted.get("approval_id") == approval_id
            ]
            audit_event = matching_events[0] if matching_events else None
            approval_matches = (
                approval is not None
                and approval.status == ActionApprovalStatus.APPROVED
                and approval.decided_by == approver_id
                and approval.decision_reason == reason
                and approval.idempotency_key == idempotency_key
            )
            audit_matches = (
                audit_event is not None
                and audit_event.actor_id == approver_id
                and audit_event.payload_redacted.get("status") == ActionApprovalStatus.APPROVED.value
                and audit_event.payload_redacted.get("idempotency_key") == idempotency_key
                and audit_event.payload_redacted.get("reason") == reason
            )
            return {
                "status": approval.status.value if approval else None,
                "approver_id": approval.decided_by if approval else None,
                "reason": approval.decision_reason if approval else None,
                "idempotency_key": approval.idempotency_key if approval else None,
                "audit_found": audit_event is not None,
                "audit_count": len(matching_events),
                "audit_actor_id": audit_event.actor_id if audit_event else None,
                "passed": approval_matches and audit_matches and len(matching_events) == 1,
            }
    finally:
        reset_context(token)


def _invoke_cli_decision(
    manager: DatabaseManager,
    approval_id: int,
    *,
    tenant_id: str,
    approver_id: str,
    reason: str,
    idempotency_key: str,
) -> None:
    original_manager = control_cli.db_manager
    control_cli.db_manager = manager
    try:
        control_cli.safety_decide_cmd(
            approval_id,
            "approve",
            approver_id=approver_id,
            idempotency_key=idempotency_key,
            reason=reason,
            tenant_id=tenant_id,
        )
        control_cli.safety_decide_cmd(
            approval_id,
            "approve",
            approver_id=approver_id,
            idempotency_key=idempotency_key,
            reason=reason,
            tenant_id=tenant_id,
        )
    finally:
        control_cli.db_manager = original_manager


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "approval.db"
    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    asyncio.run(bootstrap_database(manager))
    try:
        project_id, approval_id = asyncio.run(_seed(manager, "tenant-a"))
        _, expired_id = asyncio.run(_seed(manager, "tenant-a", project_id, expired=True))
        cli_project_id, cli_approval_id = asyncio.run(_seed(manager, "tenant-cli"))
        app = create_app(manager)
        with TestClient(app) as client:
            api_token = os.getenv("LOCALFORGE_API_TOKEN")
            auth_headers = {"authorization": f"Bearer {api_token}"} if api_token else {}
            headers_a = {
                "x-tenant-id": "tenant-a",
                "x-user-id": "alice",
                "x-approver-id": "alice",
                "x-idempotency-key": "approval-once-1",
                "x-approval-reason": "reviewed locally",
            }
            headers_a.update(auth_headers)
            approved = client.post(f"/safety/approvals/{approval_id}/approve", headers=headers_a)
            replayed = client.post(f"/safety/approvals/{approval_id}/approve", headers=headers_a)
            expired_headers = {
                "x-tenant-id": "tenant-a",
                "x-user-id": "alice",
                "x-approver-id": "alice",
                **auth_headers,
            }
            expired = client.post(
                f"/safety/approvals/{expired_id}/approve",
                headers=expired_headers,
            )
            cross_tenant_headers = {
                "x-tenant-id": "tenant-b",
                "x-user-id": "bob",
                "x-approver-id": "bob",
                **auth_headers,
            }
            cross_tenant = client.post(
                f"/safety/approvals/{approval_id}/approve",
                headers=cross_tenant_headers,
            )

        api_persisted = asyncio.run(
            _inspect_decision(
                manager,
                "tenant-a",
                project_id,
                approval_id,
                approver_id="alice",
                reason="reviewed locally",
                idempotency_key="approval-once-1",
            )
        )
        api_status = (
            approved.status_code == 200
            and replayed.status_code == 200
            and replayed.json().get("idempotency_key") == "approval-once-1"
            and expired.status_code == 409
            and cross_tenant.status_code == 404
            and bool(api_persisted["passed"])
        )

        cli_tenant = "tenant-cli"
        cli_approver_id = "cli-auditor"
        cli_reason = "CLI compliance decision"
        cli_idempotency_key = "cli-approval-once-1"
        cli_error: str | None = None
        try:
            _invoke_cli_decision(
                manager,
                cli_approval_id,
                tenant_id=cli_tenant,
                approver_id=cli_approver_id,
                reason=cli_reason,
                idempotency_key=cli_idempotency_key,
            )
        except Exception as exc:  # pragma: no cover - report failure is the assertion
            cli_error = type(exc).__name__
        cli_persisted = asyncio.run(
            _inspect_decision(
                manager,
                cli_tenant,
                cli_project_id,
                cli_approval_id,
                approver_id=cli_approver_id,
                reason=cli_reason,
                idempotency_key=cli_idempotency_key,
            )
        )
        cli_status = cli_error is None and bool(cli_persisted["passed"])
        api_evidence = {
            "status": "PASS" if api_status else "FAIL",
            "decision_status": approved.status_code,
            "replay_status": replayed.status_code,
            "expiry_status": expired.status_code,
            "cross_tenant_status": cross_tenant.status_code,
            "persisted": api_persisted,
        }
        cli_evidence = {
            "status": "PASS" if cli_status else "FAIL",
            "invocation": "safety_decide_cmd",
            "tenant_id": cli_tenant,
            "approval_id": cli_approval_id,
            "replay": "PASS" if cli_error is None else "FAIL",
            "error": cli_error,
            "persisted": cli_persisted,
        }
        report = {
            "schema": "forgeos.approval_compliance.v1",
            "status": "PASS" if api_status and cli_status else "FAIL",
            "api_status": "PASS" if api_status else "FAIL",
            "cli_status": "PASS" if cli_status else "FAIL",
            "api": api_evidence,
            "cli": cli_evidence,
            "approved": approved.json() if approved.status_code == 200 else {"status_code": approved.status_code},
            "replayed_status": replayed.status_code,
            "expired_status": expired.status_code,
            "cross_tenant_status": cross_tenant.status_code,
            "project_id": project_id,
            "approval_id": approval_id,
        }
    finally:
        asyncio.run(manager.close())
    (output / "approval_compliance.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
