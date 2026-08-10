"""FastAPI adapters for durable engineering continuity and execution profiles."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import (
    EngineeringGoalCreateRequest,
    EngineeringGoalRevisionRequest,
    EngineeringSessionCreateRequest,
    EngineeringSessionTransitionRequest,
    EngineeringSteerRequest,
    EngineeringTurnAdmissionRequest,
    ExecutionProfileActionRequest,
    ExecutionProfileRequest,
)
from localforge.services.engineering import (
    EngineeringContinuityService,
    EngineeringError,
    EngineeringImmutableTurn,
    EngineeringInvalidTransition,
    EngineeringLimitExceeded,
    EngineeringNotFound,
)
from localforge.storage import DatabaseManager, UnitOfWork

T = TypeVar("T")


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, EngineeringNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, EngineeringInvalidTransition):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, EngineeringImmutableTurn):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, EngineeringLimitExceeded):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, EngineeringError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def create_engineering_router(manager: DatabaseManager) -> APIRouter:
    router = APIRouter(tags=["engineering"])

    async def call(
        operation: Callable[[EngineeringContinuityService], Awaitable[T]],
    ) -> T:
        try:
            async with UnitOfWork(manager) as uow:
                assert uow.engineering is not None
                return await operation(uow.engineering)
        except Exception as exc:
            _raise_http(exc)
            raise AssertionError("unreachable") from exc

    @router.post(
        "/projects/{project_id}/engineering/sessions",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        project_id: int, req: EngineeringSessionCreateRequest
    ) -> dict[str, Any]:
        session = await call(
            lambda service: service.create_session(
                project_id=project_id,
                title=req.title,
                default_model=req.default_model,
                max_turns=req.max_turns,
                max_wall_seconds=req.max_wall_seconds,
                max_retries=req.max_retries,
                quality_gate_names=req.quality_gate_names,
                metadata=req.metadata,
            )
        )
        return _dump(session)

    @router.get("/projects/{project_id}/engineering/sessions")
    async def list_sessions(project_id: int) -> list[dict[str, Any]]:
        sessions = await call(lambda service: service.list_sessions(project_id))
        return [_dump(item) for item in sessions]

    @router.get("/engineering/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        session = await call(lambda service: service.get_session(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail="Engineering session not found")
        return _dump(session)

    @router.get("/projects/{project_id}/engineering/sessions/{session_id}")
    async def get_project_session(project_id: int, session_id: str) -> dict[str, Any]:
        session = await call(lambda service: service.get_session(session_id))
        if session is None or session.project_id != project_id:
            raise HTTPException(status_code=404, detail="Engineering session not found")
        return _dump(session)

    @router.post("/engineering/sessions/{session_id}/close")
    async def close_session(
        session_id: str, req: EngineeringSessionTransitionRequest | None = None
    ) -> dict[str, Any]:
        payload = req or EngineeringSessionTransitionRequest(status="COMPLETED")
        try:
            session = await call(
                lambda service: service.close_session(
                    session_id, result=payload.result, reason=payload.reason or "closed"
                )
            )
        except HTTPException:
            raise
        return _dump(session)

    @router.post("/engineering/sessions/{session_id}/state")
    async def transition_session(
        session_id: str, req: EngineeringSessionTransitionRequest
    ) -> dict[str, Any]:
        session = await call(
            lambda service: service.transition_session(
                session_id, req.status, reason=req.reason, result=req.result
            )
        )
        return _dump(session)

    @router.post("/engineering/sessions/{session_id}/pause")
    async def pause_session(session_id: str, reason: str = "user_pause") -> dict[str, Any]:
        return _dump(await call(lambda service: service.pause_session(session_id, reason=reason)))

    @router.post("/engineering/sessions/{session_id}/resume")
    async def resume_session(session_id: str, reason: str = "user_resume") -> dict[str, Any]:
        return _dump(await call(lambda service: service.resume_session(session_id, reason=reason)))

    @router.post("/engineering/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str, reason: str = "user_cancel") -> dict[str, Any]:
        return _dump(await call(lambda service: service.cancel_session(session_id, reason=reason)))

    @router.post("/engineering/sessions/{session_id}/steer", status_code=status.HTTP_201_CREATED)
    async def steer_session(
        session_id: str, req: EngineeringSteerRequest
    ) -> dict[str, Any]:
        turn = await call(
            lambda service: service.steer(
                session_id, req.instruction, idempotency_key=req.idempotency_key
            )
        )
        return _dump(turn)

    @router.post(
        "/engineering/sessions/{session_id}/goals",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_goal(
        session_id: str, req: EngineeringGoalCreateRequest
    ) -> dict[str, Any]:
        goal = await call(
            lambda service: service.create_goal(
                session_id=session_id,
                objective=req.objective,
                acceptance_criteria=req.acceptance_criteria,
                metadata=req.metadata,
            )
        )
        return _dump(goal)

    @router.get("/engineering/goals/{goal_id}")
    async def get_goal(goal_id: str) -> dict[str, Any]:
        goal = await call(lambda service: service.get_goal(goal_id))
        if goal is None:
            raise HTTPException(status_code=404, detail="Engineering goal not found")
        return _dump(goal)

    @router.post("/engineering/goals/{goal_id}/revise")
    async def revise_goal(
        goal_id: str, req: EngineeringGoalRevisionRequest
    ) -> dict[str, Any]:
        goal = await call(
            lambda service: service.revise_goal(
                goal_id,
                req.objective,
                req.acceptance_criteria,
                expected_revision=req.expected_revision,
                metadata=req.metadata,
                reason=req.reason,
            )
        )
        return _dump(goal)

    @router.get("/engineering/sessions/{session_id}/goal")
    async def current_goal(session_id: str) -> dict[str, Any] | None:
        goal = await call(lambda service: service.get_current_goal(session_id))
        return _dump(goal) if goal else None

    @router.post(
        "/engineering/sessions/{session_id}/turns",
        status_code=status.HTTP_201_CREATED,
    )
    async def admit_turn(
        session_id: str, req: EngineeringTurnAdmissionRequest
    ) -> dict[str, Any]:
        turn = await call(
            lambda service: service.admit_turn(
                session_id=session_id,
                input_text=req.input_text,
                kind=req.kind,
                idempotency_key=req.idempotency_key,
                model=req.model,
                result=req.result,
                retry_count=req.retry_count,
                metadata=req.metadata,
            )
        )
        return _dump(turn)

    @router.get("/engineering/sessions/{session_id}/turns")
    async def list_turns(session_id: str) -> list[dict[str, Any]]:
        turns = await call(lambda service: service.list_turns(session_id))
        return [_dump(item) for item in turns]

    @router.get("/engineering/sessions/{session_id}/timeline")
    async def timeline(session_id: str) -> list[dict[str, Any]]:
        turns = await call(lambda service: service.timeline(session_id))
        return [_dump(item) for item in turns]

    @router.get("/engineering/turns/{turn_id}")
    async def get_turn(turn_id: str) -> dict[str, Any]:
        turn = await call(lambda service: service.get_turn(turn_id))
        if turn is None:
            raise HTTPException(status_code=404, detail="Engineering turn not found")
        return _dump(turn)

    @router.get("/projects/{project_id}/engineering/profiles")
    async def list_profiles(project_id: int) -> list[dict[str, Any]]:
        profiles = await call(lambda service: service.list_profiles(project_id))
        return [_dump(item) for item in profiles]

    @router.put("/projects/{project_id}/engineering/profiles")
    @router.post("/projects/{project_id}/engineering/profiles")
    async def upsert_profile(
        project_id: int, req: ExecutionProfileRequest
    ) -> dict[str, Any]:
        profile = await call(
            lambda service: service.create_or_update_profile(
                project_id=project_id,
                session_id=req.session_id,
                name=req.name,
                trust=req.trust,
                mode=req.mode,
                tool_policies=req.tool_policies,
                metadata=req.metadata,
            )
        )
        return _dump(profile)

    @router.get("/engineering/sessions/{session_id}/profile")
    async def resolve_session_profile(session_id: str) -> dict[str, Any]:
        session = await call(lambda service: service.get_session(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail="Engineering session not found")
        profile = await call(
            lambda service: service.resolve_profile(session.project_id, session_id=session_id)
        )
        return _dump(profile)

    @router.post("/projects/{project_id}/engineering/profile/evaluate")
    async def evaluate_profile_action(
        project_id: int, req: ExecutionProfileActionRequest
    ) -> dict[str, Any]:
        evaluation = await call(
            lambda service: service.evaluate_action(
                project_id=project_id,
                action_kind=req.action_kind,
                payload=req.payload,
                purpose=req.purpose,
                risk_level=req.risk_level,
                session_id=req.session_id,
                turn_id=req.turn_id,
                idempotency_key=req.idempotency_key,
            )
        )
        return _dump(evaluation)

    return router
