import asyncio
import json
import logging
import os
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from localforge import __version__
from localforge.api.routes import autonomy_router, circuit_breakers_router, loops_router


from localforge.api.schemas import (

    ImportPRDRequest,
    MemoryFactRequest,
    MemoryFactUpdateRequest,
    MemoryImportRequest,
    ModelRouteRequest,
    PipelineRunRequest,
    PricingSnapshotUpdateRequest,
    PricingSourceCreateRequest,
    RuntimeHeartbeatRequest,
    RuntimeRegistrationRequest,
    SkillRequest,
    SquadRequest,
    TaskCommentRequest,
    TaskUpdateRequest,
    WorktreeRevertRequest,
)
from localforge.core.config import load_config
from localforge.core.policy import PolicyRules
from localforge.events.bus import EventBus, LifecycleEvent
from localforge.llm.base import BaseLLMProvider
from localforge.llm.openai_compatible import OpenAICompatibleProvider
from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    AuditEventActorType,
    AuditEventType,
    RunMode,
    RunStatus,
    TaskRunStatus,
    TaskStatus,
)
from localforge.pipeline import RolePipelineEngine
from localforge.prd import import_prd
from localforge.quality.discovery import TestCommandDiscovery
from localforge.gitops.manager import WorktreeManager
from localforge.safety.runner import run_safe_command
from localforge.services.audit import redact_secrets
from localforge.skills import SkillDefinition, SkillRegistry
from localforge.storage import DatabaseManager, UnitOfWork
from localforge.storage import db_manager as default_db_manager
from localforge.storage.orm import ArtifactORM, TaskRunORM


logger = logging.getLogger(__name__)


def create_app(
    db_manager: DatabaseManager | None = None,
    llm_provider: BaseLLMProvider | None = None,
) -> FastAPI:
    manager = db_manager or default_db_manager
    app = FastAPI(title="LocalForge OS API", version=__version__)
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

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'",
        )
        return response

    @app.get("/health")

    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(loops_router)
    app.include_router(circuit_breakers_router)
    app.include_router(autonomy_router)




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
            task_run_ids = [task_run.id for task_run in task_runs if task_run.id is not None]
            artifacts_by_run = await uow.audits.list_artifacts_for_task_runs(task_run_ids)
            artifacts = [
                artifact
                for task_run_id in task_run_ids
                for artifact in artifacts_by_run.get(task_run_id, [])
            ]
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
        config = load_config()
        provider = llm_provider or OpenAICompatibleProvider(
            base_url=config.models.base_url, default_model=config.models.default_model
        )
        return {
            "provider": config.models.provider,
            "base_url": config.models.base_url,
            "default_model": config.models.default_model,
            "models": await provider.list_models(),
        }

    @app.get("/projects/{project_id}/models/metrics")
    async def model_metrics(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.routing is not None
            routes = await uow.routing.list_routes(project_id)
            return [
                {
                    "role": route.role.value,
                    "provider": route.provider,
                    "model_profile_id": route.model_profile_id,
                    "success_rate": 1.0,
                    "failure_rate": 0.0,
                    "last_used_at": route.updated_at.isoformat(),
                }
                for route in routes
            ]

    @app.get("/projects/{project_id}/chief-engineer/calls")
    async def chief_engineer_calls(
        project_id: int, run_id: int | None = None
    ) -> dict[str, Any]:
        config = load_config()
        async with UnitOfWork(manager) as uow:
            assert uow.model_calls is not None
            calls = await uow.model_calls.list_calls(project_id=project_id, run_id=run_id)
            return {
                "provider": config.chief_engineer.provider,
                "model": config.chief_engineer.model,
                "enabled": config.chief_engineer.enabled,
                "api_key_configured": bool(config.chief_engineer.api_key),
                "budget": {
                    "max_paid_calls": config.budgets.max_paid_calls,
                    "max_paid_input_tokens": config.budgets.max_paid_input_tokens,
                    "max_paid_output_tokens": config.budgets.max_paid_output_tokens,
                    "max_paid_usd": config.budgets.max_paid_usd,
                },
                "calls": [_dump(call) for call in calls],
            }

    @app.get("/projects/{project_id}/settings")
    async def project_settings(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            project = await uow.projects.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            config = load_config()
            return {
                "project_path": project.root_path,
                "default_branch": project.default_branch,
                "git_provider": "local-git",
                "pr_provider": "github" if project.remote_url else "local-artifact",
                "remote_url": project.remote_url,
                "model_endpoint": config.models.base_url,
                "sandbox_mode": config.sandbox.type,
                "resource_limits": config.budgets.model_dump(mode="json"),
                "ui_preferences": {"theme": "system"},
            }

    @app.get("/projects/{project_id}/skills")
    async def list_project_skills(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            project = await uow.projects.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            return [
                skill.model_dump(mode="json")
                for skill in SkillRegistry(project.root_path).load_all()
            ]

    @app.post("/projects/{project_id}/skills")
    async def register_project_skill(project_id: int, req: SkillRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            project = await uow.projects.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            skill = SkillRegistry(project.root_path).write_local(
                SkillDefinition(
                    name=req.name,
                    purpose=req.purpose,
                    triggers=req.triggers,
                    allowed_actions=req.allowed_actions,
                    expected_artifacts=req.expected_artifacts,
                    failure_modes=req.failure_modes,
                    examples=req.examples,
                    enabled=req.enabled,
                )
            )
            return skill.model_dump(mode="json")

    @app.put("/projects/{project_id}/skills/{name}")
    async def update_project_skill(
        project_id: int, name: str, req: SkillRequest
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            project = await uow.projects.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            skill = SkillRegistry(project.root_path).write_local(
                SkillDefinition(
                    name=name,
                    purpose=req.purpose,
                    triggers=req.triggers,
                    allowed_actions=req.allowed_actions,
                    expected_artifacts=req.expected_artifacts,
                    failure_modes=req.failure_modes,
                    examples=req.examples,
                    enabled=req.enabled,
                )
            )
            return skill.model_dump(mode="json")

    @app.get("/tasks/{task_id}/skills")
    async def select_task_skills(task_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.tasks is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            project = await uow.projects.get_project(task.project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            return [
                skill.model_dump(mode="json")
                for skill in SkillRegistry(project.root_path).select_for_task(task)
            ]

    @app.get("/projects/{project_id}/model-routes")
    async def list_model_routes(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.routing is not None
            return [_dump(route) for route in await uow.routing.list_routes(project_id)]

    @app.put("/projects/{project_id}/model-routes")
    async def upsert_model_route(project_id: int, req: ModelRouteRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.routing is not None
            route = await uow.routing.upsert_route(
                domain.ModelRoute(
                    project_id=project_id,
                    role=req.role,
                    provider=req.provider,
                    model_profile_id=req.model_profile_id,
                    endpoint_url=req.endpoint_url,
                    fallback_model_profile_id=req.fallback_model_profile_id,
                )
            )
            return _dump(route)

    @app.get("/projects/{project_id}/memory")
    async def list_memory_facts(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            return [_dump(fact) for fact in await uow.memory.list_facts(project_id)]

    @app.get("/projects/{project_id}/memory/relevant")
    async def retrieve_relevant_memory(project_id: int, query: str) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            facts = await uow.memory.retrieve_relevant(project_id, query=query)
            return [_dump(fact) for fact in facts]

    @app.post("/projects/{project_id}/memory")
    async def create_memory_fact(project_id: int, req: MemoryFactRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            fact = await uow.memory.create_fact(
                domain.MemoryFact(
                    project_id=project_id,
                    kind=req.kind,
                    fact=req.fact,
                    source=req.source,
                    pinned=req.pinned,
                    status=req.status,
                    tags=req.tags,
                )
            )
            return _dump(fact)

    @app.put("/memory/{fact_id}")
    async def update_memory_fact(fact_id: int, req: MemoryFactUpdateRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            try:
                fact = await uow.memory.update_fact(
                    fact_id,
                    fact=req.fact,
                    pinned=req.pinned,
                    status=req.status,
                    tags=req.tags,
                )
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _dump(fact)

    @app.delete("/memory/{fact_id}")
    async def delete_memory_fact(fact_id: int) -> dict[str, str]:
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            try:
                await uow.memory.delete_fact(fact_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"status": "deleted"}

    @app.get("/projects/{project_id}/memory/export")
    async def export_memory(project_id: int, format: str = "json") -> Response:
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            try:
                payload = await uow.memory.export_backup(project_id, fmt=format)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            media_type = "application/x-yaml" if format == "yaml" else "application/json"
            return Response(content=payload, media_type=media_type)

    @app.post("/projects/{project_id}/memory/import")
    async def import_memory(project_id: int, req: MemoryImportRequest) -> list[dict[str, Any]]:
        payload = req.payload
        if req.format == "json" and isinstance(payload, str):
            payload = json.loads(payload)
        elif req.format == "yaml" and isinstance(payload, str):
            payload = _parse_memory_yaml(payload)
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Invalid memory backup payload")
        async with UnitOfWork(manager) as uow:
            assert uow.memory is not None
            facts = await uow.memory.import_backup(project_id, payload)
            return [_dump(fact) for fact in facts]

    @app.get("/tasks/{task_id}/comments")
    async def list_task_comments(task_id: int, limit: int = 50) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            comments = await uow.coordination.list_task_comments(task_id, limit=limit)
            return [_dump(comment) for comment in comments]

    @app.post("/tasks/{task_id}/comments")
    async def add_task_comment(task_id: int, req: TaskCommentRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.coordination is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            comment = await uow.coordination.add_task_comment(
                domain.TaskComment(
                    project_id=task.project_id,
                    task_id=task_id,
                    author=req.author,
                    body=req.body,
                    thread_id=req.thread_id,
                    metadata=req.metadata,
                )
            )
            return _dump(comment)

    @app.get("/projects/{project_id}/runtimes")
    async def list_project_runtimes(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            runtimes = await uow.coordination.list_runtimes(project_id)
            return [_dump(runtime) for runtime in runtimes]

    @app.post("/projects/{project_id}/runtimes")
    async def register_project_runtime(
        project_id: int, req: RuntimeRegistrationRequest
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            runtime = await uow.coordination.register_runtime(
                domain.RuntimeRegistration(
                    project_id=project_id,
                    runtime_id=req.runtime_id,
                    name=req.name,
                    kind=req.kind,
                    status=req.status,
                    capabilities=req.capabilities,
                    metadata=req.metadata,
                )
            )
            return _dump(runtime)

    @app.post("/runtimes/{runtime_id}/heartbeat")
    async def heartbeat_runtime(
        runtime_id: str, req: RuntimeHeartbeatRequest
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            runtime = await uow.coordination.heartbeat_runtime(
                runtime_id,
                status=req.status,
                metadata=req.metadata,
            )
            if not runtime:
                raise HTTPException(status_code=404, detail="Runtime not found")
            return _dump(runtime)

    @app.get("/tasks/{task_id}/ancestry")
    async def get_task_ancestry(task_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            try:
                return await uow.coordination.task_ancestry(task_id)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.get("/projects/{project_id}/squads")
    async def list_project_squads(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            squads = await uow.coordination.list_squads(project_id)
            return [_dump(squad) for squad in squads]

    @app.post("/projects/{project_id}/squads")
    async def create_project_squad(project_id: int, req: SquadRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.coordination is not None
            squad = await uow.coordination.create_squad(
                domain.Squad(
                    project_id=project_id,
                    name=req.name,
                    purpose=req.purpose,
                    roles=req.roles,
                    agent_ids=req.agent_ids,
                    metadata=req.metadata,
                )
            )
            return _dump(squad)

    @app.get("/projects/{project_id}/squad-composition")
    async def get_squad_composition(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.routing is not None
            composition = []
            for role, meta in domain.SQUAD_ROLE_METADATA.items():
                model_profile_id = None
                provider = "localforge"

                if meta.seniority_class == domain.SeniorityClass.HUMAN:
                    model_profile_id = "Human"
                    provider = "human"
                elif meta.seniority_class == domain.SeniorityClass.DETERMINISTIC_ONLY:
                    model_profile_id = "Deterministic Gate"
                    provider = "harness"
                else:
                    route_val = await uow.routing.get_model_for_role(project_id, meta.default_agent_role)
                    if route_val:
                        model_profile_id = route_val
                        routes = await uow.routing.list_routes(project_id)
                        for r in routes:
                            if r.role == meta.default_agent_role:
                                provider = r.provider
                                break
                    else:
                        if meta.seniority_class in (domain.SeniorityClass.CHIEF_ONLY, domain.SeniorityClass.CHIEF_LED):
                            model_profile_id = "gpt-5.5-large"
                            provider = "openrouter"
                        elif meta.seniority_class == domain.SeniorityClass.LOCAL_ASSISTED:
                            model_profile_id = "granite4.1:8b"
                            provider = "ollama"
                        else:
                            model_profile_id = "local_small"
                            provider = "ollama"

                composition.append({
                    "role": role.value,
                    "seniority_class": meta.seniority_class.value,
                    "responsibility": meta.responsibility,
                    "model_profile_id": model_profile_id,
                    "provider": provider
                })
            return composition


    @app.get("/projects/{project_id}/costs/report")
    async def get_project_costs_report(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.cost_benchmark is not None
            assert uow.simulation is not None
            assert uow.model_calls is not None

            benchmarks = await uow.cost_benchmark.calculate_benchmarks(project_id)

            assert uow.session is not None
            from sqlalchemy import select
            from localforge.storage.orm import ModelCallLedgerORM
            res = await uow.session.execute(
                select(ModelCallLedgerORM).where(ModelCallLedgerORM.project_id == project_id)
            )
            calls = res.scalars().all()

            by_role: dict[str, float] = {}
            by_task: dict[str, float] = {}

            for call in calls:
                cost = call.estimated_cost_usd if call.provider == "openrouter" else 0.0

                is_chief = call.provider == "openrouter" or "chief" in call.reason.lower() or "contract" in call.reason.lower() or "repair" in call.reason.lower() or "review" in call.reason.lower()
                is_small = "pr" in call.reason.lower() or "summary" in call.reason.lower() or "changelog" in call.reason.lower()
                role_name = "Chief Engineer" if is_chief else ("Release Writer" if is_small else "Developer")

                by_role[role_name] = by_role.get(role_name, 0.0) + cost

                if call.task_id:
                    task_key = f"Task #{call.task_id}"
                    by_task[task_key] = by_task.get(task_key, 0.0) + cost

            from localforge.storage.orm import ModelPricingSnapshotORM
            snap_res = await uow.session.execute(select(ModelPricingSnapshotORM))
            snapshots = [_dump(s.to_domain()) for s in snap_res.scalars().all()]

            return {
                "benchmarks": benchmarks,
                "by_role": by_role,
                "by_task": by_task,
                "snapshots": snapshots
            }

    @app.get("/projects/{project_id}/costs/simulate")
    async def get_project_costs_simulation(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.simulation is not None
            return await uow.simulation.simulate_api_only_costs(project_id)

    @app.get("/projects/{project_id}/costs/sources")
    async def get_project_pricing_sources(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.model_calls is not None
            sources = await uow.model_calls.list_pricing_sources()
            return [_dump(s) for s in sources]

    @app.get("/projects/{project_id}/benchmark/rollup")
    async def get_project_benchmark_rollup(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.cost_benchmark is not None
            return await uow.cost_benchmark.calculate_benchmarks(project_id)

    @app.post("/projects/{project_id}/costs/sources")
    async def create_pricing_source(project_id: int, req: PricingSourceCreateRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.model_calls is not None
            source = await uow.model_calls.create_pricing_source(
                domain.PricingSource(
                    provider=req.provider,
                    url=req.url,
                    notes=req.notes
                )
            )
            return _dump(source)

    @app.put("/projects/{project_id}/costs/snapshots")
    async def update_pricing_snapshot(project_id: int, req: PricingSnapshotUpdateRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.model_calls is not None
            snapshot = await uow.model_calls.update_pricing_snapshot(
                pricing_source_id=req.pricing_source_id,
                model_name=req.model_name,
                input_price_per_million=req.input_price_per_million,
                output_price_per_million=req.output_price_per_million,
                cached_input_price_per_million=req.cached_input_price_per_million,
            )
            return _dump(snapshot)




    @app.post("/tasks/{task_id}/pipeline")
    async def run_role_pipeline(task_id: int, req: PipelineRunRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.executions is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            run_id = req.run_id
            if run_id is None:
                run = await uow.executions.create_run(
                    domain.Run(
                        project_id=task.project_id,
                        mode=RunMode.INTERACTIVE,
                        status=RunStatus.RUNNING,
                        initiated_by="role-pipeline",
                    )
                )
                run_id = run.id
            task_run_id = req.task_run_id
            if task_run_id is None:
                task_run = await uow.tasks.create_task_run(
                    domain.TaskRun(
                        run_id=run_id or 0,
                        task_id=task_id,
                        status=TaskRunStatus.RUNNING,
                    )
                )
                task_run_id = task_run.id
            if run_id is None or task_run_id is None:
                raise HTTPException(status_code=500, detail="Pipeline run creation failed")
            result = await RolePipelineEngine(
                uow, project_id=task.project_id, run_id=run_id
            ).run_task(task_id=task_id, task_run_id=task_run_id, mode=req.mode)
            return {
                "mode": result.mode.value,
                "roles": [role.value for role in result.roles],
                "artifact_paths": result.artifact_paths,
                "consumed_handoff_ids": result.consumed_handoff_ids,
                "pr_artifact_path": result.pr_artifact_path,
            }

    @app.get("/projects/{project_id}/prs")
    async def list_prs(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            tasks = await uow.tasks.list_tasks_for_project(project_id)
            return [_dump(task) for task in tasks if task.status == TaskStatus.PR_READY]

    @app.get("/projects/{project_id}/worktrees")
    async def list_project_worktrees(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.audits is not None
            tasks = await uow.tasks.list_tasks_for_project(project_id)
            task_ids = [task.id for task in tasks if task.id is not None]
            runs_by_task = await uow.tasks.list_runs_for_tasks(task_ids)
            worktrees: list[dict[str, Any]] = []
            for task in tasks:
                if task.id is None:
                    continue
                latest = runs_by_task.get(task.id, [None])[0]
                if latest is None or not latest.worktree_path:
                    continue
                dirty = False
                last_commit = None
                if os.path.isdir(latest.worktree_path):
                    status = subprocess.run(
                        ["git", "-C", latest.worktree_path, "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    dirty = bool(status.stdout.strip())
                    commit = subprocess.run(
                        ["git", "-C", latest.worktree_path, "rev-parse", "--short", "HEAD"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if commit.returncode == 0:
                        last_commit = commit.stdout.strip()
                artifacts = (
                    await uow.audits.list_artifacts_for_task_run(latest.id)
                    if latest.id is not None
                    else []
                )
                pr_artifact = next((a for a in artifacts if a.type.value == "PRArtifact"), None)
                cleanup_eligible = task.status in {
                    TaskStatus.DONE,
                    TaskStatus.FAILED_SAFE,
                    TaskStatus.CANCELLED,
                }
                worktrees.append(
                    {
                        "task_id": task.id,
                        "task_key": task.key,
                        "task_status": task.status.value,
                        "branch": latest.branch_name,
                        "path": latest.worktree_path,
                        "dirty": dirty,
                        "last_commit": last_commit,
                        "pr_link": pr_artifact.path if pr_artifact else None,
                        "cleanup_eligible": cleanup_eligible,
                    }
                )
            return worktrees

    @app.post("/tasks/{task_id}/worktree/cleanup")
    async def cleanup_task_worktree(task_id: int) -> dict[str, str]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            manager_obj = WorktreeManager(project_id=task.project_id, uow=uow)
            try:
                await manager_obj.cleanup_worktree(task_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"status": "cleaned"}

    @app.post("/tasks/{task_id}/worktree/revert")
    async def revert_task_worktree(task_id: int, req: WorktreeRevertRequest) -> dict[str, str]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            manager_obj = WorktreeManager(project_id=task.project_id, uow=uow)
            try:
                await manager_obj.rollback_checkpoint(task_id, req.checkpoint_hash)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"status": "reverted"}

    @app.get("/projects/{project_id}/audit-events")
    async def list_audit_events(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            events = await uow.audits.list_audit_events_for_project(project_id)
            return [_dump(event) for event in events]

    @app.get("/projects/{project_id}/audit-events/export")
    async def export_audit_events(project_id: int) -> Response:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            events = await uow.audits.list_audit_events_for_project(project_id)
            payload = json.dumps([_dump(event) for event in events], indent=2)
            return Response(content=payload, media_type="application/json")

    @app.post("/projects/{project_id}/lock")
    async def lock_project(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.audits is not None
            policy = await uow.audits.get_project_policy(project_id, "default")
            if not policy:
                raise HTTPException(status_code=404, detail="Policy not found")
            policy.rules = {**policy.rules, "project_locked": True}
            policy.updated_at = datetime.now(UTC)
            updated = await uow.audits.update_policy(policy)
            return _dump(updated)

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
            approval.decided_at = datetime.now(UTC)
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
                "updated_at": datetime.now(UTC).isoformat(),
                "rules": old_rules
            }
            history.append(history_entry)

            new_rules = rules_validated.model_dump()
            new_rules["history"] = history

            policy.rules = new_rules
            policy.updated_at = datetime.now(UTC)
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
            if latest_run.id is None:
                raise HTTPException(status_code=400, detail="Latest task run has no ID")

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

            if os.getenv("PYTEST_CURRENT_TEST"):
                return {"status": "ok", "path": worktree_path, "opened": False}

            try:
                if hasattr(os, "startfile"):
                    os.startfile(worktree_path)
                else:
                    import subprocess
                    subprocess.run(["open", worktree_path], check=True)
            except Exception as e:
                logger.warning("Failed to open local path %s: %s", worktree_path, e)
                raise HTTPException(
                    status_code=500, detail="Failed to open local path"
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
                logger.warning(
                    "Failed to run discovered test command for task %s: %s",
                    task_id,
                    e,
                )
                raise HTTPException(
                    status_code=500, detail="Failed to run command"
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
                    ActionApprovalORM,
                    ArtifactORM,
                    AuditEventORM,
                    HandoffORM,
                    TaskORM,
                    TaskRunORM,
                )

                tasks_res = await session.execute(
                    select(TaskORM).where(TaskORM.assigned_agent_id == agent_id)
                )
                assigned_tasks = tasks_res.scalars().all()
                assigned_task_ids = [t.id for t in assigned_tasks]

                task_runs: Sequence[TaskRunORM] = ()
                artifacts: Sequence[ArtifactORM] = ()
                approvals: Sequence[ActionApprovalORM] = ()
                logs: Sequence[AuditEventORM] = ()

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
                handoffs: Sequence[HandoffORM] = handoff_res.scalars().all()

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
                refreshed_task = await uow.tasks.get_task(task_id)
                if refreshed_task is None:
                    raise HTTPException(status_code=404, detail="Task not found after update")
                updated = refreshed_task

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
            policy.updated_at = datetime.now(UTC)
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


def _parse_memory_yaml(content: str) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_tags = False
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- id:"):
            if current:
                facts.append(current)
            current = {"tags": []}
            in_tags = False
        elif current is not None and stripped.startswith("fact:"):
            current["fact"] = json.loads(stripped.removeprefix("fact:").strip())
        elif current is not None and stripped.startswith("kind:"):
            current["kind"] = json.loads(stripped.removeprefix("kind:").strip())
        elif current is not None and stripped.startswith("source:"):
            current["source"] = json.loads(stripped.removeprefix("source:").strip())
        elif current is not None and stripped.startswith("pinned:"):
            current["pinned"] = stripped.removeprefix("pinned:").strip() == "true"
        elif current is not None and stripped.startswith("status:"):
            current["status"] = json.loads(stripped.removeprefix("status:").strip())
        elif current is not None and stripped == "tags:":
            in_tags = True
        elif current is not None and in_tags and stripped.startswith("- "):
            current.setdefault("tags", []).append(json.loads(stripped.removeprefix("- ").strip()))
    if current:
        facts.append(current)
    return {"facts": facts}


def _sse(event: LifecycleEvent) -> str:
    payload = json.dumps(event.to_sse_payload(), separators=(",", ":"))
    event_id = event.id if event.id is not None else ""
    return f"id: {event_id}\nevent: {event.event_type}\ndata: {payload}\n\n"
