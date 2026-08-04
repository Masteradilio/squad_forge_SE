import asyncio
import os

from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    ActionKind,
    AuditEventActorType,
    AuditEventType,
    AutonomyLevel,
    RunMode,
)
from localforge.safety.action_gateway import ActionGateway
from localforge.safety.kernel import ActionRequest, SafetyDecision, SafetyKernel
from localforge.services.security_controls import redact_secrets as redact_security_value
from localforge.storage import UnitOfWork

__all__ = ["SafetyKernel", "SafetyViolationError", "redact_secrets", "run_safe_command"]


class SafetyViolationError(Exception):
    """Raised when an action request violates security rules or is denied/timed out."""

    pass


def redact_secrets(text: str) -> str:
    """Scan and redact known sensitive tokens from command outputs."""
    if not text:
        return text

    sensitive_vars = [
        "LOCALFORGE_GITHUB_TOKEN",
        "LOCALFORGE_MODEL_API_KEY",
        "GITHUB_TOKEN",
    ]
    redacted = text
    for var in sensitive_vars:
        val = os.getenv(var)
        if val and len(val.strip()) > 3:
            redacted = redacted.replace(val, "[REDACTED]")
    return redact_security_value(redacted)


async def run_safe_command(
    project_id: int,
    command: str,
    uow: UnitOfWork,
    run_id: int | None = None,
    task_id: int | None = None,
    timeout: float = 60.0,
    run_mode: RunMode = RunMode.INTERACTIVE,
    poll_interval: float = 0.5,
    max_approval_wait: float = 10.0,  # Short default wait for testing
) -> tuple[int, str, str]:
    """Intercept, evaluate, and execute a shell command through the Safety Kernel.

    Enforces path boundaries, command bans, secrets redaction, and database
    approval queue workflows.
    """
    assert uow.projects is not None
    assert uow.tasks is not None
    assert uow.safety is not None
    assert uow.audits is not None

    # 1. Fetch project root path
    project = await uow.projects.get_project(project_id)
    if not project:
        raise ValueError(f"Project with ID {project_id} not found.")
    project_root = project.root_path

    # Override project_root with active TaskRun's worktree_path if set
    if task_id:
        task_runs = await uow.tasks.list_runs_for_task(task_id)
        if task_runs:
            active_run = task_runs[0]
            if active_run.worktree_path:
                project_root = active_run.worktree_path

    # 2. Fetch task risk level & sandbox overrides
    risk_level = "low"
    sandbox_image = None
    network_enabled = None
    if task_id:
        task = await uow.tasks.get_task(task_id)
        if task:
            risk_level = task.risk_level
            if task.metadata:
                sandbox_image = task.metadata.get("sandbox_image")
                network_enabled = task.metadata.get("network_enabled")

    # 3. Create ActionRequest
    request = ActionRequest(
        project_id=project_id,
        run_id=run_id,
        task_id=task_id,
        kind=ActionKind.RUN_COMMAND,
        payload={"command": command},
        purpose=f"CLI execution of: {command}",
        risk_level=risk_level,
    )

    # 4. Evaluate request through the common action gateway.
    gateway_decision = await ActionGateway(uow).evaluate(
        request,
        project_root=project_root,
        autonomy_level=AutonomyLevel.L3_UNATTENDED,
    )
    decision = gateway_decision.decision
    reason = gateway_decision.reason

    if decision == SafetyDecision.DENY:
        # Log Audit safety block
        audit = domain.AuditEvent(
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            actor_type=AuditEventActorType.SYSTEM,
            actor_id="safety-kernel",
            event_type=AuditEventType.SAFETY_DECISION,
            payload_redacted={
                "action": "run_command",
                "command": redact_secrets(command),
                "decision": "DENY",
                "reason": reason,
            },
        )
        await uow.audits.append_audit_event(audit)
        assert uow.session is not None
        await uow.session.commit()
        raise SafetyViolationError(f"Action DENIED by Safety Kernel: {reason}")

    elif decision == SafetyDecision.REQUIRE_APPROVAL:
        # Check mode restriction
        if run_mode == RunMode.UNATTENDED:
            audit = domain.AuditEvent(
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="safety-kernel",
                event_type=AuditEventType.SAFETY_DECISION,
                payload_redacted={
                    "action": "run_command",
                    "command": redact_secrets(command),
                    "decision": "DENY",
                    "reason": "Approval required but mode is UNATTENDED",
                },
            )
            await uow.audits.append_audit_event(audit)
            assert uow.session is not None
            await uow.session.commit()
            raise SafetyViolationError(
                "Action requires manual approval but run mode is UNATTENDED."
            )

        # Create pending approval request
        approval = domain.ActionApproval(
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            action_kind=ActionKind.RUN_COMMAND,
            payload={"command": command},
            purpose=f"Command execution: {command}",
            risk_level=risk_level,
            status=ActionApprovalStatus.PENDING,
        )
        approval_db = await uow.safety.create_approval(approval)
        assert uow.session is not None
        assert approval_db.id is not None

        # Commit transaction to ensure visible to polling scripts/API
        await uow.session.commit()

        # Poll database approval status
        elapsed = 0.0
        approved = False
        final_status = ActionApprovalStatus.PENDING

        while elapsed < max_approval_wait:
            uow.session.expire_all()
            refreshed = await uow.safety.get_approval(approval_db.id)
            if refreshed:
                final_status = refreshed.status
                if refreshed.status == ActionApprovalStatus.APPROVED:
                    approved = True
                    break
                elif refreshed.status == ActionApprovalStatus.REJECTED:
                    break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if not approved:
            # If timed out, update to TIMEOUT
            if final_status == ActionApprovalStatus.PENDING:
                final_status = ActionApprovalStatus.TIMEOUT
                approval_db.status = ActionApprovalStatus.TIMEOUT
                # Update status in db
                refreshed_obj = await uow.safety.get_approval(approval_db.id)
                if refreshed_obj:
                    refreshed_obj.status = ActionApprovalStatus.TIMEOUT
                    await uow.safety.update_approval(refreshed_obj)
                    await uow.session.commit()

            # Audit Reject
            audit = domain.AuditEvent(
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="safety-kernel",
                event_type=AuditEventType.SAFETY_DECISION,
                payload_redacted={
                    "action": "run_command",
                    "command": redact_secrets(command),
                    "decision": "DENY",
                    "reason": f"Approval rejected or timed out with status: {final_status}",
                },
            )
            await uow.audits.append_audit_event(audit)
            raise SafetyViolationError(f"Action approval rejected or timed out: {final_status}")

    # 5. Execute allowed/approved command
    try:
        from localforge.core.config import load_config
        from localforge.sandbox.factory import create_sandbox

        config = load_config()
        sandbox = create_sandbox(
            config,
            project_root,
            image_override=sandbox_image,
            network_override=network_enabled,
        )

        await sandbox.create()
        try:
            exit_code, stdout_str, stderr_str = await sandbox.execute(command, timeout=timeout)
        finally:
            await sandbox.destroy()

        # Redact secrets
        redacted_out = redact_secrets(stdout_str)
        redacted_err = redact_secrets(stderr_str)

        # Audit successful execution
        audit = domain.AuditEvent(
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            actor_type=AuditEventActorType.SYSTEM,
            actor_id="safety-kernel",
            event_type=AuditEventType.SAFETY_DECISION,
            payload_redacted={
                "action": "run_command",
                "command": redact_secrets(command),
                "decision": "ALLOW",
                "exit_code": exit_code,
            },
        )
        await uow.audits.append_audit_event(audit)

        return exit_code, redacted_out, redacted_err

    except Exception as e:
        if isinstance(e, SafetyViolationError) or isinstance(e, asyncio.TimeoutError):
            raise
        raise RuntimeError(f"Unexpected error executing command: {e}") from e
