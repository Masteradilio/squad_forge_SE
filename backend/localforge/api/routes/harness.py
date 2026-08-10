"""Project-scoped API for durable Harness state and bounded child agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status

from localforge.api.schemas import (
    HarnessContinuationCheckRequest,
    HarnessEntryRequest,
    HarnessRefineRequest,
    HarnessSubagentRequest,
    HarnessSubagentTransitionRequest,
)
from localforge.runtime.harness_state import HarnessEntry, HarnessState
from localforge.runtime.run_control import RunContinuationPolicy
from localforge.runtime.subagents import (
    HarnessStateSubagentStore,
    SubagentRegistry,
    SubagentRegistryError,
    SubagentSpec,
)
from localforge.storage import UnitOfWork, db_manager

router = APIRouter(tags=["harness"])


async def _project_root(project_id: int) -> Path:
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        project = await uow.projects.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return Path(project.root_path).resolve()


def _registry(root: Path) -> SubagentRegistry:
    return SubagentRegistry(HarnessStateSubagentStore(HarnessState(root)))


@router.get("/projects/{project_id}/harness/state")
async def list_harness_state(
    project_id: int,
    kind: str | None = None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    root = await _project_root(project_id)
    state = HarnessState(root)
    try:
        entries = state.list(kind=kind, scope=scope)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [entry.model_dump(mode="json") for entry in entries]


@router.post("/projects/{project_id}/harness/state", status_code=status.HTTP_201_CREATED)
async def upsert_harness_state(project_id: int, req: HarnessEntryRequest) -> dict[str, Any]:
    root = await _project_root(project_id)
    try:
        entry = HarnessState(root).upsert(HarnessEntry.model_validate(req.model_dump()))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return entry.model_dump(mode="json")


@router.post("/projects/{project_id}/harness/state/{entry_id}/refine")
async def refine_harness_state(
    project_id: int,
    entry_id: str,
    req: HarnessRefineRequest,
) -> dict[str, Any]:
    root = await _project_root(project_id)
    try:
        event = HarnessState(root).refine(entry_id, req.evidence, req.updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return event.model_dump(mode="json")


@router.get("/projects/{project_id}/harness/refinements")
async def list_harness_refinements(project_id: int) -> list[dict[str, Any]]:
    root = await _project_root(project_id)
    return [event.model_dump(mode="json") for event in HarnessState(root).list_refinements()]


@router.get("/projects/{project_id}/harness/subagents")
async def list_harness_subagents(project_id: int) -> list[dict[str, Any]]:
    root = await _project_root(project_id)
    return [record.model_dump(mode="json") for record in _registry(root).list()]


@router.post("/projects/{project_id}/harness/subagents", status_code=status.HTTP_201_CREATED)
async def register_harness_subagent(
    project_id: int,
    req: HarnessSubagentRequest,
) -> dict[str, Any]:
    root = await _project_root(project_id)
    payload = req.model_dump(exclude_none=True)
    spec = SubagentSpec.model_validate(payload)
    registry = _registry(root)
    try:
        record = (
            registry.register_child(spec.parent_id, spec)
            if spec.parent_id is not None
            else registry.register(spec)
        )
    except (KeyError, SubagentRegistryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.post("/projects/{project_id}/harness/subagents/{subagent_id}/transition")
async def transition_harness_subagent(
    project_id: int,
    subagent_id: str,
    req: HarnessSubagentTransitionRequest,
) -> dict[str, Any]:
    root = await _project_root(project_id)
    try:
        record = _registry(root).transition(
            subagent_id,
            req.status,
            result=req.result,
            evidence=req.evidence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SubagentRegistryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@router.post("/projects/{project_id}/harness/continuation/check")
async def check_harness_continuation(
    project_id: int,
    req: HarnessContinuationCheckRequest,
) -> dict[str, Any]:
    root = await _project_root(project_id)
    pause_file = Path(req.pause_file) if req.pause_file else root / ".localforge" / "harness" / "pause"
    policy = RunContinuationPolicy(
        max_turns=req.max_turns,
        max_wall_seconds=req.max_wall_seconds,
        max_retries=req.max_retries,
        pause_file=pause_file,
        quality_gate_names=req.quality_gate_names,
    )
    return {
        "should_continue": policy.should_continue(
            req.turns,
            req.elapsed_seconds,
            req.retries,
            quality_gates=req.quality_gates,
        ),
        "paused": policy.check_pause(),
        "pause_file": str(pause_file),
        "quality_gate_names": policy.quality_gate_names,
    }

