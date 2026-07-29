from datetime import UTC, datetime

import pytest
from localforge.models import domain
from localforge.models.enums import LoopStatus, TriggerKind
from localforge.services.loop_runtime import claim_schedule_metadata, next_run_at, validate_schedule
from localforge.storage import UnitOfWork
from localforge.storage.orm import LoopDefinitionORM
from sqlalchemy import select


@pytest.mark.asyncio
async def test_interval_schedule_initializes_and_claims_once(db_manager) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        project = await uow.projects.create_project(
            domain.Project(name="R4 Interval", root_path="/tmp/r4", default_branch="main")
        )
        loop = await uow.loops.create_loop(
            domain.LoopDefinition(
                project_id=project.id,  # type: ignore[arg-type]
                name="interval",
                repository_path="/tmp/r4",
                trigger=domain.LoopTrigger(
                    kind=TriggerKind.INTERVAL,
                    schedule="10m",
                    metadata={"next_run_at": "2026-07-29T12:00:00Z"},
                ),
            )
        )

        first = await uow.loops.claim_due_schedules(project.id, now=now)  # type: ignore[arg-type]
        second = await uow.loops.claim_due_schedules(project.id, now=now)  # type: ignore[arg-type]

        assert len(first) == 1
        claimed_loop, key = first[0]
        assert claimed_loop.id == loop.id
        assert key == "interval:2026-07-29T12:00:00Z:rev:0"
        assert claimed_loop.trigger.metadata["last_trigger_at"] == "2026-07-29T12:00:00Z"
        assert claimed_loop.trigger.metadata["next_run_at"] == "2026-07-29T12:10:00Z"
        assert claimed_loop.trigger.metadata["trigger_revision"] == 1
        assert second == []


@pytest.mark.asyncio
async def test_two_coordinators_cannot_claim_same_due_schedule(db_manager) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    async with UnitOfWork(db_manager) as seed:
        assert seed.projects is not None
        assert seed.loops is not None
        project = await seed.projects.create_project(
            domain.Project(name="R4 Atomic", root_path="/tmp/r4", default_branch="main")
        )
        loop = await seed.loops.create_loop(
            domain.LoopDefinition(
                project_id=project.id,  # type: ignore[arg-type]
                name="atomic-interval",
                repository_path="/tmp/r4",
                trigger=domain.LoopTrigger(
                    kind=TriggerKind.INTERVAL,
                    schedule="10m",
                    metadata={"next_run_at": "2026-07-29T12:00:00Z"},
                ),
            )
        )

    async with UnitOfWork(db_manager) as stale_uow:
        assert stale_uow.session is not None
        assert stale_uow.loops is not None
        result = await stale_uow.session.execute(
            select(LoopDefinitionORM).where(LoopDefinitionORM.id == loop.id)
        )
        stale_orm = result.scalar_one()
        stale_loop = stale_orm.to_domain()
        stale_trigger, stale_key = claim_schedule_metadata(stale_loop.trigger, now=now)
        assert stale_trigger is not None
        assert stale_key == "interval:2026-07-29T12:00:00Z:rev:0"

        async with UnitOfWork(db_manager) as winning_uow:
            assert winning_uow.loops is not None
            first = await winning_uow.loops.claim_due_schedules(project.id, now=now)  # type: ignore[arg-type]
            assert len(first) == 1

        stale_claim = await stale_uow.loops._compare_and_swap_schedule_claim(
            stale_orm,
            trigger_json=stale_trigger.model_dump(mode="json"),
        )
        assert stale_claim is None

    async with UnitOfWork(db_manager) as verify:
        assert verify.loops is not None
        duplicate = await verify.loops.claim_due_schedules(project.id, now=now)  # type: ignore[arg-type]
        refreshed = await verify.loops.get_loop(loop.id or 0)
        assert duplicate == []
        assert refreshed is not None
        assert refreshed.trigger.metadata["trigger_revision"] == 1


@pytest.mark.asyncio
async def test_cron_schedule_uses_timezone_and_skip_misfire_policy(db_manager) -> None:
    now = datetime(2026, 7, 29, 15, 5, tzinfo=UTC)
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        project = await uow.projects.create_project(
            domain.Project(name="R4 Cron", root_path="/tmp/r4", default_branch="main")
        )
        await uow.loops.create_loop(
            domain.LoopDefinition(
                project_id=project.id,  # type: ignore[arg-type]
                name="cron",
                repository_path="/tmp/r4",
                trigger=domain.LoopTrigger(
                    kind=TriggerKind.CRON,
                    schedule="0 9 * * *",
                    metadata={
                        "timezone": "America/Sao_Paulo",
                        "misfire_policy": "skip",
                        "next_run_at": "2026-07-29T12:00:00Z",
                    },
                ),
            )
        )

        claimed = await uow.loops.claim_due_schedules(project.id, now=now)  # type: ignore[arg-type]

        assert len(claimed) == 1
        claimed_loop, key = claimed[0]
        assert key == "cron:2026-07-29T12:00:00Z:rev:0"
        assert claimed_loop.trigger.metadata["timezone"] == "America/Sao_Paulo"
        assert claimed_loop.trigger.metadata["next_run_at"] == "2026-07-30T12:00:00Z"


def test_schedule_validation_rejects_bad_interval_and_cron() -> None:
    with pytest.raises(ValueError, match="Interval"):
        validate_schedule(domain.LoopTrigger(kind=TriggerKind.INTERVAL, schedule="ten minutes"))
    with pytest.raises(ValueError, match="five fields"):
        validate_schedule(domain.LoopTrigger(kind=TriggerKind.CRON, schedule="* * *"))
    assert next_run_at(
        domain.LoopTrigger(kind=TriggerKind.INTERVAL, schedule="30s"),
        now=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    ) == datetime(2026, 7, 29, 12, 0, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_paused_loop_cannot_be_claimed(db_manager) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        project = await uow.projects.create_project(
            domain.Project(name="R4 Pause", root_path="/tmp/r4", default_branch="main")
        )
        loop = await uow.loops.create_loop(
            domain.LoopDefinition(
                project_id=project.id,  # type: ignore[arg-type]
                name="paused",
                repository_path="/tmp/r4",
                status=LoopStatus.PAUSED,
                trigger=domain.LoopTrigger(
                    kind=TriggerKind.INTERVAL,
                    schedule="1m",
                    metadata={"next_run_at": "2026-07-29T12:00:00Z"},
                ),
            )
        )

        claimed = await uow.loops.claim_due_schedules(project.id, now=now)  # type: ignore[arg-type]

        assert loop.status == LoopStatus.PAUSED
        assert claimed == []


@pytest.mark.asyncio
async def test_due_schedule_claim_executes_loop_run_once(db_manager) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None
        project = await uow.projects.create_project(
            domain.Project(name="R4 Execute", root_path="/tmp/r4", default_branch="main")
        )
        await uow.loops.create_loop(
            domain.LoopDefinition(
                project_id=project.id,  # type: ignore[arg-type]
                name="scheduled-noop",
                repository_path="/tmp/r4",
                trigger=domain.LoopTrigger(
                    kind=TriggerKind.INTERVAL,
                    schedule="1m",
                    metadata={
                        "next_run_at": "2026-07-29T12:00:00Z",
                        "default_payload": {"force_noop": True},
                    },
                ),
            )
        )

        first = await uow.loop_coordinator.trigger_due_schedules(project.id, now=now)  # type: ignore[arg-type]
        second = await uow.loop_coordinator.trigger_due_schedules(project.id, now=now)  # type: ignore[arg-type]

        assert len(first) == 1
        assert first[0].idempotency_key == "interval:2026-07-29T12:00:00Z:rev:0"
        assert second == []
        runs = await uow.loops.list_runs_for_loop(first[0].loop_id)
        assert len(runs) == 1
