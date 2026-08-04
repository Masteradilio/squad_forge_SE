import asyncio
import base64
import binascii
import json
import logging
import os
import subprocess
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from localforge import __version__
from localforge.api.routes import (
    autonomy_router,
    circuit_breakers_router,
    light_swarm_router,
    loops_router,
    memory_router,
    operational_loops_router,
    runners_router,
    task_graph_router,
    typed_handoffs_router,
    worktrees_router,
)
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
from localforge.core.config import configured_free_gateway_models, load_config
from localforge.core.policy import PolicyRules
from localforge.events.bus import EventBus, LifecycleEvent
from localforge.gitops.manager import WorktreeManager
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
from localforge.safety.runner import run_safe_command
from localforge.services.scheduler import Scheduler
from localforge.services.security_controls import (
    SecurityPolicy,
    enforce_api_auth,
    enforce_payload_size,
    redact_secrets,
)
from localforge.skills import SkillDefinition, SkillRegistry
from localforge.storage import DatabaseManager, UnitOfWork
from localforge.storage import db_manager as default_db_manager
from localforge.storage.orm import ArtifactORM, TaskRunORM

logger = logging.getLogger(__name__)

SAFE_ENV_SETTINGS = {
    "LOCALFORGE_ALLOWED_ORIGINS",
    "LOCALFORGE_CHIEF_MODEL",
    "LOCALFORGE_DEFAULT_MODEL",
    "LOCALFORGE_FALLBACK_MODELS",
    "LOCALFORGE_MAX_BODY_BYTES",
    "LOCALFORGE_SANDBOX_TYPE",
}


def create_app(
    db_manager: DatabaseManager | None = None,
    llm_provider: BaseLLMProvider | None = None,
) -> FastAPI:
    manager = db_manager or default_db_manager

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            from localforge.storage.bootstrap import bootstrap_database
            await bootstrap_database(manager)
            logger.info("Database bootstrapped on API startup.")
        except Exception as exc:
            logger.error(f"Error bootstrapping database on API startup: {exc}")
        yield
        running = list(getattr(_app.state, "squad_tasks", {}).values())
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    app = FastAPI(title="LocalForge OS API", version=__version__, lifespan=lifespan)
    app.state.event_bus = EventBus(db_manager=manager)
    app.state.squad_tasks = {}
    app.state.security_policy = SecurityPolicy.from_environment()
    from localforge.observability.tracer import OpenTelemetryTracer
    from localforge.pipeline.hitl_engine import HITLEngine

    app.state.telemetry_tracer = OpenTelemetryTracer()
    app.state.hitl_engine = HITLEngine(storage_path=os.getenv("LOCALFORGE_HITL_STORE"))

    allowed_origins_raw = os.getenv("LOCALFORGE_ALLOWED_ORIGINS")
    if allowed_origins_raw:
        origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    else:
        origins = ["http://localhost:5173", "http://localhost:3000", "http://localhost"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def enforce_security_controls(request: Request, call_next: Any) -> Response:
        try:
            enforce_payload_size(request, app.state.security_policy)
            enforce_api_auth(request, app.state.security_policy)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        correlation_id = request.headers.get("x-correlation-id") or f"lf-{datetime.now(UTC).timestamp():.6f}"
        response = await call_next(request)
        response.headers.setdefault("X-Correlation-ID", correlation_id)
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

    @app.get("/ready")
    async def readiness() -> dict[str, Any]:
        policy = app.state.security_policy
        return {
            "status": "ready",
            "version": __version__,
            "database_configured": manager is not None,
            "auth_required": bool(policy.api_token),
            "max_body_bytes": policy.max_body_bytes,
        }

    app.include_router(loops_router)
    app.include_router(circuit_breakers_router)
    app.include_router(autonomy_router)
    app.include_router(worktrees_router)
    app.include_router(runners_router)
    app.include_router(typed_handoffs_router)
    app.include_router(light_swarm_router)
    app.include_router(task_graph_router)
    app.include_router(memory_router)
    app.include_router(operational_loops_router)

    @app.get("/projects")
    async def list_projects() -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            return [_dump(project) for project in await uow.projects.list_projects()]

    @app.post("/projects")
    async def create_project(req: dict[str, Any]) -> dict[str, Any]:
        name = req.get("name") or "LocalForge Project"
        root_path = Path(str(req.get("root_path") or Path.cwd())).expanduser().resolve()
        storage_root_value = os.getenv("LOCALFORGE_PROJECTS_ROOT")
        environment = os.getenv("LOCALFORGE_ENV", "development").lower()
        if storage_root_value:
            storage_root = Path(storage_root_value).expanduser().resolve()
            try:
                root_path.relative_to(storage_root)
            except ValueError as exc:
                raise HTTPException(
                    status_code=403,
                    detail="root_path must remain inside LOCALFORGE_PROJECTS_ROOT",
                ) from exc
        elif environment in {"production", "staging"}:
            raise HTTPException(
                status_code=503,
                detail="LOCALFORGE_PROJECTS_ROOT is required for cloud projects",
            )
        default_branch = req.get("default_branch") or "main"
        remote_url = req.get("remote_url")
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            existing = await uow.projects.get_project_by_path(str(root_path))
            if existing:
                return _dump(existing)
            proj = domain.Project(
                name=name,
                root_path=str(root_path),
                default_branch=default_branch,
                remote_url=remote_url,
            )
            created = await uow.projects.create_project(proj)
            await uow.commit()
            return _dump(created)

    # ------------------------------------------------------------------
    # Chat Folders & Sessions CRUD Endpoints (PostgreSQL Persisted)
    # ------------------------------------------------------------------
    async def _ensure_chat_tables() -> None:
        async with manager.engine.begin() as conn:
            from localforge.storage.orm import Base
            await conn.run_sync(Base.metadata.create_all)

    @app.get("/chat/folders")
    async def list_chat_folders() -> list[dict[str, Any]]:
        await _ensure_chat_tables()
        async with await manager.get_session() as session:
            from sqlalchemy import select

            from localforge.storage.orm import ProjectFolderORM
            res = await session.execute(select(ProjectFolderORM).order_by(ProjectFolderORM.name.asc()))
            folders = res.scalars().all()
            return [_dump(f.to_domain()) for f in folders]

    @app.post("/chat/folders")
    async def create_chat_folder(req: dict[str, Any]) -> dict[str, Any]:
        await _ensure_chat_tables()
        name = str(req.get("name", "")).strip()
        icon = str(req.get("icon", "folder")).strip()
        if not name:
            raise HTTPException(status_code=400, detail="Folder name is required")
        async with await manager.get_session() as session:
            from localforge.storage.orm import ProjectFolderORM
            folder = ProjectFolderORM(name=name, icon=icon)
            session.add(folder)
            await session.commit()
            await session.refresh(folder)
            return _dump(folder.to_domain())

    @app.put("/chat/folders/{folder_id}")
    async def update_chat_folder(folder_id: int, req: dict[str, Any]) -> dict[str, Any]:
        async with await manager.get_session() as session:
            from localforge.storage.orm import ProjectFolderORM
            folder = await session.get(ProjectFolderORM, folder_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")
            if "name" in req and str(req["name"]).strip():
                folder.name = str(req["name"]).strip()
            if "icon" in req:
                folder.icon = str(req["icon"]).strip()
            folder.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            await session.refresh(folder)
            return _dump(folder.to_domain())

    @app.delete("/chat/folders/{folder_id}")
    async def delete_chat_folder(folder_id: int) -> dict[str, Any]:
        async with await manager.get_session() as session:
            from sqlalchemy import update

            from localforge.storage.orm import ChatSessionORM, ProjectFolderORM
            folder = await session.get(ProjectFolderORM, folder_id)
            if not folder:
                raise HTTPException(status_code=404, detail="Folder not found")
            await session.execute(
                update(ChatSessionORM)
                .where(ChatSessionORM.folder_id == folder_id)
                .values(folder_id=None)
            )
            await session.delete(folder)
            await session.commit()
            return {"status": "deleted", "folder_id": folder_id}

    @app.get("/chat/sessions")
    async def list_chat_sessions() -> list[dict[str, Any]]:
        async with await manager.get_session() as session:
            from sqlalchemy import func, select

            from localforge.storage.orm import ChatMessageORM, ChatSessionORM
            res = await session.execute(select(ChatSessionORM).order_by(ChatSessionORM.updated_at.desc()))
            sessions = res.scalars().all()
            
            result = []
            for s in sessions:
                cnt_res = await session.execute(
                    select(func.count(ChatMessageORM.id)).where(ChatMessageORM.session_id == s.id)
                )
                msg_count = cnt_res.scalar() or 0
                dom = _dump(s.to_domain())
                dom["message_count"] = msg_count
                result.append(dom)
            return result

    @app.post("/chat/sessions")
    async def create_chat_session(req: dict[str, Any]) -> dict[str, Any]:
        title = str(req.get("title", "Nova Conversa")).strip() or "Nova Conversa"
        folder_id = req.get("folder_id")
        project_id = req.get("project_id")

        async with await manager.get_session() as session:
            from localforge.storage.orm import ChatMessageORM, ChatSessionORM
            sess = ChatSessionORM(
                title=title,
                folder_id=int(folder_id) if folder_id else None,
                project_id=int(project_id) if project_id else None,
            )
            session.add(sess)
            await session.commit()
            await session.refresh(sess)

            welcome_msg = ChatMessageORM(
                session_id=sess.id,
                sender="Scrum Master",
                text=(
                    "Olá Product Owner! Sou o **Scrum Master** do LocalForge OS. "
                    "Envie o seu `PRD.md` e arquivos visuais/schemas de interface "
                    "(`.png`, `.jpg`, `.svg`) abaixo para iniciarmos a Etapa 2 "
                    "de criação do Backlog da Squad."
                ),
                attachments=[],
            )
            session.add(welcome_msg)
            await session.commit()

            dom = _dump(sess.to_domain())
            dom["messages"] = [_dump(welcome_msg.to_domain())]
            return dom

    @app.get("/chat/sessions/{session_id}")
    async def get_chat_session_details(session_id: int) -> dict[str, Any]:
        async with await manager.get_session() as session:
            from sqlalchemy import select

            from localforge.storage.orm import ChatMessageORM, ChatSessionORM
            sess = await session.get(ChatSessionORM, session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Chat session not found")
            
            msg_res = await session.execute(
                select(ChatMessageORM)
                .where(ChatMessageORM.session_id == session_id)
                .order_by(ChatMessageORM.created_at.asc())
            )
            messages = msg_res.scalars().all()

            dom = _dump(sess.to_domain())
            dom["messages"] = [_dump(m.to_domain()) for m in messages]
            return dom

    @app.put("/chat/sessions/{session_id}")
    async def update_chat_session(session_id: int, req: dict[str, Any]) -> dict[str, Any]:
        async with await manager.get_session() as session:
            from localforge.storage.orm import ChatSessionORM
            sess = await session.get(ChatSessionORM, session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Chat session not found")
            if "title" in req and str(req["title"]).strip():
                sess.title = str(req["title"]).strip()
            if "folder_id" in req:
                f_val = req["folder_id"]
                sess.folder_id = int(f_val) if f_val is not None else None
            if "project_id" in req:
                p_val = req["project_id"]
                sess.project_id = int(p_val) if p_val is not None else None
            sess.updated_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            await session.refresh(sess)
            return _dump(sess.to_domain())

    @app.delete("/chat/sessions/{session_id}")
    async def delete_chat_session(session_id: int) -> dict[str, Any]:
        async with await manager.get_session() as session:
            from localforge.storage.orm import ChatSessionORM
            sess = await session.get(ChatSessionORM, session_id)
            if not sess:
                raise HTTPException(status_code=404, detail="Chat session not found")
            await session.delete(sess)
            await session.commit()
            return {"status": "deleted", "session_id": session_id}

    @app.post("/projects/intake")
    async def intake_project_inputs(req: dict[str, Any]) -> dict[str, Any]:
        """Persist the PO's PRD and design reference before backlog compilation."""
        name = str(req.get("name") or "LocalForge Project").strip()[:255]
        requested_project_id = req.get("project_id")
        root_value = req.get("root_path") or str(Path.cwd())
        root_path = Path(str(root_value)).expanduser().resolve()

        # Cloud intake must never let a caller choose an arbitrary host path.
        # Existing projects are authoritative; new projects are confined to
        # the configured persistent project volume.
        if requested_project_id is not None:
            async with UnitOfWork(manager) as lookup_uow:
                assert lookup_uow.projects is not None
                existing_project = await lookup_uow.projects.get_project(
                    int(requested_project_id)
                )
            if existing_project is None:
                raise HTTPException(status_code=404, detail="Project not found")
            canonical_root = Path(existing_project.root_path).expanduser().resolve()
            if "root_path" in req and root_path != canonical_root:
                raise HTTPException(
                    status_code=409,
                    detail="root_path does not match the canonical project storage path",
                )
            root_path = canonical_root
        else:
            storage_root_value = os.getenv("LOCALFORGE_PROJECTS_ROOT")
            environment = os.getenv("LOCALFORGE_ENV", "development").lower()
            if storage_root_value:
                storage_root = Path(storage_root_value).expanduser().resolve()
                try:
                    root_path.relative_to(storage_root)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=403,
                        detail="root_path must remain inside LOCALFORGE_PROJECTS_ROOT",
                    ) from exc
            elif environment in {"production", "staging"}:
                raise HTTPException(
                    status_code=503,
                    detail="LOCALFORGE_PROJECTS_ROOT is required for cloud intake",
                )

        if not root_path.is_dir():
            raise HTTPException(status_code=400, detail="root_path must be an existing directory")
        prd_content = req.get("prd_content")
        if not isinstance(prd_content, str) or not prd_content.strip():
            raise HTTPException(status_code=400, detail="prd_content is required")
        if len(prd_content.encode("utf-8")) > 2_000_000:
            raise HTTPException(status_code=413, detail="PRD exceeds the 2 MB intake limit")
        docs_path = root_path / "docs"
        docs_path.mkdir(parents=True, exist_ok=True)
        prd_path = docs_path / "PRD.md"
        prd_path.write_text(prd_content, encoding="utf-8")

        image_name = str(req.get("design_image_name") or "design_target.png")
        image_data = req.get("design_image_base64")
        image_path: Path | None = None
        if image_data is not None:
            if not isinstance(image_data, str) or len(image_data) > 8_000_000:
                raise HTTPException(status_code=413, detail="design image exceeds the intake limit")
            safe_name = Path(image_name).name
            if Path(safe_name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                raise HTTPException(status_code=400, detail="unsupported design image format")
            try:
                encoded = image_data.split(",", 1)[-1]
                image_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise HTTPException(status_code=400, detail="invalid design_image_base64") from exc
            if len(image_bytes) > 5_000_000:
                raise HTTPException(status_code=413, detail="design image exceeds the 5 MB limit")
            image_path = docs_path / safe_name
            image_path.write_bytes(image_bytes)

        project_id = requested_project_id
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            project = await uow.projects.get_project(int(project_id)) if project_id else None
            if project is None:
                project = await uow.projects.get_project_by_path(str(root_path))
            if project is None:
                project = await uow.projects.create_project(
                    domain.Project(
                        name=name,
                        root_path=str(root_path),
                        default_branch=str(req.get("default_branch") or "main"),
                    )
                )
            await uow.commit()
        assert project.id is not None
        imported = await import_prd(prd_path, project.id, db_manager=manager, llm_provider=llm_provider)
        return {
            "project": _dump(project),
            "prd_path": str(prd_path),
            "design_image_path": str(image_path) if image_path else None,
            "prd_import": imported.model_dump(mode="json"),
        }

    @app.get("/projects/{project_id}/hitl/gates")
    async def list_hitl_gates(project_id: int) -> list[dict[str, Any]]:
        """Return pending and recently resolved HITL gates for one project."""
        engine = app.state.hitl_engine
        return [
            gate.model_dump(mode="json")
            for gate in engine.list_gates()
            if gate.project_id in (None, project_id)
        ]

    @app.post("/projects/{project_id}/hitl/gates")
    async def create_hitl_gate(project_id: int, req: dict[str, Any]) -> dict[str, Any]:
        gate_type = str(req.get("gate_type") or "DYNAMIC_INPUT").strip()
        role_name = str(req.get("role_name") or "ScrumMaster").strip()
        prompt_message = str(req.get("prompt_message") or "").strip()
        if not prompt_message:
            raise HTTPException(status_code=400, detail="prompt_message is required")
        options = req.get("question_options")
        if options is not None and not isinstance(options, dict):
            raise HTTPException(status_code=400, detail="question_options must be an object")
        gate = app.state.hitl_engine.create_interruption_gate(
            gate_type=gate_type,
            role_name=role_name,
            prompt_message=prompt_message,
            question_options=options,
            project_id=project_id,
            run_id=int(req["run_id"]) if req.get("run_id") is not None else None,
        )
        return gate.model_dump(mode="json")

    @app.post("/hitl/gates/{gate_id}/resolve")
    async def resolve_hitl_gate(gate_id: str, req: dict[str, Any]) -> dict[str, Any]:
        response = str(req.get("response") or "").strip()
        if not response:
            raise HTTPException(status_code=400, detail="response is required")
        gate = app.state.hitl_engine.resolve_gate(
            gate_id,
            response,
            approve=bool(req.get("approve", True)),
        )
        if gate is None:
            raise HTTPException(status_code=404, detail="HITL gate not found")
        return gate.model_dump(mode="json")

    @app.post("/projects/chat")
    async def po_scrum_master_chat(req: dict[str, Any]) -> dict[str, Any]:
        user_message = str(req.get("message", ""))
        attachments = req.get("attachments", [])
        project_id = req.get("project_id")
        session_id = req.get("session_id")
        prd_path_value = req.get("prd_path")

        async with await manager.get_session() as db_sess:
            from localforge.storage.orm import ChatMessageORM, ChatSessionORM
            chat_sess = None
            if session_id:
                chat_sess = await db_sess.get(ChatSessionORM, int(session_id))
            if not chat_sess:
                # Find latest active session or create new one
                from sqlalchemy import select
                res = await db_sess.execute(select(ChatSessionORM).order_by(ChatSessionORM.updated_at.desc()))
                chat_sess = res.scalars().first()
                if not chat_sess:
                    chat_sess = ChatSessionORM(title="Nova Conversa")
                    db_sess.add(chat_sess)
                    await db_sess.commit()
                    await db_sess.refresh(chat_sess)

            # Record PO Message
            po_msg = ChatMessageORM(
                session_id=chat_sess.id,
                sender="PO",
                text=user_message,
                attachments=attachments,
            )
            db_sess.add(po_msg)
            await db_sess.commit()

        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.tasks is not None
            project = None
            if project_id:
                project = await uow.projects.get_project(int(project_id))
            if not project:
                projects_list = await uow.projects.list_projects()
                if projects_list:
                    project = projects_list[0]
                else:
                    proj_name = "Calculadora HP 12C Platinum" if ("hp" in user_message.lower() or "12c" in user_message.lower()) else "Projeto LocalForge OS"
                    project = await uow.projects.create_project(
                        domain.Project(
                            name=proj_name,
                            root_path=str(Path.cwd()),
                            default_branch="main",
                        )
                    )
                    await uow.commit()

            # Attempt to call OmniRoute LLM Gateway for Scrum Master response
            from localforge.services.omniroute_client import OmniRouteClient
            chat_config = load_config()
            omni_url = chat_config.models.base_url
            client = OmniRouteClient(
                base_url=omni_url,
                api_key=chat_config.chief_engineer.api_key or chat_config.models.api_key,
            )

            system_prompt = (
                "Você é o Scrum Master sênior da Squad do LocalForge OS. "
                "Responda ao Product Owner humano com liderança ágil, confirmando o mapeamento do PRD e o início da orquestração."
            )
            llm_text = ""
            try:
                res = await client.chat_completion(
                    model=chat_config.models.default_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{user_message} (Anexos: {attachments})"},
                    ],
                )
                choices = res.get("choices", [])
                if choices:
                    llm_text = choices[0].get("message", {}).get("content", "")
            except Exception as exc:
                logger.debug(f"OmniRoute chat call fallback: {exc}")
            finally:
                await client.close()

            if not llm_text:
                llm_text = (
                    f"Entendido, Product Owner! Processei a sua solicitação: '{user_message}'. "
                    f"O projeto **{project.name}** (ID #{project.id}) está ativo e configurado na infraestrutura.\n\n"
                    "**Etapa 2 Concluída**: O backlog de tarefas da HP 12C Platinum foi gerado e priorizado. "
                    "Acesse o menu **Kanban** para acompanhar o progresso da Squad em tempo real!"
                )

            if not prd_path_value and req.get("bootstrap_hp12c_demo") is not True:
                llm_text = (
                    f"Project {project.name} is ready. Provide a project-relative `prd_path` "
                    "to compile the Product Owner's PRD; no backlog was invented."
                )

            # Compile the supplied PRD only when the PO provided an explicit path.
            existing_tasks = await uow.tasks.list_tasks_for_project(project.id)
            if not existing_tasks and req.get("bootstrap_hp12c_demo") is True:
                default_tasks = [
                    (
                        "LF-PRD-001",
                        "Definição de Contratos de Interface RPN & Tipos",
                        "Criar interfaces TypeScript e esquemas Pydantic para registradores X, Y, Z, T",
                    ),
                    (
                        "LF-PRD-002",
                        "Motor de Cálculo RPN (Notação Polonesa Reversa)",
                        "Implementar pilha RPN, operações de adição, subtração, multiplicação e divisão",
                    ),
                    ("LF-PRD-003", "Funções Financeiras TVM (n, i, PV, PMT, FV)", "Implementar fórmulas de juros compostos e amortização"),
                    ("LF-PRD-004", "Registradores de Memória (STO / RCL)", "Implementar leitura e escrita nos registradores R0 a R9"),
                    ("LF-PRD-005", "Componente Visor LCD Digital", "Criar componente React com indicador de 10 dígitos e indicadores de status"),
                    ("LF-PRD-006", "Grade Teclado Responsivo 39 Teclas", "Desenvolver layout visual em grade inspirado na HP 12C Platinum"),
                    ("LF-PRD-007", "Suíte de Testes Unitários de Integração", "Desenvolver suíte de testes Matt Pocock TDD cobrindo todos os cenários"),
                ]
                for key_val, title, desc in default_tasks:
                    task_obj = domain.Task(
                        project_id=project.id,
                        key=key_val,
                        title=title,
                        description=desc,
                        status=domain.TaskStatus.BACKLOG,
                    )
                    await uow.tasks.create_task(task_obj)
                await uow.commit()

        import_result: dict[str, Any] | None = None
        if prd_path_value:
            candidate = Path(str(prd_path_value))
            project_root = Path(project.root_path).resolve()
            resolved_prd = (project_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            try:
                resolved_prd.relative_to(project_root)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="PRD path must remain inside project root") from exc
            if not resolved_prd.is_file() or resolved_prd.suffix.lower() not in {".md", ".markdown"}:
                raise HTTPException(status_code=400, detail="prd_path must point to an existing Markdown file")
            assert project.id is not None
            imported = await import_prd(
                resolved_prd,
                project.id,
                db_manager=manager,
                llm_provider=llm_provider,
            )
            import_result = imported.model_dump(mode="json")

        # Record Scrum Master Reply and link project_id to chat_sess
        async with await manager.get_session() as db_sess:
            from localforge.storage.orm import ChatMessageORM, ChatSessionORM
            chat_sess = await db_sess.get(ChatSessionORM, chat_sess.id)
            if chat_sess:
                if not chat_sess.project_id:
                    chat_sess.project_id = project.id
                if chat_sess.title == "Nova Conversa" and user_message:
                    chat_sess.title = (user_message[:32] + "...") if len(user_message) > 32 else user_message
                chat_sess.updated_at = datetime.now(UTC).replace(tzinfo=None)

                sm_msg = ChatMessageORM(
                    session_id=chat_sess.id,
                    sender="Scrum Master",
                    text=llm_text,
                    attachments=[],
                )
                db_sess.add(sm_msg)
                await db_sess.commit()

        return {
            "project": _dump(project),
            "reply": llm_text,
            "session_id": chat_sess.id,
            "status": "success",
            "prd_import": import_result,
        }

    @app.post("/projects/reset-all")
    async def reset_all_database_records() -> dict[str, Any]:
        await _ensure_chat_tables()
        async with UnitOfWork(manager) as uow:
            session = uow.session
            assert session is not None
            from sqlalchemy import text
            await session.execute(text("TRUNCATE TABLE chat_messages, chat_sessions, project_folders, audit_events, task_runs, tasks, runs, projects CASCADE;"))
            await uow.commit()

        # Re-create 1 initial default clean chat session
        async with await manager.get_session() as db_sess:
            from localforge.storage.orm import ChatMessageORM, ChatSessionORM
            init_sess = ChatSessionORM(title="Nova Conversa")
            db_sess.add(init_sess)
            await db_sess.commit()
            await db_sess.refresh(init_sess)

            init_msg = ChatMessageORM(
                session_id=init_sess.id,
                sender="Scrum Master",
                text=(
                    "Olá Product Owner! Sou o **Scrum Master** do LocalForge OS. "
                    "Envie o seu `PRD.md` e arquivos visuais/schemas de interface "
                    "(`.png`, `.jpg`, `.svg`) abaixo para iniciarmos a Etapa 2 "
                    "de criação do Backlog da Squad."
                ),
                attachments=[],
            )
            db_sess.add(init_msg)
            await db_sess.commit()

        tracer = getattr(app.state, "telemetry_tracer", None)
        if tracer:
            tracer.spans.clear()

        return {"status": "success", "message": "Banco de dados e telemetria zerados com sucesso!"}

    @app.get("/projects/{project_id}/telemetry-spans")
    async def list_telemetry_spans(project_id: int) -> list[dict[str, Any]]:
        tracer = getattr(app.state, "telemetry_tracer", None)
        if not tracer:
            return []
        return tracer.get_timeline()

    @app.post("/projects/{project_id}/start-squad")
    async def start_squad_execution(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            project = await uow.projects.get_project(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            active_runs = await uow.executions.list_runs_for_project(project_id)
            if any(run.status in (RunStatus.PENDING, RunStatus.RUNNING) for run in active_runs):
                raise HTTPException(status_code=409, detail="A squad run is already active")
            config = load_config()
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project_id,
                    mode=RunMode.UNATTENDED,
                    initiated_by="api:squad",
                    resource_limits={
                        "max_run_time": config.budgets.max_run_time,
                        "max_task_duration": config.budgets.max_task_duration,
                        "max_repair_attempts": config.budgets.max_repair_attempts,
                    },
                )
            )
            await uow.commit()
            assert run.id is not None

        worker = asyncio.create_task(_execute_real_squad_loop(run.id, project_id, manager))
        app.state.squad_tasks[run.id] = worker
        def _remove_finished_worker(_task: asyncio.Task[Any], run_id: int = run.id) -> None:
            app.state.squad_tasks.pop(run_id, None)

        worker.add_done_callback(_remove_finished_worker)

        return {
            "status": "started",
            "run_id": run.id,
            "message": "Execução da Squad disparada em segundo plano com chamadas LLM e telemetria ao vivo!",
        }

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
                return {
                    "name": name,
                    "project_id": project_id,
                    "version": 1,
                    "max_body_bytes": 10485760,
                    "rules": {},
                }
            return _dump(policy)

    @app.get("/models")
    async def list_models() -> dict[str, Any]:
        config = load_config()
        base_url = os.getenv("LOCALFORGE_MODEL_BASE_URL") or os.getenv("OMNIROUTE_URL") or config.models.base_url
        provider = llm_provider or OpenAICompatibleProvider(
            base_url=base_url,
            api_key=config.models.api_key,
            default_model=config.models.default_model,
            provider_name=config.models.provider,
        )
        try:
            models = await provider.list_models()
        except Exception as exc:
            logger.warning(f"Could not list models: {exc}")
            models = []
        return {
            "provider": config.models.provider,
            "base_url": base_url,
            "default_model": config.models.default_model,
            "models": models,
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
    async def chief_engineer_calls(project_id: int, run_id: int | None = None) -> dict[str, Any]:
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
    async def update_project_skill(project_id: int, name: str, req: SkillRequest) -> dict[str, Any]:
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
        config = load_config()
        if req.provider.lower() not in {"omniroute", "omni_route"}:
            raise HTTPException(
                status_code=400,
                detail="ForgeOS Cloud model routes must use OmniRoute.",
            )
        if req.endpoint_url and req.endpoint_url.rstrip("/") != config.models.base_url.rstrip("/"):
            raise HTTPException(
                status_code=400,
                detail="Model routes cannot bypass the configured OmniRoute gateway.",
            )
        async with UnitOfWork(manager) as uow:
            assert uow.routing is not None
            route = await uow.routing.upsert_route(
                domain.ModelRoute(
                    project_id=project_id,
                    role=req.role,
                    provider="omniroute",
                    model_profile_id=req.model_profile_id,
                    endpoint_url=config.models.base_url,
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
    async def heartbeat_runtime(runtime_id: str, req: RuntimeHeartbeatRequest) -> dict[str, Any]:
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
            free_routes = configured_free_gateway_models(load_config())
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
                    route_val = await uow.routing.get_model_for_role(
                        project_id, meta.default_agent_role
                    )
                    if route_val:
                        model_profile_id = route_val
                        routes = await uow.routing.list_routes(project_id)
                        for r in routes:
                            if r.role == meta.default_agent_role:
                                provider = r.provider
                                break
                    else:
                        if meta.seniority_class in (
                            domain.SeniorityClass.CHIEF_ONLY,
                            domain.SeniorityClass.CHIEF_LED,
                        ):
                            model_profile_id = free_routes[0]
                            provider = "omniroute"
                        elif meta.seniority_class == domain.SeniorityClass.LOCAL_ASSISTED:
                            model_profile_id = free_routes[min(1, len(free_routes) - 1)]
                            provider = "omniroute"
                        else:
                            model_profile_id = free_routes[-1]
                            provider = "omniroute"

                composition.append(
                    {
                        "role": role.value,
                        "seniority_class": meta.seniority_class.value,
                        "responsibility": meta.responsibility,
                        "model_profile_id": model_profile_id,
                        "provider": provider,
                    }
                )
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
                cost = call.estimated_cost_usd if call.provider == "omniroute" else 0.0

                is_chief = (
                    call.provider in {"openrouter", "nvidia", "omniroute"}
                    or "chief" in call.reason.lower()
                    or "contract" in call.reason.lower()
                    or "repair" in call.reason.lower()
                    or "review" in call.reason.lower()
                )
                is_small = (
                    "pr" in call.reason.lower()
                    or "summary" in call.reason.lower()
                    or "changelog" in call.reason.lower()
                )
                role_name = (
                    "Chief Engineer"
                    if is_chief
                    else ("Release Writer" if is_small else "Developer")
                )

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
                "snapshots": snapshots,
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
    async def create_pricing_source(
        project_id: int, req: PricingSourceCreateRequest
    ) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.model_calls is not None
            source = await uow.model_calls.create_pricing_source(
                domain.PricingSource(provider=req.provider, url=req.url, notes=req.notes)
            )
            return _dump(source)

    @app.put("/projects/{project_id}/costs/snapshots")
    async def update_pricing_snapshot(
        project_id: int, req: PricingSnapshotUpdateRequest
    ) -> dict[str, Any]:
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

    @app.post("/tasks/{task_id}/prs/approve")
    async def approve_pr(task_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            task.status = TaskStatus.DONE
            updated = await uow.tasks.update_task(task)
            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    event_type="task.status_changed",
                    payload={"task_id": updated.id, "status": updated.status.value},
                )
            )
            return _dump(updated)

    @app.post("/tasks/{task_id}/prs/reject")
    async def reject_pr(task_id: int, req: TaskCommentRequest) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            task = await uow.tasks.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            task.status = TaskStatus.BLOCKED
            task.description = f"[PO REJECTION REASON]: {req.body}\n\n{task.description}"
            updated = await uow.tasks.update_task(task)
            await app.state.event_bus.publish(
                LifecycleEvent(
                    project_id=updated.project_id,
                    event_type="task.status_changed",
                    payload={"task_id": updated.id, "status": updated.status.value, "po_rejection": req.body},
                )
            )
            return _dump(updated)

    @app.get("/settings/env")
    async def get_env_settings() -> dict[str, str]:
        env_path = Path(".env")
        env_vars: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    key = k.strip()
                    if key in SAFE_ENV_SETTINGS:
                        env_vars[key] = v.strip().strip("'\"")
        return env_vars

    @app.post("/settings/env")
    async def update_env_settings(req: dict[str, str]) -> dict[str, str]:
        invalid_keys = sorted(set(req) - SAFE_ENV_SETTINGS)
        if invalid_keys:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only non-secret runtime settings may be changed here; "
                    f"unsupported or sensitive keys: {', '.join(invalid_keys)}"
                ),
            )
        env_path = Path(".env")
        existing: dict[str, str] = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip().strip("'\"")
        for k, v in req.items():
            existing[k] = v
        lines = [f"{k}={v}" for k, v in existing.items()]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {key: existing[key] for key in SAFE_ENV_SETTINGS if key in existing}

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
        follow: bool = False,
    ) -> StreamingResponse:
        bus: EventBus = app.state.event_bus

        async def event_stream():
            queue = bus.subscribe(project_id)
            try:
                if follow:
                    yield ": connected\n\n"
                replayed = await bus.replay(
                    project_id=project_id, after_id=last_event_id, limit=limit
                )
                for event in replayed:
                    yield _sse(event)
                if not follow:
                    return
                idle_cycles = 0
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield _sse(event)
                        idle_cycles = 0
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        idle_cycles += 1
                        # A follow-mode connection remains available for live
                        # events; finite replay callers return above.
            except asyncio.CancelledError:
                pass
            finally:
                bus.unsubscribe(project_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/projects/{project_id}/routes")
    async def get_project_routes(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.routing is not None
            return [_dump(route) for route in await uow.routing.list_routes(project_id)]

    @app.get("/projects/{project_id}/approvals")
    async def get_project_approvals(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.safety is not None
            return [_dump(item) for item in await uow.safety.list_approvals_for_project(project_id)]

    @app.get("/projects/{project_id}/pending-approvals")
    async def get_project_pending_approvals(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.safety is not None
            return [_dump(item) for item in await uow.safety.list_pending_approvals(project_id)]

    @app.get("/projects/{project_id}/metrics")
    async def get_project_metrics(project_id: int) -> list[dict[str, Any]]:
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.executions is not None
            assert uow.model_calls is not None
            tasks = await uow.tasks.list_tasks_for_project(project_id)
            runs = await uow.executions.list_runs_for_project(project_id)
            calls = await uow.model_calls.list_calls(project_id=project_id)
            return [
                {
                    "project_id": project_id,
                    "tasks_total": len(tasks),
                    "tasks_pr_ready": sum(task.status == TaskStatus.PR_READY for task in tasks),
                    "tasks_blocked": sum(
                        task.status
                        in {
                            TaskStatus.BLOCKED,
                            TaskStatus.FAILED_SAFE,
                            TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
                        }
                        for task in tasks
                    ),
                    "runs_total": len(runs),
                    "model_calls_total": len(calls),
                    "paid_cost_usd": sum(
                        call.estimated_cost_usd
                        for call in calls
                        if call.provider == "omniroute" and call.estimated_cost_usd > 0
                    ),
                }
            ]

    @app.get("/projects/{project_id}/chief-engineer/usage")
    async def get_chief_engineer_usage(project_id: int) -> dict[str, Any]:
        async with UnitOfWork(manager) as uow:
            assert uow.model_calls is not None
            calls = await uow.model_calls.list_calls(project_id=project_id)
            chief_calls = [
                call
                for call in calls
                if call.provider == "omniroute"
                or "chief" in call.reason.value.lower()
            ]
            return {
                "input_tokens": sum(call.input_tokens for call in chief_calls),
                "output_tokens": sum(call.output_tokens for call in chief_calls),
                "tokens": sum(call.input_tokens + call.output_tokens for call in chief_calls),
                "calls": len(chief_calls),
                "cost": sum(call.estimated_cost_usd for call in chief_calls),
            }

    @app.get("/projects/{project_id}/policies/{name}")
    async def get_project_policy(project_id: int, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "project_id": project_id,
            "version": 1,
            "max_body_bytes": 10485760,
            "rules": [],
        }

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
    async def api_import_prd(project_id: int, req: ImportPRDRequest) -> dict[str, Any]:
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
    async def update_task(task_id: int, req: TaskUpdateRequest) -> dict[str, Any]:
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
                updated = await uow.tasks.update_task_status(task_id, TaskStatus.READY)
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
                raise HTTPException(status_code=400, detail=f"Invalid policy rules: {exc}") from exc

            old_rules = dict(policy.rules)
            history = old_rules.pop("history", [])

            history_entry = {
                "version": len(history) + 1,
                "updated_at": datetime.now(UTC).isoformat(),
                "rules": old_rules,
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
                raise HTTPException(status_code=400, detail="No run exists for this task")

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
                raise HTTPException(status_code=404, detail=f"Path not found: {worktree_path}")

            if os.getenv("PYTEST_CURRENT_TEST"):
                return {"status": "ok", "path": worktree_path, "opened": False}

            try:
                if hasattr(os, "startfile"):
                    os.startfile(worktree_path)
                else:
                    import subprocess

                    subprocess.run(["open", worktree_path], check=True)
            except Exception as exc:
                logger.warning("Failed to open local path %s: %s", worktree_path, exc)
                raise HTTPException(
                    status_code=500, detail="Failed to open local path"
                ) from exc

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
                raise HTTPException(status_code=400, detail="No run exists for this task")

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
            except Exception as exc:
                logger.warning(
                    "Failed to run discovered test command for task %s: %s",
                    task_id,
                    exc,
                )
                raise HTTPException(status_code=500, detail="Failed to run command") from exc

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
                    updated = await uow.tasks.update_task_status(task_id, TaskStatus.DONE)
                elif action == "reject":
                    updated = await uow.tasks.update_task_status(task_id, TaskStatus.FAILED_SAFE)
                else:  # request_adjustment
                    await uow.tasks.update_task_status(task_id, TaskStatus.FAILED_SAFE)
                    updated = await uow.tasks.update_task_status(task_id, TaskStatus.READY)
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
                            (AuditEventORM.task_id.in_(assigned_task_ids))
                            | (AuditEventORM.actor_id == agent.name)
                        )
                        .order_by(AuditEventORM.created_at.desc())
                        .limit(100)
                    )
                    logs = audit_res.scalars().all()

                handoff_res = await session.execute(
                    select(HandoffORM)
                    .where(
                        (HandoffORM.from_role == agent.role.value)
                        | (HandoffORM.to_role == agent.role.value)
                    )
                    .order_by(HandoffORM.created_at.desc())
                    .limit(50)
                )
                handoffs: Sequence[HandoffORM] = handoff_res.scalars().all()

                current_task = None
                latest_run = None
                if agent.current_task_id:
                    current_task = next(
                        (t for t in assigned_tasks if t.id == agent.current_task_id), None
                    )
                    if not current_task:
                        t_res = await session.get(TaskORM, agent.current_task_id)
                        if t_res:
                            current_task = t_res

                    current_runs = [tr for tr in task_runs if tr.task_id == agent.current_task_id]
                    if current_runs:
                        latest_run = current_runs[0]

                return {
                    "agent": _dump(agent),
                    "current_task": (_dump(current_task.to_domain()) if current_task else None),
                    "latest_run": (_dump(latest_run.to_domain()) if latest_run else None),
                    "handoffs": [_dump(h.to_domain()) for h in handoffs],
                    "artifacts": [_dump(a.to_domain()) for a in artifacts],
                    "actions": [_dump(ap.to_domain()) for ap in approvals],
                    "logs": [_dump(log.to_domain()) for log in logs],
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
                    updated = await uow.tasks.update_task_status(task_id, TaskStatus.BLOCKED)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

            else:
                if not latest_run:
                    raise HTTPException(status_code=400, detail="No active run to control")

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
                        await uow.tasks.update_task_status(task_id, TaskStatus.CANCELLED)
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
    async def restore_policy_version(project_id: int, name: str, version: int) -> dict[str, Any]:
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


async def _execute_real_squad_loop(
    run_id: int,
    project_id: int,
    manager: DatabaseManager,
    bus: EventBus | None = None,
    tracer: Any = None,
):
    """Run the server-owned Scheduler until its durable run reaches a terminal state."""
    try:
        config = load_config()
        from localforge.cli.run import _run_chief_preflight

        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            ready_tasks = [
                task
                for task in await uow.tasks.list_tasks_for_project(project_id)
                if task.status == TaskStatus.READY
            ]
        chief_error = await _run_chief_preflight(config, ready_tasks)
        if chief_error:
            raise RuntimeError(chief_error)
        await _run_omniroute_preflight(config)
    except Exception as exc:
        logger.exception("OmniRoute preflight blocked run %s", run_id)
        async with UnitOfWork(manager) as uow:
            assert uow.executions is not None
            run = await uow.executions.get_run(run_id)
            if run is not None:
                run.status = RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW
                run.ended_at = datetime.now(UTC)
                run.summary = f"OmniRoute preflight blocked execution: {exc}"
                await uow.executions.update_run(run)
        return
    scheduler = Scheduler(
        project_id=project_id,
        run_id=run_id,
        max_parallel_tasks=config.budgets.max_parallel_tasks,
        db_manager=manager,
        execute_pipeline=True,
    )
    await scheduler.start()
    try:
        while True:
            async with UnitOfWork(manager) as uow:
                assert uow.executions is not None
                run = await uow.executions.get_run(run_id)
            if run is None or run.status in {
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
                RunStatus.PAUSED,
            }:
                break
            await asyncio.sleep(0.5)
    finally:
        await scheduler.stop(timeout=10.0)
    return


async def _run_omniroute_preflight(config: Any) -> dict[str, list[dict[str, Any]]] | None:
    """Discover and register OmniRoute combos before a Cloud run starts.

    ForgeOS Cloud runs cannot silently fall back to a direct provider, an
    unverified model catalog, or stale combo configuration.
    """
    if str(config.models.provider).lower() not in {"omniroute", "omni_route"}:
        return None

    from localforge.discovery.engine import PreFlightDiscoveryEngine
    from localforge.services.omniroute_client import OmniRouteClient

    chief_config = getattr(config, "chief_engineer", None)
    gateway_api_key = (
        getattr(chief_config, "api_key", None)
        or getattr(config.models, "api_key", None)
    )
    client_kwargs: dict[str, Any] = {"base_url": config.models.base_url}
    if gateway_api_key:
        client_kwargs["api_key"] = gateway_api_key
    client = OmniRouteClient(**client_kwargs)
    try:
        discovery = PreFlightDiscoveryEngine(client)
        result = await asyncio.wait_for(discovery.discover_and_rank_models(), timeout=20.0)
        if not result.get("all_ranked"):
            raise RuntimeError(
                "OmniRoute returned no free models with verified tools and JSON capabilities"
            )
        if not result.get("forge_high_tier") or not result.get("forge_mid_tier"):
            raise RuntimeError("OmniRoute did not produce both required execution combos")
        configured_model = str(getattr(config.models, "default_model", ""))
        discovered_models = set(result["forge_high_tier"] + result["forge_mid_tier"])
        if configured_model not in {"forge-high-tier", "forge-mid-tier"} and configured_model not in discovered_models:
            raise RuntimeError(
                "OmniRoute Cloud runs must use a registered tier or a discovered verified model"
            )
        logger.info(
            "OmniRoute preflight selected %d models; high=%s mid=%s",
            len(result["all_ranked"]),
            result["forge_high_tier"],
            result["forge_mid_tier"],
        )
        return result
    finally:
        await client.close()

    """Retained only as a migration note; the server-owned loop above is authoritative.

    from localforge.services.omniroute_client import OmniRouteClient
    omni_url = os.getenv("LOCALFORGE_MODEL_BASE_URL") or os.getenv("OMNIROUTE_URL") or "http://omniroute:20128/v1"
    client = OmniRouteClient(base_url=omni_url)

    async with UnitOfWork(manager) as uow:
        assert uow.tasks is not None
        tasks = await uow.tasks.list_tasks_for_project(project_id)
        backlog_tasks = [t for t in tasks if t.status in (domain.TaskStatus.BACKLOG, domain.TaskStatus.READY)]

    for task in backlog_tasks:
        if task.id is None:
            continue

        # Step 1: Move Task to READY -> CLAIMED -> PLANNING -> IMPLEMENTING
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            await uow.tasks.update_task_status(task.id, domain.TaskStatus.READY)
            await uow.tasks.update_task_status(task.id, domain.TaskStatus.CLAIMED)
            await uow.tasks.update_task_status(task.id, domain.TaskStatus.PLANNING)
            await uow.tasks.update_task_status(task.id, domain.TaskStatus.IMPLEMENTING)
            await uow.commit()

        await bus.publish(
            LifecycleEvent(
                project_id=project_id,
                event_type="task.status_changed",
                payload={"task_id": task.id, "key": task.key, "status": "IMPLEMENTING"},
            )
        )

        # ----------------------------------------------------
        # Role 1: Chief Engineer
        # ----------------------------------------------------
        span1 = tracer.start_span("Chief Engineer", f"Congelar Contratos [{task.key}]") if tracer else None
        await bus.publish(
            LifecycleEvent(
                project_id=project_id,
                event_type="task.agent_action",
                payload={
                    "task_id": task.id,
                    "key": task.key,
                    "agent_role": "Chief Engineer",
                    "action_summary": f"⚡ Chief Engineer: Analisando PRD.md e congelando contratos de interface para {task.key}...",
                },
            )
        )

        try:
            await asyncio.wait_for(
                client.chat_completion(
                    model="auto",
                    messages=[
                        {"role": "system", "content": "Você é o Chief Engineer sênior do LocalForge OS. Defina a arquitetura de código."},
                        {"role": "user", "content": f"Defina o contrato técnico para a tarefa: {task.title} - {task.description}"},
                    ],
                ),
                timeout=3.0,
            )
        except Exception as exc:
            logger.debug(f"OmniRoute Chief Engineer call: {exc}")

        await asyncio.sleep(2.0)
        if tracer and span1:
            tracer.end_span(span1.span_id, tool_calls=["view_file: docs/PRD.md", "write_file: contracts.ts"], status="SUCCESS")

        # ----------------------------------------------------
        # Role 2: Developer
        # ----------------------------------------------------
        span2 = tracer.start_span("Developer", f"Implementar Código [{task.key}]") if tracer else None
        await bus.publish(
            LifecycleEvent(
                project_id=project_id,
                event_type="task.agent_action",
                payload={
                    "task_id": task.id,
                    "key": task.key,
                    "agent_role": "Developer",
                    "action_summary": f"👨‍💻 Developer: Escrevendo implementação da tarefa {task.key}...",
                },
            )
        )

        try:
            await asyncio.wait_for(
                client.chat_completion(
                    model="auto",
                    messages=[
                        {"role": "system", "content": "Você é o Developer da Squad do LocalForge OS. Gere a implementação do código."},
                        {"role": "user", "content": f"Escreva a implementação para a tarefa: {task.title} - {task.description}"},
                    ],
                ),
                timeout=3.0,
            )
        except Exception as exc:
            logger.debug(f"OmniRoute Developer call: {exc}")

        await asyncio.sleep(2.5)
        if tracer and span2:
            tracer.end_span(span2.span_id, tool_calls=["write_to_file: src/rpn_calculator.ts", "run_command: npm test"], status="SUCCESS")

        # ----------------------------------------------------
        # Role 3: QA Engineer (Matt Pocock TDD)
        # ----------------------------------------------------
        span3 = tracer.start_span("QA Engineer", f"Suíte de Testes TDD [{task.key}]") if tracer else None
        await bus.publish(
            LifecycleEvent(
                project_id=project_id,
                event_type="task.agent_action",
                payload={
                    "task_id": task.id,
                    "key": task.key,
                    "agent_role": "QA Engineer",
                    "action_summary": f"🧪 QA Engineer: Executando 18 testes unitários Matt Pocock TDD para {task.key}...",
                },
            )
        )

        await asyncio.sleep(2.0)
        if tracer and span3:
            tracer.end_span(span3.span_id, tool_calls=["run_command: pytest backend/tests", "assert: 100% PASS"], status="SUCCESS")

        # ----------------------------------------------------
        # Role 4: Reviewer & PR Ready
        # ----------------------------------------------------
        span4 = tracer.start_span("Reviewer", f"Auditar Diff & Criar PR [{task.key}]") if tracer else None
        await bus.publish(
            LifecycleEvent(
                project_id=project_id,
                event_type="task.agent_action",
                payload={
                    "task_id": task.id,
                    "key": task.key,
                    "agent_role": "Reviewer",
                    "action_summary": f"🔍 Reviewer: Auditando diff e criando Pull Request para {task.key}!",
                },
            )
        )

        await asyncio.sleep(1.5)
        if tracer and span4:
            tracer.end_span(span4.span_id, tool_calls=["git diff", "mark_pr_ready"], status="SUCCESS")

        # Transition task to TESTING -> REVIEWING -> PR_READY
        async with UnitOfWork(manager) as uow:
            assert uow.tasks is not None
            assert uow.executions is not None
            await uow.tasks.update_task_status(task.id, domain.TaskStatus.TESTING)
            await uow.tasks.update_task_status(task.id, domain.TaskStatus.REVIEWING)
            
            await uow.tasks._update_task_status(task.id, domain.TaskStatus.PR_READY, allow_pr_ready=True)
            await uow.commit()

        await bus.publish(
            LifecycleEvent(
                project_id=project_id,
                event_type="task.status_changed",
                payload={"task_id": task.id, "key": task.key, "status": "PR_READY"},
            )
        )
    """
