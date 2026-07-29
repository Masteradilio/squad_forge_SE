import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    ActionKind,
    AuditEventType,
    RunMode,
)
from localforge.safety import (
    ActionRequest,
    SafetyDecision,
    SafetyKernel,
    SafetyViolationError,
    is_path_safe,
    redact_secrets,
    run_safe_command,
)
from localforge.storage import UnitOfWork


def test_is_path_safe(tmp_path):
    """Verify is_path_safe correctly assesses paths relative to root path."""
    root = tmp_path / "worktree"
    root.mkdir()

    # Safe subdirectory target
    safe_target = root / "src" / "main.py"
    assert is_path_safe(str(safe_target), str(root)) is True

    # Unsafe target using parent relative traverse
    unsafe_target = root / ".." / "outside.txt"
    assert is_path_safe(str(unsafe_target), str(root)) is False


def test_action_request_validation():
    """Verify that ActionRequest enforces correct payload requirements."""
    # Valid Command
    req_cmd = ActionRequest(
        project_id=1,
        kind=ActionKind.RUN_COMMAND,
        payload={"command": "pytest"},
        purpose="running tests",
    )
    assert req_cmd.kind == ActionKind.RUN_COMMAND

    # Invalid Command (missing command field)
    with pytest.raises(ValueError) as exc:
        ActionRequest(
            project_id=1,
            kind=ActionKind.RUN_COMMAND,
            payload={},
            purpose="running tests",
        )
    assert "Command string is required" in str(exc.value)

    # Valid File
    req_file = ActionRequest(
        project_id=1,
        kind=ActionKind.WRITE_FILE,
        payload={"path": "src/main.py"},
        purpose="writing source",
    )
    assert req_file.kind == ActionKind.WRITE_FILE

    # Invalid File (missing path field)
    with pytest.raises(ValueError) as exc:
        ActionRequest(
            project_id=1,
            kind=ActionKind.WRITE_FILE,
            payload={},
            purpose="writing source",
        )
    assert "Path string is required" in str(exc.value)


@pytest.mark.anyio
async def test_safety_kernel_evaluate_file(tmp_path, db_session):
    """Verify that SafetyKernel rejects traversal writes and protected paths."""
    uow = UnitOfWork()
    uow.session = db_session
    # Initialize UOW service bindings manually
    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService

    uow.projects = ProjectService(db_session)
    uow.audits = AuditService(db_session)

    # Register project
    proj_data = domain.Project(
        name="KernelTest",
        root_path=str(tmp_path),
        default_branch="main",
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    # 1. Safe write evaluation
    req_safe = ActionRequest(
        project_id=project.id,
        kind=ActionKind.WRITE_FILE,
        payload={"path": os.path.join(str(tmp_path), "test.txt")},
        purpose="write clean file",
    )
    decision, reason = await SafetyKernel.evaluate(req_safe, uow, str(tmp_path))
    assert decision == SafetyDecision.ALLOW

    # 2. Out-of-bounds write evaluation (traversal block)
    req_unsafe = ActionRequest(
        project_id=project.id,
        kind=ActionKind.WRITE_FILE,
        payload={"path": os.path.join(str(tmp_path), "..", "outside.txt")},
        purpose="write traversed file",
    )
    decision, reason = await SafetyKernel.evaluate(req_unsafe, uow, str(tmp_path))
    assert decision == SafetyDecision.DENY
    assert "outside workspace" in reason

    # 3. Protected path evaluation (denying write to .env)
    req_protected = ActionRequest(
        project_id=project.id,
        kind=ActionKind.WRITE_FILE,
        payload={"path": os.path.join(str(tmp_path), ".env")},
        purpose="writing env variables",
    )
    decision, reason = await SafetyKernel.evaluate(req_protected, uow, str(tmp_path))
    assert decision == SafetyDecision.DENY
    assert "Access to protected path" in reason


@pytest.mark.anyio
async def test_safety_kernel_evaluate_commands(tmp_path, db_session):
    """Verify commands evaluation against policy rules and risk limits."""
    uow = UnitOfWork()
    uow.session = db_session
    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService

    uow.projects = ProjectService(db_session)
    uow.audits = AuditService(db_session)

    proj_data = domain.Project(
        name="CmdTest",
        root_path=str(tmp_path),
        default_branch="main",
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    # Register default policy template
    policy = domain.Policy(
        project_id=project.id,
        name="default",
        rules={
            "blocked_commands": ["rm -rf", "git push --force"],
            "protected_paths": [".env"],
            "allowed_commands": [],
        },
    )
    await uow.audits.create_policy(policy)

    # 1. Blocked command
    req_blocked = ActionRequest(
        project_id=project.id,
        kind=ActionKind.RUN_COMMAND,
        payload={"command": "rm -rf /tmp/data"},
        purpose="cleaning",
    )
    decision, reason = await SafetyKernel.evaluate(req_blocked, uow, str(tmp_path))
    assert decision == SafetyDecision.DENY

    # 2. Risk level escalation to require approval
    req_risk = ActionRequest(
        project_id=project.id,
        kind=ActionKind.RUN_COMMAND,
        payload={"command": "git status"},
        purpose="checking status",
        risk_level="high",
    )
    decision, reason = await SafetyKernel.evaluate(req_risk, uow, str(tmp_path))
    assert decision == SafetyDecision.REQUIRE_APPROVAL


@pytest.mark.anyio
async def test_run_safe_command_unattended(tmp_path, db_session):
    """Verify that run_safe_command fails immediately when requiring approval in unattended mode."""
    uow = UnitOfWork()
    uow.session = db_session
    from localforge.services.audit import AuditService
    from localforge.services.execution import ExecutionService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService

    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    # Register project
    proj_data = domain.Project(
        name="UnattendedTest",
        root_path=str(tmp_path),
        default_branch="main",
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    # Let's verify via task context
    task_data = domain.Task(
        project_id=project.id,
        key="LF-05",
        title="High Risk Task",
        description="Testing safety",
        risk_level="high",
    )
    task = await uow.tasks.create_task(task_data)

    with pytest.raises(SafetyViolationError) as exc:
        await run_safe_command(
            project_id=project.id,
            command="git status",
            uow=uow,
            run_mode=RunMode.UNATTENDED,
            task_id=task.id,
            run_id=None,
        )
    assert "UNATTENDED" in str(exc.value)

    # Verify audit event logged
    events = await uow.audits.list_audit_events_for_project(project.id)
    assert len(events) >= 1
    assert events[0].event_type == AuditEventType.SAFETY_DECISION
    assert events[0].payload_redacted["decision"] == "DENY"


@pytest.mark.anyio
async def test_run_safe_command_interactive_approval(tmp_path, db_session):
    """Verify command runner handles database pending approval queues and polls successfully."""
    uow = UnitOfWork()
    uow.session = db_session
    from localforge.services.audit import AuditService
    from localforge.services.execution import ExecutionService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService

    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    # Register project
    proj_data = domain.Project(
        name="ApprovalTest",
        root_path=str(tmp_path),
        default_branch="main",
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    task_data = domain.Task(
        project_id=project.id,
        key="LF-06",
        title="High Risk",
        description="Test approval polling",
        risk_level="high",
    )
    task = await uow.tasks.create_task(task_data)

    # Start runner command in the background (as task)
    # We mock execution return to make it fast
    with patch(
        "localforge.sandbox.local.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
    ) as mock_subproc:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"Command output", b"")
        mock_proc.returncode = 0
        mock_subproc.return_value = mock_proc

        runner_task = asyncio.create_task(
            run_safe_command(
                project_id=project.id,
                command="git status",
                uow=uow,
                run_mode=RunMode.INTERACTIVE,
                task_id=task.id,
                poll_interval=0.1,
                max_approval_wait=2.0,
            )
        )

        # Yield control to let task start and insert approval request in DB
        await asyncio.sleep(0.2)

        # Check pending approvals
        # Note: the task committed the session, so we can fetch approvals inside a fresh query
        uow.session.expire_all()
        approvals = await uow.safety.list_pending_approvals(project.id)
        assert len(approvals) == 1
        pending_app = approvals[0]
        assert pending_app.status == ActionApprovalStatus.PENDING

        # Set status to APPROVED
        pending_app.status = ActionApprovalStatus.APPROVED
        pending_app.decided_by = "test-agent"
        await uow.safety.update_approval(pending_app)
        await uow.session.commit()

        # Wait for the task to complete
        code, out, err = await runner_task
        assert code == 0
        assert "Command output" in out


def test_redact_secrets():
    """Verify that redact_secrets clears environment variables matches."""
    os.environ["LOCALFORGE_GITHUB_TOKEN"] = "sekret_token_123"
    os.environ["LOCALFORGE_MODEL_API_KEY"] = "super_key_abc"

    raw_text = "Failed on API call with key super_key_abc and token sekret_token_123"
    redacted = redact_secrets(raw_text)

    assert "super_key_abc" not in redacted
    assert "sekret_token_123" not in redacted
    assert redacted == "Failed on API call with key [REDACTED] and token [REDACTED]"
