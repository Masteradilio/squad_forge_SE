import asyncio
import json
import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from localforge.core.policy import PolicyRules
from localforge.quality.discovery import TestCommandDiscovery
from localforge.safety.runner import run_safe_command

from localforge.events.bus import EventBus, LifecycleEvent
from localforge.llm.fake import FakeLLMProvider
from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    AuditEventActorType,
    AuditEventType,
    RunStatus,
    TaskStatus,
)
from localforge.prd import import_prd
from localforge.services.audit import redact_secrets
from localforge.storage import DatabaseManager, UnitOfWork
from localforge.storage import db_manager as default_db_manager
from localforge.storage.orm import ArtifactORM, TaskRunORM


class ImportPRDRequest(BaseModel):
    path: str
    dry_run: bool = False


class TaskUpdateRequest(BaseModel):
    epic_id: int | None = None
    title: str
    description: str
    acceptance_criteria: list[str]
    dependency_task_ids: list[int]
    risk_level: str
    status: TaskStatus



def create_app(db_manager: DatabaseManager | None = None) -> FastAPI:
    manager = db_manager or default_db_manager
    app = FastAPI(title="LocalForge OS API", version="0.1.0")
    app.state.event_bus = EventBus(db_manager=manager)

    allowed_origins_raw = os.getenv("LOCALFORGE_ALLOWED_ORIGINS")
    if allowed_origins_raw:
        origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    else:
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/projects")
    async def list_projects() -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            return [_dump(project) for project in await uow.projects.list_projects()]

    @app.get("/projects/{project_id}/tasks")
    async def list_tasks(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            return [_dump(task) for task in await uow.tasks.list_tasks_for_project(project_id)]

    @app.get("/projects/{project_id}/runs")
    async def list_runs(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.executions is not None
            return [_dump(run) for run in await uow.executions.list_runs_for_project(project_id)]

    @app.get("/agents")
    async def list_agents() -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.executions is not None
            return [_dump(agent) for agent in await uow.executions.list_active_agents()]

    @app.get("/tasks/{task_id}/artifacts")
    async def list_task_artifacts(task_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.audits is not None
            task_runs = await uow.tasks.list_runs_for_task(task_id)
            artifacts = []
            for task_run in task_runs:
                if task_run.id is not None:
                    artifacts.extend(await uow.audits.list_artifacts_for_task_run(task_run.id))
            return [_dump(artifact) for artifact in artifacts]

    @app.get("/projects/{project_id}/policies/{name}")
    async def get_policy(project_id: int, name: str) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            policy = await uow.audits.get_project_policy(project_id, name)
            if not policy:
                raise HTTPException(status_code=404, detail="Policy not found")
            return _dump(policy)

    @app.get("/models")
    async def list_models() -> dict[str, Any]:
        provider = FakeLLMProvider()
        return {"provider": "localforge", "models": await provider.list_models()}

    @app.get("/projects/{project_id}/prs")
    async def list_prs(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            tasks = await uow.tasks.list_tasks_for_project(project_id)
            return [_dump(task) for task in tasks if task.status == TaskStatus.PR_READY]

    @app.get("/projects/{project_id}/audit-events")
    async def list_audit_events(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            events = await uow.audits.list_audit_events_for_project(project_id)
            return [_dump(event) for event in events]

    @app.get("/projects/{project_id}/events")
    async def stream_project_events(
        project_id: int,
        last_event_id: int = 0,
        limit: int = 25,
    ) -> StreamingResponse:
        bus: EventBus = app.state.event_bus

        async def event_stream():
            queue = bus.subscribe(project_id)
            try:
                replayed = await bus.replay(
                    project_id=project_id, after_id=last_event_id, limit=limit
                )
                for event in replayed:
                    yield _sse(event)
                heartbeat_sent = False
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=0.25)
                        yield _sse(event)
                    except TimeoutError:
                        if heartbeat_sent:
                            break
                        heartbeat_sent = True
                        yield ": keep-alive\n\n"
            finally:
                bus.unsubscribe(project_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/runs/{run_id}/{action}")
    async def command_run(run_id: int, action: str) -> dict[str, Any]:
        allowed = {
            "start": RunStatus.RUNNING,
            "pause": RunStatus.PAUSED,
            "resume": RunStatus.RUNNING,
            "stop": RunStatus.CANCELLED,
        }
        if action not in allowed:
            raise HTTPException(status_code=400, detail="Unsupported run command")
        async with UnitOfWork(manager) as uow:
            assert uow.executions is not None
            assert uow.audits is not None
            run = await uow.executions.get_run(run_id)
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")
            run.status = allowed[action]
            updated = await uow.executions.update_run(run)
            await uow.audits.append_audit_event(
                domain.AuditEvent(
                    project_id=updated.project_id,
                    run_id=updated.id,
                    actor_type=AuditEventActorType.USER,
                    actor_id="local-api",
                    event_type=AuditEventType.SYSTEM_EVENT,
                    payload_redacted={"action": f"run_{action}", "status": updated.status.value},
                )
            )
            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    run_id=updated.id,
                    event_type="run.started" if action in {"start", "resume"} else "system.event",
                    payload={"action": f"run_{action}", "status": updated.status.value},
                )
            )
            return _dump(updated)

    @app.get("/artifacts/{artifact_id}/content")
    async def get_artifact_content(artifact_id: int) -> dict[str, Any]:
        async with await manager.get_session() as session:
            artifact = await session.get(ArtifactORM, artifact_id)
            if not artifact:
                raise HTTPException(status_code=404, detail="Artifact not found")
            task_run = await session.get(TaskRunORM, artifact.task_run_id)
            if not task_run:
                raise HTTPException(status_code=404, detail="Task run not found")
            async with UnitOfWork(manager) as uow:
                assert uow.executions is not None
                assert uow.projects is not None
                run = await uow.executions.get_run(task_run.run_id)
                if not run:
                    raise HTTPException(status_code=404, detail="Run not found")
                project = await uow.projects.get_project(run.project_id)
                if not project:
                    raise HTTPException(status_code=404, detail="Project not found")
                target = os.path.realpath(
                    os.path.abspath(os.path.join(project.root_path, artifact.path))
                )
                root = os.path.realpath(os.path.abspath(project.root_path))
                try:
                    if os.path.commonpath([target, root]) != root:
                        raise HTTPException(
                            status_code=403, detail="Artifact path traversal blocked"
                        )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=403, detail="Artifact path traversal blocked"
                    ) from exc
                if not os.path.isfile(target):
                    raise HTTPException(status_code=404, detail="Artifact file not found")
                with open(target, encoding="utf-8") as handle:
                    content = redact_secrets(handle.read())
                return {"id": artifact.id, "path": artifact.path, "content": content}

    @app.get("/projects/{project_id}/safety/pending")
    async def list_pending_approvals(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.safety is not None
            approvals = await uow.safety.list_pending_approvals(project_id)
            return [_dump(approval) for approval in approvals]

    @app.post("/safety/approvals/{approval_id}/{action}")
    async def decide_approval(approval_id: int, action: str) -> dict[str, Any]:
        allowed = {
            "approve": ActionApprovalStatus.APPROVED,
            "reject": ActionApprovalStatus.REJECTED,
        }
        if action not in allowed:
            raise HTTPException(status_code=400, detail="Invalid approval decision")
        async with UnitOfWork(manager) as uow:
            assert uow.safety is not None
            assert uow.audits is not None
            approval = await uow.safety.get_approval(approval_id)
            if not approval:
                raise HTTPException(status_code=404, detail="Approval request not found")
            approval.status = allowed[action]
            approval.decided_at = datetime.utcnow()
            approval.decided_by = "local-api"
            updated = await uow.safety.update_approval(approval)
            
            # Publish event
            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    run_id=updated.run_id,
                    event_type=f"safety.action_{action}d",
                    payload={"approval_id": updated.id, "status": updated.status.value},
                )
            )
            return _dump(updated)

    @app.get("/projects/{project_id}/epics")
    async def list_epics(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            epics = await uow.tasks.list_epics_for_project(project_id)
            return [_dump(epic) for epic in epics]

    @app.post("/projects/{project_id}/import-prd")
    async def api_import_prd(
        project_id: int, req: ImportPRDRequest
    ) -> dict[str, Any]:
        try:
            result = await import_prd(
                path=req.path,
                project_id=project_id,
                db_manager=manager,
                dry_run=req.dry_run,
            )
            return result.model_dump()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/tasks/{task_id}")
    async def update_task(
        task_id: int, req: TaskUpdateRequest
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task.epic_id = req.epic_id
            task.title = req.title
            task.description = req.description
            task.acceptance_criteria = req.acceptance_criteria
            task.dependency_task_ids = req.dependency_task_ids
            task.risk_level = req.risk_level

            status_changed = task.status != req.status
            task.status = req.status

            try:
                updated = await uow.tasks.update_task(task)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            if status_changed:
                await app.state.event_bus.publish(
                    LifecycleEvent(
                        project_id=updated.project_id,
                        event_type="task.status_changed",
                        payload={
                            "task_id": updated.id,
                            "status": updated.status.value,
                        },
                    )
                )

            return _dump(updated)

    @app.post("/tasks/{task_id}/approve")
    async def approve_task_plan(task_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            try:
                updated = await uow.tasks.update_task_status(
                    task_id, TaskStatus.READY
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    event_type="task.status_changed",
                    payload={
                        "task_id": updated.id,
                        "status": updated.status.value,
                    },
                )
            )
            return _dump(updated)

    @app.put("/projects/{project_id}/policies/{name}")
    async def update_policy_rules(
        project_id: int, name: str, req: dict[str, Any]
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            policy = await uow.audits.get_project_policy(project_id, name)
            if not policy:
                raise HTTPException(status_code=404, detail="Policy not found")
            try:
                req_copy = dict(req)
                req_copy.pop("history", None)
                rules_validated = PolicyRules.model_validate(req_copy)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid policy rules: {exc}"
                ) from exc

            old_rules = dict(policy.rules)
            history = old_rules.pop("history", [])

            history_entry = {
                "version": len(history) + 1,
                "updated_at": datetime.utcnow().isoformat(),
                "rules": old_rules
            }
            history.append(history_entry)

            new_rules = rules_validated.model_dump()
            new_rules["history"] = history

            policy.rules = new_rules
            policy.updated_at = datetime.utcnow()
            updated = await uow.audits.update_policy(policy)
            return _dump(updated)

    @app.get("/tasks/{task_id}/pr-details")
    async def get_task_pr_details(task_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.projects is not None
            assert uow.audits is not None

            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            project = await uow.projects.get_project(task.project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            task_runs = await uow.tasks.list_runs_for_task(task_id)
            if not task_runs:
                raise HTTPException(
                    status_code=400, detail="No run exists for this task"
                )

            task_runs = sorted(task_runs, key=lambda r: r.started_at, reverse=True)
            latest_run = task_runs[0]

            artifacts = await uow.audits.list_artifacts_for_task_run(latest_run.id)

            summary = latest_run.final_summary or task.description or ""
            changed_files = task.metadata.get("changed_files", [])
            tests_content = ""
            risk_content = ""
            repair_content = ""
            patch_content = ""

            for artifact in artifacts:
                target = os.path.realpath(
                    os.path.abspath(os.path.join(project.root_path, artifact.path))
                )
                root = os.path.realpath(os.path.abspath(project.root_path))
                try:
                    if os.path.commonpath([target, root]) != root:
                        continue
                except ValueError:
                    continue

                if not os.path.isfile(target):
                    continue

                try:
                    with open(target, encoding="utf-8") as handle:
                        content = redact_secrets(handle.read())
                except Exception:
                    continue

                if artifact.path.endswith("diff.patch"):
                    patch_content = content
                    if not changed_files:
                        for line in content.splitlines():
                            if line.startswith("+++ b/"):
                                path = line[6:].strip()
                                if path not in changed_files:
                                    changed_files.append(path)
                elif artifact.path.endswith("tests.md"):
                    tests_content = content
                elif artifact.path.endswith("risk.md"):
                    risk_content = content
                elif artifact.path.endswith("repair.md"):
                    if repair_content:
                        repair_content += "\n\n" + content
                    else:
                        repair_content = content
                elif artifact.path.endswith("pr.md"):
                    summary = content

            return {
                "summary": summary,
                "changed_files": changed_files,
                "tests_content": tests_content,
                "risk_content": risk_content,
                "repair_content": repair_content,
                "patch_content": patch_content,
                "artifacts": [_dump(a) for a in artifacts],
            }

    @app.post("/tasks/{task_id}/open-path")
    async def open_task_local_path(task_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.projects is not None

            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            project = await uow.projects.get_project(task.project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            task_runs = await uow.tasks.list_runs_for_task(task_id)
            worktree_path = project.root_path
            if task_runs:
                task_runs = sorted(task_runs, key=lambda r: r.started_at, reverse=True)
                if task_runs[0].worktree_path:
                    worktree_path = task_runs[0].worktree_path

            if not os.path.exists(worktree_path):
                raise HTTPException(
                    status_code=404, detail=f"Path not found: {worktree_path}"
                )

            try:
                if hasattr(os, "startfile"):
                    os.startfile(worktree_path)
                else:
                    import subprocess
                    subprocess.run(["open", worktree_path], check=True)
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to open path: {e}"
                )

            return {"status": "ok", "path": worktree_path}

    @app.post("/tasks/{task_id}/rerun-tests")
    async def rerun_task_tests(task_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.projects is not None

            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            project = await uow.projects.get_project(task.project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            task_runs = await uow.tasks.list_runs_for_task(task_id)
            if not task_runs:
                raise HTTPException(
                    status_code=400, detail="No run exists for this task"
                )

            task_runs = sorted(task_runs, key=lambda r: r.started_at, reverse=True)
            latest_run = task_runs[0]
            worktree_path = latest_run.worktree_path or project.root_path

            discovery = TestCommandDiscovery()
            discovered = discovery.discover(worktree_path)

            test_cmd = "python -m pytest"
            for cmd in discovered:
                if "test" in cmd.command:
                    test_cmd = cmd.command
                    break

            try:
                exit_code, stdout, stderr = await run_safe_command(
                    project_id=task.project_id,
                    command=test_cmd,
                    uow=uow,
                    run_id=latest_run.run_id,
                    task_id=task_id,
                    timeout=60.0,
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to run command: {e}"
                )

            return {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
            }

    @app.post("/tasks/{task_id}/pr-review/{action}")
    async def decide_pr_review(task_id: int, action: str) -> dict[str, Any]:
        if action not in {"accept", "reject", "request_adjustment"}:
            raise HTTPException(status_code=400, detail="Invalid action")

        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            try:
                if action == "accept":
                    updated = await uow.tasks.update_task_status(
                        task_id, TaskStatus.DONE
                    )
                elif action == "reject":
                    updated = await uow.tasks.update_task_status(
                        task_id, TaskStatus.FAILED_SAFE
                    )
                else:  # request_adjustment
                    await uow.tasks.update_task_status(
                        task_id, TaskStatus.FAILED_SAFE
                    )
                    updated = await uow.tasks.update_task_status(
                        task_id, TaskStatus.READY
                    )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    event_type="task.status_changed",
                    payload={
                        "task_id": updated.id,
                        "status": updated.status.value,
                    },
                )
            )
            return _dump(updated)

    @app.get("/agents/{agent_id}/details")
    async def get_agent_details(agent_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.executions is not None
            agent = await uow.executions.get_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            async with await manager.get_session() as session:
                from sqlalchemy import select
                from localforge.storage.orm import (
                    TaskORM, TaskRunORM, ArtifactORM,
                    ActionApprovalORM, AuditEventORM, HandoffORM
                )

                tasks_res = await session.execute(
                    select(TaskORM).where(TaskORM.assigned_agent_id == agent_id)
                )
                assigned_tasks = tasks_res.scalars().all()
                assigned_task_ids = [t.id for t in assigned_tasks]

                task_runs = []
                artifacts = []
                approvals = []
                logs = []

                if assigned_task_ids:
                    runs_res = await session.execute(
                        select(TaskRunORM)
                        .where(TaskRunORM.task_id.in_(assigned_task_ids))
                        .order_by(TaskRunORM.started_at.desc())
                    )
                    task_runs = runs_res.scalars().all()
                    task_run_ids = [tr.id for tr in task_runs]

                    if task_run_ids:
                        art_res = await session.execute(
                            select(ArtifactORM)
                            .where(ArtifactORM.task_run_id.in_(task_run_ids))
                            .order_by(ArtifactORM.created_at.desc())
                        )
                        artifacts = art_res.scalars().all()

                    app_res = await session.execute(
                        select(ActionApprovalORM)
                        .where(ActionApprovalORM.task_id.in_(assigned_task_ids))
                        .order_by(ActionApprovalORM.created_at.desc())
                    )
                    approvals = app_res.scalars().all()

                    audit_res = await session.execute(
                        select(AuditEventORM)
                        .where(
                            (AuditEventORM.task_id.in_(assigned_task_ids)) |
                            (AuditEventORM.actor_id == agent.name)
                        )
                        .order_by(AuditEventORM.created_at.desc())
                        .limit(100)
                    )
                    logs = audit_res.scalars().all()

                handoff_res = await session.execute(
                    select(HandoffORM)
                    .where(
                        (HandoffORM.from_role == agent.role.value) |
                        (HandoffORM.to_role == agent.role.value)
                    )
                    .order_by(HandoffORM.created_at.desc())
                    .limit(50)
                )
                handoffs = handoff_res.scalars().all()

                current_task = None
                latest_run = None
                if agent.current_task_id:
                    current_task = next(
                        (t for t in assigned_tasks if t.id == agent.current_task_id),
                        None
                    )
                    if not current_task:
                        t_res = await session.get(TaskORM, agent.current_task_id)
                        if t_res:
                            current_task = t_res

                    current_runs = [
                        tr for tr in task_runs if tr.task_id == agent.current_task_id
                    ]
                    if current_runs:
                        latest_run = current_runs[0]

                return {
                    "agent": _dump(agent),
                    "current_task": (
                        _dump(current_task.to_domain()) if current_task else None
                    ),
                    "latest_run": (
                        _dump(latest_run.to_domain()) if latest_run else None
                    ),
                    "handoffs": [_dump(h.to_domain()) for h in handoffs],
                    "artifacts": [_dump(a.to_domain()) for a in artifacts],
                    "actions": [_dump(ap.to_domain()) for ap in approvals],
                    "logs": [_dump(l.to_domain()) for l in logs],
                }

    @app.post("/tasks/{task_id}/control/{action}")
    async def control_task_execution(task_id: int, action: str) -> dict[str, Any]:
        if action not in {"pause", "resume", "terminate", "block"}:
            raise HTTPException(status_code=400, detail="Invalid control action")

        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.executions is not None

            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

            task_runs = await uow.tasks.list_runs_for_task(task_id)
            latest_run = None
            if task_runs:
                task_runs = sorted(task_runs, key=lambda r: r.started_at, reverse=True)
                latest_run = task_runs[0]

            if action == "block":
                try:
                    updated = await uow.tasks.update_task_status(
                        task_id, TaskStatus.BLOCKED
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

            else:
                if not latest_run:
                    raise HTTPException(
                        status_code=400, detail="No active run to control"
                    )

                run = await uow.executions.get_run(latest_run.run_id)
                if not run:
                    raise HTTPException(status_code=404, detail="Run not found")

                if action == "pause":
                    run.status = RunStatus.PAUSED
                    if latest_run.status == TaskRunStatus.RUNNING:
                        async with await manager.get_session() as session:
                            from localforge.storage.orm import TaskRunORM
                            db_tr = await session.get(TaskRunORM, latest_run.id)
                            if db_tr:
                                db_tr.status = "PENDING"
                                await session.commit()
                elif action == "resume":
                    run.status = RunStatus.RUNNING
                elif action == "terminate":
                    run.status = RunStatus.CANCELLED
                    try:
                        await uow.tasks.update_task_status(
                            task_id, TaskStatus.CANCELLED
                        )
                    except ValueError:
                        async with await manager.get_session() as session:
                            from localforge.storage.orm import TaskORM
                            db_task = await session.get(TaskORM, task_id)
                            if db_task:
                                db_task.status = "CANCELLED"
                                await session.commit()

                await uow.executions.update_run(run)
                updated = await uow.tasks.get_task(task_id)

            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    event_type="task.status_changed",
                    payload={
                        "task_id": updated.id,
                        "status": updated.status.value,
                    },
                )
            )
            return _dump(updated)

    @app.post("/projects/{project_id}/policies/{name}/restore/{version}")
    async def restore_policy_version(
        project_id: int, name: str, version: int
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            policy = await uow.audits.get_project_policy(project_id, name)
            if not policy:
                raise HTTPException(status_code=404, detail="Policy not found")

            history = policy.rules.get("history", [])
            target_entry = next((h for h in history if h["version"] == version), None)
            if not target_entry:
                raise HTTPException(
                    status_code=404, detail=f"Version {version} not found in history"
                )

            restored_rules = dict(target_entry["rules"])
            restored_rules["history"] = history
            policy.rules = restored_rules
            policy.updated_at = datetime.utcnow()
            updated = await uow.audits.update_policy(policy)
            return _dump(updated)

    # Serve static files from frontend/dist if the directory exists
    frontend_dist = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../frontend/dist")
    )
    if os.path.isdir(frontend_dist):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def _dump(model: Any) -> dict[str, Any]:
    data = model.model_dump(mode="json")
    for key, value in list(data.items()):
        if hasattr(value, "value"):
            data[key] = value.value
    return data


def _sse(event: LifecycleEvent) -> str:
    payload = json.dumps(event.to_sse_payload(), separators=(",", ":"))
    event_id = event.id if event.id is not None else ""
    return f"id: {event_id}\nevent: {event.event_type}\ndata: {payload}\n\n"
