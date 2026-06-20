import asyncio
import json
import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
