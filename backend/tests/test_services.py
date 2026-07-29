from datetime import datetime

import pytest
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    ArtifactType,
    AuditEventActorType,
    AuditEventType,
    DocumentKind,
    HandoffKind,
    HandoffStatus,
    RunMode,
    RunStatus,
    TaskStatus,
)
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.task import TaskService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_project_service(db_session: AsyncSession):
    proj_service = ProjectService(db_session)

    # 1. Create Project
    proj = domain.Project(name="LF Test", root_path="/test/path", default_branch="main")
    created = await proj_service.create_project(proj)
    assert created.id is not None
    assert created.name == "LF Test"

    # 2. Get Project
    fetched = await proj_service.get_project(created.id)
    assert fetched is not None
    assert fetched.root_path == "/test/path"

    # 3. Get Project by path
    fetched_path = await proj_service.get_project_by_path("/test/path")
    assert fetched_path is not None
    assert fetched_path.id == created.id

    # 4. List projects
    projects = await proj_service.list_projects()
    assert len(projects) == 1

    # 5. Create Document
    doc = domain.ProductDocument(
        project_id=created.id, kind=DocumentKind.PRD, path="PRD.md", content_hash="hash123"
    )
    created_doc = await proj_service.create_document(doc)
    assert created_doc.id is not None
    assert created_doc.content_hash == "hash123"

    # 6. Get Document by hash
    fetched_doc = await proj_service.get_document_by_hash(created.id, "hash123")
    assert fetched_doc is not None
    assert fetched_doc.path == "PRD.md"


@pytest.mark.asyncio
async def test_task_service_and_state_machine(db_session: AsyncSession):
    proj_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    exec_service = ExecutionService(db_session)
    audit_service = AuditService(db_session)

    # Setup Project
    proj = await proj_service.create_project(
        domain.Project(name="LF Test", root_path="/t", default_branch="m")
    )
    assert proj.id is not None

    # 1. Create Epic
    epic = await task_service.create_epic(
        domain.Epic(project_id=proj.id, title="Epic 1", summary="Sum")
    )
    assert epic.id is not None

    # 2. Create Task
    task = await task_service.create_task(
        domain.Task(
            project_id=proj.id,
            epic_id=epic.id,
            key="LF-100",
            title="Task 1",
            description="Desc",
            acceptance_criteria=["Done"],
        )
    )
    assert task.id is not None
    assert task.status == TaskStatus.BACKLOG

    # 3. Test Invalid State Transition (BACKLOG -> CLAIMED should raise ValueError)
    with pytest.raises(ValueError) as exc:
        await task_service.update_task_status(task.id, TaskStatus.CLAIMED)
    assert "Illegal state transition" in str(exc.value)

    # 4. Test Valid State Transition (BACKLOG -> READY -> CLAIMED -> PLANNING)
    t_ready = await task_service.update_task_status(task.id, TaskStatus.READY)
    assert t_ready.status == TaskStatus.READY

    t_claimed = await task_service.update_task_status(task.id, TaskStatus.CLAIMED)
    assert t_claimed.status == TaskStatus.CLAIMED

    t_planning = await task_service.update_task_status(task.id, TaskStatus.PLANNING)
    assert t_planning.status == TaskStatus.PLANNING

    await task_service.update_task_status(task.id, TaskStatus.IMPLEMENTING)
    await task_service.update_task_status(task.id, TaskStatus.TESTING)
    await task_service.update_task_status(task.id, TaskStatus.REVIEWING)
    with pytest.raises(ValueError, match="mark_pr_ready"):
        await task_service.update_task_status(task.id, TaskStatus.PR_READY)
    run = await exec_service.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.UNATTENDED, initiated_by="test")
    )
    assert run.id is not None
    task_run = await task_service.create_task_run(
        domain.TaskRun(
            run_id=run.id,
            task_id=task.id,
            worktree_path="/tmp/lf-100",
            branch_name="localforge/lf-100",
        )
    )
    assert task_run.id is not None
    artifact = await audit_service.create_artifact(
        domain.Artifact(
            task_run_id=task_run.id,
            type=ArtifactType.PR,
            path=".localforge/artifacts/runs/1/tasks/lf-100/pr.md",
            content_hash="a" * 64,
        )
    )
    gate_evidence = {
        "source": "unit_test",
        "task_run_id": task_run.id,
        "maker_id": "maker",
        "checker_id": "checker",
        "pre_pr_gate": {"passed": True},
        "checks_executed": ["pytest"],
        "artifact_paths": [artifact.path],
        "branch_name": task_run.branch_name,
        "worktree_path": task_run.worktree_path,
    }
    pr_ready = await task_service.mark_pr_ready(task.id, gate_evidence=gate_evidence)
    assert pr_ready.status == TaskStatus.PR_READY
    assert pr_ready.metadata["pr_ready_gate"]["passed"] is True
    evidence = pr_ready.metadata["pr_ready_gate"]["evidence"]
    assert evidence["schema"] == "localforge.pr_ready_evidence.v1"
    assert evidence["artifact_paths"] == [artifact.path]
    assert await task_service.mark_pr_ready(task.id, gate_evidence=gate_evidence) == pr_ready
    conflicting_evidence = {**gate_evidence, "source": "conflicting"}
    with pytest.raises(ValueError, match="already been recorded"):
        await task_service.mark_pr_ready(task.id, gate_evidence=conflicting_evidence)


@pytest.mark.asyncio
async def test_pr_ready_rejects_untyped_or_spoofed_evidence(db_session: AsyncSession):
    proj_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    exec_service = ExecutionService(db_session)
    audit_service = AuditService(db_session)

    proj = await proj_service.create_project(
        domain.Project(name="LF Test", root_path="/t", default_branch="m")
    )
    assert proj.id is not None
    task = await task_service.create_task(
        domain.Task(project_id=proj.id, key="LF-101", title="Task", description="Desc")
    )
    assert task.id is not None
    run = await exec_service.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.UNATTENDED, initiated_by="test")
    )
    assert run.id is not None
    task_run = await task_service.create_task_run(
        domain.TaskRun(
            run_id=run.id,
            task_id=task.id,
            worktree_path="/tmp/lf-101",
            branch_name="localforge/lf-101",
        )
    )
    assert task_run.id is not None
    await audit_service.create_artifact(
        domain.Artifact(
            task_run_id=task_run.id,
            type=ArtifactType.PR,
            path=".localforge/artifacts/runs/1/tasks/lf-101/pr.md",
            content_hash="b" * 64,
        )
    )
    for status in (
        TaskStatus.READY,
        TaskStatus.CLAIMED,
        TaskStatus.PLANNING,
        TaskStatus.IMPLEMENTING,
        TaskStatus.TESTING,
        TaskStatus.REVIEWING,
    ):
        await task_service.update_task_status(task.id, status)

    with pytest.raises(ValueError):
        await task_service.mark_pr_ready(
            task.id,
            gate_evidence={"source": "unit_test", "task_run_id": task_run.id},
        )
    with pytest.raises(ValueError, match="independent"):
        await task_service.mark_pr_ready(
            task.id,
            gate_evidence={
                "source": "unit_test",
                "task_run_id": task_run.id,
                "maker_id": "same",
                "checker_id": "same",
                "pre_pr_gate": {"passed": True},
                "checks_executed": ["pytest"],
            },
        )
    with pytest.raises(ValueError, match="pre_pr_gate"):
        await task_service.mark_pr_ready(
            task.id,
            gate_evidence={
                "source": "unit_test",
                "task_run_id": task_run.id,
                "maker_id": "maker",
                "checker_id": "checker",
                "pre_pr_gate": {"passed": False},
                "checks_executed": ["pytest"],
            },
        )


@pytest.mark.asyncio
async def test_execution_and_handoffs(db_session: AsyncSession):
    proj_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    exec_service = ExecutionService(db_session)

    # Setup Project & Task
    proj = await proj_service.create_project(
        domain.Project(name="LF Test", root_path="/t", default_branch="m")
    )
    assert proj.id is not None

    task = await task_service.create_task(
        domain.Task(project_id=proj.id, key="LF-100", title="T", description="D")
    )
    assert task.id is not None

    # 1. Create Run
    run = await exec_service.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.UNATTENDED, initiated_by="user")
    )
    assert run.id is not None
    assert run.status == RunStatus.PENDING

    # 2. Register Agent
    agent = await exec_service.register_agent(
        domain.Agent(name="Coder-Alpha", role=AgentRole.CODER, model_profile_id="llama3")
    )
    assert agent.id is not None

    # 3. Create TaskRun
    task_run = await task_service.create_task_run(
        domain.TaskRun(run_id=run.id, task_id=task.id, attempt_count=1)
    )
    assert task_run.id is not None

    # 4. Create Handoff
    handoff = await exec_service.create_handoff(
        domain.Handoff(
            task_run_id=task_run.id,
            from_role=AgentRole.PLANNER,
            to_role=AgentRole.CODER,
            kind=HandoffKind.PLAN,
            payload_json={"plan": "step 1"},
        )
    )
    assert handoff.id is not None
    assert handoff.status == HandoffStatus.PENDING

    # 5. List and Consume Handoff
    pending = await exec_service.list_pending_handoffs(to_role=AgentRole.CODER)
    assert len(pending) == 1
    assert pending[0].id == handoff.id

    consumed = await exec_service.consume_handoff(handoff.id)
    assert consumed.status == HandoffStatus.CONSUMED
    assert isinstance(consumed.consumed_at, datetime)


@pytest.mark.asyncio
async def test_audit_artifacts_policies(db_session: AsyncSession):
    proj_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    exec_service = ExecutionService(db_session)
    audit_service = AuditService(db_session)

    # Setup
    proj = await proj_service.create_project(
        domain.Project(name="LF Test", root_path="/t", default_branch="m")
    )
    assert proj.id is not None

    task = await task_service.create_task(
        domain.Task(project_id=proj.id, key="LF-100", title="T", description="D")
    )
    assert task.id is not None

    run = await exec_service.create_run(
        domain.Run(project_id=proj.id, mode=RunMode.UNATTENDED, initiated_by="user")
    )
    assert run.id is not None

    task_run = await task_service.create_task_run(
        domain.TaskRun(run_id=run.id, task_id=task.id, attempt_count=1)
    )
    assert task_run.id is not None

    # 1. Append Audit Event
    event = await audit_service.append_audit_event(
        domain.AuditEvent(
            project_id=proj.id,
            run_id=run.id,
            task_id=task.id,
            actor_type=AuditEventActorType.SYSTEM,
            event_type=AuditEventType.STATE_CHANGE,
            payload_redacted={"info": "started"},
        )
    )
    assert event.id is not None

    events = await audit_service.list_audit_events_for_project(proj.id)
    assert len(events) == 1
    assert events[0].id == event.id

    # 2. Create Artifact
    artifact = await audit_service.create_artifact(
        domain.Artifact(
            task_run_id=task_run.id,
            type=ArtifactType.PLAN,
            path="plan.md",
            content_hash="abc",
        )
    )
    assert artifact.id is not None

    artifacts = await audit_service.list_artifacts_for_task_run(task_run.id)
    assert len(artifacts) == 1
    assert artifacts[0].id == artifact.id

    # 3. Policy management
    policy = await audit_service.create_policy(
        domain.Policy(
            project_id=proj.id,
            name="default",
            rules={"max_repair_attempts": 3},
        )
    )
    assert policy.id is not None

    fetched_policy = await audit_service.get_project_policy(proj.id, "default")
    assert fetched_policy is not None
    assert fetched_policy.rules["max_repair_attempts"] == 3
