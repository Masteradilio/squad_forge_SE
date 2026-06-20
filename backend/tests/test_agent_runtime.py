import pytest
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    AuditEventType,
    HandoffKind,
    RunMode,
    TaskStatus,
)
from localforge.runtime.context import TaskContextBuilder
from localforge.runtime.file_tools import SafeFileEditor
from localforge.runtime.handoffs import RuntimeHandoffService
from localforge.runtime.lead_agent import LeadAgentRuntime
from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.safety import SafetyService
from localforge.services.task import TaskService
from localforge.storage import UnitOfWork


@pytest.mark.anyio
async def test_task_context_builder_bounds_large_files_and_includes_policy_and_worktree(
    db_session, tmp_path
):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    small = worktree / "small.py"
    large = worktree / "large.py"
    small.write_text("print('ok')\n", encoding="utf-8")
    large.write_text("x" * 500, encoding="utf-8")

    project = await uow.projects.create_project(
        domain.Project(name="Runtime", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    policy = domain.Policy(
        project_id=project.id,
        name="default",
        rules={"blocked_commands": ["rm -rf"], "protected_paths": [".env"], "allowed_commands": []},
    )
    await uow.audits.create_policy(policy)
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-1001",
            title="Build context",
            description="Use relevant files",
            acceptance_criteria=["Includes small file"],
            metadata={"relevant_files": ["small.py", "large.py"]},
        )
    )

    context = await TaskContextBuilder(uow).build(task.id, str(worktree), max_chars=300)

    assert "Build context" in context.rendered
    assert str(worktree) in context.rendered
    assert "print('ok')" in context.rendered
    assert "large.py omitted" in context.rendered
    assert ".env" in context.rendered
    assert len(context.rendered) <= 300


@pytest.mark.anyio
async def test_safe_file_editor_writes_inside_worktree_rejects_outside_and_records_diff(
    db_session, tmp_path
):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".localforge").mkdir()
    project = await uow.projects.create_project(
        domain.Project(name="Editor", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=project.id, key="LF-1003", title="Edit", description="")
    )
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(
        domain.TaskRun(
            run_id=run.id,
            task_id=task.id,
            worktree_path=str(worktree),
            branch_name="localforge/lf-1003",
        )
    )
    assert task_run.id is not None

    editor = SafeFileEditor(uow, project_id=project.id, run_id=run.id, task_id=task.id)
    result = await editor.write_text(
        worktree_root=str(worktree),
        relative_path="README.md",
        content="# Updated\n",
        task_run_id=task_run.id,
        task_key=task.key,
    )

    assert (worktree / "README.md").read_text(encoding="utf-8") == "# Updated\n"
    assert "README.md" in result.diff
    artifacts = await uow.audits.list_artifacts_for_task_run(task_run.id)
    assert artifacts and artifacts[0].path.endswith("diff.patch")

    with pytest.raises(ValueError):
        await editor.write_text(str(worktree), "../outside.md", "bad")


@pytest.mark.anyio
async def test_lead_agent_runtime_completes_trivial_file_change_through_safe_tools(
    db_session, tmp_path
):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    project = await uow.projects.create_project(
        domain.Project(name="Lead", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-1002",
            title="Write note",
            description="Create a note",
            acceptance_criteria=["note exists"],
            status=TaskStatus.PLANNING,
            metadata={
                "runtime_actions": [
                    {"kind": "write_file", "path": "NOTE.md", "content": "hello\n"},
                    {"kind": "run_command", "command": "git status"},
                ]
            },
        )
    )
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(
        domain.TaskRun(run_id=run.id, task_id=task.id, worktree_path=str(worktree))
    )
    assert task_run.id is not None

    runtime = LeadAgentRuntime(uow, project_id=project.id, run_id=run.id)
    summary = await runtime.run_task(task.id, task_run.id)

    assert (worktree / "NOTE.md").read_text(encoding="utf-8") == "hello\n"
    assert "summarized" in summary.lower()
    refreshed = await uow.tasks.get_task(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.PR_READY
    events = await uow.audits.list_audit_events_for_project(project.id)
    assert any(event.event_type == AuditEventType.SAFETY_DECISION for event in events)


@pytest.mark.anyio
async def test_runtime_handoff_is_stored_consumed_once_and_visible_in_replay(db_session, tmp_path):
    uow = UnitOfWork()
    uow.session = db_session
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.executions = ExecutionService(db_session)
    uow.audits = AuditService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="Handoff", root_path=str(tmp_path), default_branch="main")
    )
    assert project.id is not None
    run = await uow.executions.create_run(
        domain.Run(project_id=project.id, mode=RunMode.INTERACTIVE, initiated_by="test")
    )
    assert run.id is not None
    task = await uow.tasks.create_task(
        domain.Task(project_id=project.id, key="LF-1004", title="Hand off", description="")
    )
    assert task.id is not None
    task_run = await uow.tasks.create_task_run(domain.TaskRun(run_id=run.id, task_id=task.id))
    assert task_run.id is not None

    service = RuntimeHandoffService(uow, project_id=project.id, run_id=run.id, task_id=task.id)
    handoff = await service.create(
        task_run_id=task_run.id,
        from_role=AgentRole.SPECIFIER,
        to_role=AgentRole.CODER,
        kind=HandoffKind.PLAN,
        payload={"summary": "implement"},
    )
    consumed = await service.consume_once(handoff.id)

    assert consumed.id == handoff.id
    with pytest.raises(ValueError):
        await service.consume_once(handoff.id)

    replay = await uow.audits.export_run_replay(project.id, run.id)
    payloads = [item["payload"] for item in replay]
    assert any(payload.get("action") == "handoff_created" for payload in payloads)
    assert any(payload.get("action") == "handoff_consumed" for payload in payloads)
