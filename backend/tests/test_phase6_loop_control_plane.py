import pytest
from datetime import UTC, datetime

from localforge.models import domain
from localforge.models.enums import (
    AutonomyLevel,
    ExecutionStrategy,
    LoopRunStatus,
    LoopRunVerdict,
    LoopStatus,
    TriggerKind,
)
from localforge.services.loop_coordinator import LoopCoordinator
from localforge.services.loop_service import LoopService
from localforge.storage import UnitOfWork


@pytest.mark.asyncio
async def test_loop_domain_and_persistence(db_manager) -> None:
    """Test V6-100 & V6-101: Loop domain models, ORM persistence, and export/import."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None

        proj = domain.Project(name="Loop Test Project", root_path="E:/tmp/loop_test", default_branch="main")
        project = await uow.projects.create_project(proj)

        trigger = domain.LoopTrigger(kind=TriggerKind.INTERVAL, schedule="10m")
        loop_def = domain.LoopDefinition(
            project_id=project.id,  # type: ignore[arg-type]
            name="Daily Triage Loop",
            repository_path="E:/tmp/loop_test",
            enabled=True,
            trigger=trigger,
            autonomy=AutonomyLevel.L1_INSPECT,
            max_budget_usd=10.0,
        )

        created = await uow.loops.create_loop(loop_def)
        assert created.id is not None
        assert created.name == "Daily Triage Loop"
        assert created.status == LoopStatus.IDLE
        assert created.trigger.kind == TriggerKind.INTERVAL

        # Fetch and verify
        fetched = await uow.loops.get_loop(created.id)
        assert fetched is not None
        assert fetched.max_budget_usd == 10.0

        # Export & Import
        exported_json = uow.loops.export_loop_definition(created)
        imported_def = uow.loops.import_loop_definition(exported_json, project_id=project.id)  # type: ignore[arg-type]
        assert imported_def.name == created.name
        assert imported_def.trigger.kind == TriggerKind.INTERVAL


@pytest.mark.asyncio
async def test_loop_coordinator_triage_noop(db_manager) -> None:
    """Test V6-102: Cheap triage returns NO_OP, creating no scheduler run."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None

        proj = domain.Project(name="Loop No-Op Test", root_path="E:/tmp/noop_test", default_branch="main")
        project = await uow.projects.create_project(proj)

        loop_def = domain.LoopDefinition(
            project_id=project.id,  # type: ignore[arg-type]
            name="No-Op Inspector",
            repository_path="E:/tmp/noop_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)

        # Trigger loop with force_noop payload
        run = await uow.loop_coordinator.trigger_loop(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            trigger_kind=TriggerKind.MANUAL,
            idempotency_key="noop_key_001",
            payload={"force_noop": True},
        )

        assert run.id is not None
        assert run.status == LoopRunStatus.NO_OP
        assert run.triage_verdict == LoopRunVerdict.NO_OP
        assert run.scheduler_run_id is None
        assert run.items_processed == 0


@pytest.mark.asyncio
async def test_loop_coordinator_triage_actionable(db_manager) -> None:
    """Test V6-102: Actionable triage creates a scheduler Run and items."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None

        proj = domain.Project(name="Loop Actionable Test", root_path="E:/tmp/act_test", default_branch="main")
        project = await uow.projects.create_project(proj)

        loop_def = domain.LoopDefinition(
            project_id=project.id,  # type: ignore[arg-type]
            name="Actionable Runner",
            repository_path="E:/tmp/act_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)

        # Trigger with actionable items
        payload = {
            "force_actionable": True,
            "items": [
                {"external_id": "issue_101", "title": "Fix memory leak"},
                {"external_id": "issue_102", "title": "Add test suite"},
            ],
        }

        run = await uow.loop_coordinator.trigger_loop(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            trigger_kind=TriggerKind.EVENT,
            idempotency_key="act_key_001",
            payload=payload,
        )

        assert run.status == LoopRunStatus.RUNNING
        assert run.triage_verdict == LoopRunVerdict.ACTIONABLE
        assert run.scheduler_run_id is not None
        assert run.items_processed == 2

        # Check items
        items = await uow.loops.list_items_for_run(run.id)  # type: ignore[arg-type]
        assert len(items) == 2
        assert items[0].external_id == "issue_101"
        assert items[1].title == "Add test suite"


@pytest.mark.asyncio
async def test_loop_coordinator_deduplication(db_manager) -> None:
    """Test V6-100 & V6-102: Duplicate trigger idempotency keys return existing run."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None

        proj = domain.Project(name="Loop Dedup Test", root_path="E:/tmp/dedup_test", default_branch="main")
        project = await uow.projects.create_project(proj)

        loop_def = domain.LoopDefinition(
            project_id=project.id,  # type: ignore[arg-type]
            name="Dedup Loop",
            repository_path="E:/tmp/dedup_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)

        key = "shared_event_key_123"

        run_1 = await uow.loop_coordinator.trigger_loop(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            trigger_kind=TriggerKind.EVENT,
            idempotency_key=key,
            payload={"force_noop": True},
        )

        # Trigger again with exact same idempotency key
        run_2 = await uow.loop_coordinator.trigger_loop(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            trigger_kind=TriggerKind.EVENT,
            idempotency_key=key,
            payload={"force_noop": True},
        )

        assert run_1.id == run_2.id
        assert run_2.idempotency_key == key


@pytest.mark.asyncio
async def test_loop_coordinator_pause_and_resume(db_manager) -> None:
    """Test V6-102 & V6-103: Pause and resume operations."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None

        proj = domain.Project(name="Loop Pause Test", root_path="E:/tmp/pause_test", default_branch="main")
        project = await uow.projects.create_project(proj)

        loop_def = domain.LoopDefinition(
            project_id=project.id,  # type: ignore[arg-type]
            name="Pausable Loop",
            repository_path="E:/tmp/pause_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)

        run = await uow.loop_coordinator.trigger_loop(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            trigger_kind=TriggerKind.MANUAL,
            idempotency_key="pause_key_001",
            payload={"force_actionable": True},
        )
        assert run.status == LoopRunStatus.RUNNING

        # Pause loop
        paused_def = await uow.loop_coordinator.pause_loop(created_loop.id)  # type: ignore[arg-type]
        assert paused_def.status == LoopStatus.PAUSED

        # Check run status updated to PAUSED
        updated_run = await uow.loops.get_loop_run(run.id)  # type: ignore[arg-type]
        assert updated_run is not None
        assert updated_run.status == LoopRunStatus.PAUSED

        # Resume loop
        resumed_def = await uow.loop_coordinator.resume_loop(created_loop.id)  # type: ignore[arg-type]
        assert resumed_def.status == LoopStatus.IDLE

        updated_run_2 = await uow.loops.get_loop_run(run.id)  # type: ignore[arg-type]
        assert updated_run_2 is not None
        assert updated_run_2.status == LoopRunStatus.RUNNING



@pytest.mark.asyncio
async def test_loop_coordinator_restart_recovery(db_manager) -> None:
    """Test V6-102: Process restart recovery scans and resumes triaging/running loops."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None

        proj = domain.Project(name="Loop Restart Test", root_path="E:/tmp/restart_test", default_branch="main")
        project = await uow.projects.create_project(proj)

        loop_def = domain.LoopDefinition(
            project_id=project.id,  # type: ignore[arg-type]
            name="Restart Recovery Loop",
            repository_path="E:/tmp/restart_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)

        # Manually insert a TRIAGING loop run as if interrupted during server crash
        interrupted_run = domain.LoopRun(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            status=LoopRunStatus.TRIAGING,
            trigger_kind=TriggerKind.CRON,
            idempotency_key="interrupted_key_999",
            triage_verdict=LoopRunVerdict.PENDING,
        )
        await uow.loops.create_loop_run(interrupted_run)

        # Recover
        recovered = await uow.loop_coordinator.recover_pending_loops(project.id)  # type: ignore[arg-type]
        assert len(recovered) == 1
        assert recovered[0].idempotency_key == "interrupted_key_999"
        assert recovered[0].status in (LoopRunStatus.NO_OP, LoopRunStatus.RUNNING)

