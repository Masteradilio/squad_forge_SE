from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import AgentRole, HandoffStatus
from localforge.storage.orm import AgentORM, HandoffORM, RunORM


class ExecutionService:
    """Service layer managing execution Runs, local Agents, and Handoff protocol."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # Run Operations
    async def create_run(self, run: domain.Run) -> domain.Run:
        """Create a new run session."""
        orm_obj = RunORM.from_domain(run)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_run(self, run_id: int) -> domain.Run | None:
        """Retrieve a run session by ID."""
        result = await self.session.execute(select(RunORM).where(RunORM.id == run_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def update_run(self, run: domain.Run) -> domain.Run:
        """Update a run's status or summary."""
        if not run.id:
            raise ValueError("Cannot update a run without an ID")

        result = await self.session.execute(select(RunORM).where(RunORM.id == run.id))
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Run with ID {run.id} not found")

        orm_obj.status = run.status.value
        orm_obj.ended_at = run.ended_at
        orm_obj.summary = run.summary
        orm_obj.resource_limits = run.resource_limits

        await self.session.flush()
        return orm_obj.to_domain()

    async def list_runs_for_project(self, project_id: int) -> list[domain.Run]:
        """List all runs for a project."""
        result = await self.session.execute(
            select(RunORM).where(RunORM.project_id == project_id).order_by(RunORM.started_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    # Agent Operations
    async def register_agent(self, agent: domain.Agent) -> domain.Agent:
        """Register a new local agent."""
        orm_obj = AgentORM.from_domain(agent)
        orm_obj.heartbeat_at = datetime.now(UTC)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_agent(self, agent_id: int) -> domain.Agent | None:
        """Retrieve agent by ID."""
        result = await self.session.execute(select(AgentORM).where(AgentORM.id == agent_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def record_heartbeat(self, agent_id: int) -> domain.Agent | None:
        """Record a heartbeat timestamp for an agent."""
        result = await self.session.execute(select(AgentORM).where(AgentORM.id == agent_id))
        orm_obj = result.scalar_one_or_none()
        if orm_obj:
            orm_obj.heartbeat_at = datetime.now(UTC)
            await self.session.flush()
            return orm_obj.to_domain()
        return None

    async def list_active_agents(self) -> list[domain.Agent]:
        """List active agents."""
        result = await self.session.execute(
            select(AgentORM).where(AgentORM.active).order_by(AgentORM.id)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_agent(self, agent: domain.Agent) -> domain.Agent:
        """Update agent fields."""
        if not agent.id:
            raise ValueError("Cannot update an agent without an ID")

        result = await self.session.execute(select(AgentORM).where(AgentORM.id == agent.id))
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Agent with ID {agent.id} not found")

        orm_obj.name = agent.name
        orm_obj.role = agent.role.value
        orm_obj.model_profile_id = agent.model_profile_id
        orm_obj.active = agent.active
        orm_obj.max_concurrent_tasks = agent.max_concurrent_tasks
        orm_obj.permissions_profile_id = agent.permissions_profile_id
        orm_obj.current_task_id = agent.current_task_id

        await self.session.flush()
        return orm_obj.to_domain()

    # Handoff Operations
    async def create_handoff(self, handoff: domain.Handoff) -> domain.Handoff:
        """Create a new role handoff."""
        orm_obj = HandoffORM.from_domain(handoff)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_handoff(self, handoff_id: int) -> domain.Handoff | None:
        """Retrieve a handoff by ID."""
        result = await self.session.execute(select(HandoffORM).where(HandoffORM.id == handoff_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def consume_handoff(self, handoff_id: int) -> domain.Handoff:
        """Mark a handoff as consumed by the scheduler."""
        result = await self.session.execute(select(HandoffORM).where(HandoffORM.id == handoff_id))
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Handoff with ID {handoff_id} not found")

        orm_obj.status = HandoffStatus.CONSUMED.value
        orm_obj.consumed_at = datetime.now(UTC)
        await self.session.flush()
        return orm_obj.to_domain()

    async def list_pending_handoffs(self, to_role: AgentRole | None = None) -> list[domain.Handoff]:
        """List all pending handoffs, optionally filtered by the recipient role."""
        query = select(HandoffORM).where(HandoffORM.status == HandoffStatus.PENDING.value)
        if to_role:
            query = query.where(HandoffORM.to_role == to_role.value)
        query = query.order_by(HandoffORM.priority.desc(), HandoffORM.created_at)

        result = await self.session.execute(query)
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]
