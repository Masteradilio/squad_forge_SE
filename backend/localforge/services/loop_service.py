import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import LoopRunStatus, LoopRunVerdict, LoopStatus
from localforge.storage.orm import (
    LoopDefinitionORM,
    LoopItemORM,
    LoopRunORM,
    LoopStateSnapshotORM,
)

logger = logging.getLogger(__name__)


class LoopService:
    """Service layer for Loop definitions, runs, items, and state snapshots."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_loop(self, loop_def: domain.LoopDefinition) -> domain.LoopDefinition:
        """Create and persist a new loop definition."""
        orm_obj = LoopDefinitionORM.from_domain(loop_def)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_loop(self, loop_id: int) -> domain.LoopDefinition | None:
        """Retrieve a loop definition by ID."""
        stmt = select(LoopDefinitionORM).where(LoopDefinitionORM.id == loop_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_loops_for_project(self, project_id: int) -> list[domain.LoopDefinition]:
        """List all loop definitions for a given project."""
        stmt = (
            select(LoopDefinitionORM)
            .where(LoopDefinitionORM.project_id == project_id)
            .order_by(LoopDefinitionORM.id.asc())
        )
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_loop_status(
        self, loop_id: int, status: LoopStatus, enabled: bool | None = None
    ) -> domain.LoopDefinition | None:
        """Update status or enabled state of a loop."""
        stmt = select(LoopDefinitionORM).where(LoopDefinitionORM.id == loop_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            return None

        orm_obj.status = status.value if isinstance(status, LoopStatus) else str(status)
        if enabled is not None:
            orm_obj.enabled = enabled
        orm_obj.updated_at = datetime.now(UTC)
        await self.session.flush()
        return orm_obj.to_domain()

    async def create_loop_run(self, loop_run: domain.LoopRun) -> domain.LoopRun:
        """Persist a new LoopRun."""
        orm_obj = LoopRunORM.from_domain(loop_run)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_loop_run_by_idempotency_key(self, idempotency_key: str) -> domain.LoopRun | None:
        """Retrieve a LoopRun by its idempotency key."""
        stmt = select(LoopRunORM).where(LoopRunORM.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_loop_run(self, loop_run_id: int) -> domain.LoopRun | None:
        """Retrieve a LoopRun by ID."""
        stmt = select(LoopRunORM).where(LoopRunORM.id == loop_run_id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def update_loop_run(self, loop_run: domain.LoopRun) -> domain.LoopRun:
        """Update an existing LoopRun."""
        stmt = select(LoopRunORM).where(LoopRunORM.id == loop_run.id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"LoopRun with id {loop_run.id} not found")

        orm_obj.status = (
            loop_run.status.value
            if isinstance(loop_run.status, LoopRunStatus)
            else str(loop_run.status)
        )
        orm_obj.triage_verdict = (
            loop_run.triage_verdict.value
            if isinstance(loop_run.triage_verdict, LoopRunVerdict)
            else str(loop_run.triage_verdict)
        )

        orm_obj.scheduler_run_id = loop_run.scheduler_run_id
        orm_obj.items_processed = loop_run.items_processed
        orm_obj.cost_usd = loop_run.cost_usd
        orm_obj.completed_at = loop_run.completed_at
        orm_obj.error_message = loop_run.error_message
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_runs_for_loop(self, loop_id: int, limit: int = 50) -> list[domain.LoopRun]:
        """List recent execution runs for a loop."""
        stmt = (
            select(LoopRunORM)
            .where(LoopRunORM.loop_id == loop_id)
            .order_by(LoopRunORM.started_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def create_loop_item(self, item: domain.LoopItem) -> domain.LoopItem:
        """Create and persist a LoopItem."""
        orm_obj = LoopItemORM.from_domain(item)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_loop_item_by_idempotency_key(
        self, idempotency_key: str
    ) -> domain.LoopItem | None:
        """Retrieve a LoopItem by its idempotency key."""
        stmt = select(LoopItemORM).where(LoopItemORM.idempotency_key == idempotency_key)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_items_for_run(self, loop_run_id: int) -> list[domain.LoopItem]:
        """List all items associated with a loop run."""
        stmt = (
            select(LoopItemORM)
            .where(LoopItemORM.loop_run_id == loop_run_id)
            .order_by(LoopItemORM.id.asc())
        )
        result = await self.session.execute(stmt)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_loop_item(self, item: domain.LoopItem) -> domain.LoopItem:
        """Update LoopItem execution linkage and status."""
        if item.id is None:
            raise ValueError("Cannot update LoopItem without an ID")
        stmt = select(LoopItemORM).where(LoopItemORM.id == item.id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if orm_obj is None:
            raise ValueError(f"LoopItem with id {item.id} not found")
        orm_obj.title = item.title
        orm_obj.payload_json = item.payload
        orm_obj.status = item.status
        orm_obj.scheduler_task_id = item.scheduler_task_id
        await self.session.flush()
        return orm_obj.to_domain()

    async def create_or_update_snapshot(
        self, snapshot: domain.LoopStateSnapshot
    ) -> domain.LoopStateSnapshot:
        """Save a new state snapshot for a loop."""
        orm_obj = LoopStateSnapshotORM.from_domain(snapshot)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_latest_snapshot(self, loop_id: int) -> domain.LoopStateSnapshot | None:
        """Get the latest state snapshot for a loop."""
        stmt = (
            select(LoopStateSnapshotORM)
            .where(LoopStateSnapshotORM.loop_id == loop_id)
            .order_by(LoopStateSnapshotORM.snapshot_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    def export_loop_definition(self, loop_def: domain.LoopDefinition) -> str:
        """Export loop definition to human-readable JSON string."""
        return json.dumps(loop_def.model_dump(mode="json"), indent=2)

    def import_loop_definition(self, json_data: str, project_id: int) -> domain.LoopDefinition:
        """Import loop definition from JSON string."""
        raw = json.loads(json_data)
        raw["project_id"] = project_id
        return domain.LoopDefinition.model_validate(raw)
