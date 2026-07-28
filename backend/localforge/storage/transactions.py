from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from localforge.services.audit import AuditService
from localforge.services.coordination import CoordinationService
from localforge.services.execution import ExecutionService
from localforge.services.memory import MemoryService
from localforge.services.model_calls import ModelCallLedgerService
from localforge.services.project import ProjectService
from localforge.services.routing import ModelRoutingService
from localforge.services.safety import SafetyService
from localforge.services.task import TaskService
from localforge.services.cost_benchmark import CostBenchmarkService
from localforge.services.simulation import APISimulationService
from localforge.services.loop_service import LoopService
from localforge.services.loop_coordinator import LoopCoordinator
from localforge.services.circuit_breaker import CircuitBreakerService
from localforge.services.autonomy import AutonomyService
from localforge.services.maker_checker import MakerCheckerService
from localforge.services.worktree import WorktreeService
from localforge.services.path_lease import PathLeaseService
from localforge.services.runner_pool import RunnerPoolService
from localforge.storage.database import DatabaseManager, db_manager


class UnitOfWork:
    """Context manager for managing transactions and grouping service layers.

    Guarantees ACID atomic execution across all services.
    """

    def __init__(self, manager: DatabaseManager | None = None):
        self.db_manager = manager or db_manager
        self.session: AsyncSession | None = None

        # Bind placeholders for atomic services
        self.projects: ProjectService | None = None
        self.tasks: TaskService | None = None
        self.executions: ExecutionService | None = None
        self.audits: AuditService | None = None
        self.safety: SafetyService | None = None
        self.routing: ModelRoutingService | None = None
        self.memory: MemoryService | None = None
        self.model_calls: ModelCallLedgerService | None = None
        self.coordination: CoordinationService | None = None
        self.cost_benchmark: CostBenchmarkService | None = None
        self.simulation: APISimulationService | None = None
        self.loops: LoopService | None = None
        self.loop_coordinator: LoopCoordinator | None = None
        self.circuit_breakers: CircuitBreakerService | None = None
        self.autonomy: AutonomyService | None = None
        self.maker_checker: MakerCheckerService | None = None
        self.worktrees: WorktreeService | None = None
        self.path_leases: PathLeaseService | None = None
        self.runner_pool: RunnerPoolService | None = None

    async def __aenter__(self) -> Self:
        self.session = await self.db_manager.get_session()
        self.projects = ProjectService(self.session)
        self.tasks = TaskService(self.session)
        self.executions = ExecutionService(self.session)
        self.audits = AuditService(self.session)
        self.safety = SafetyService(self.session)
        self.routing = ModelRoutingService(self.session)
        self.memory = MemoryService(self.session)
        self.model_calls = ModelCallLedgerService(self.session)
        self.coordination = CoordinationService(self.session)
        self.cost_benchmark = CostBenchmarkService(self.session)
        self.simulation = APISimulationService(self.session)
        self.loops = LoopService(self.session)
        self.loop_coordinator = LoopCoordinator(self.session)
        self.circuit_breakers = CircuitBreakerService(self.session)
        self.autonomy = AutonomyService()
        self.maker_checker = MakerCheckerService(self.session)
        self.worktrees = WorktreeService(self.session)
        self.path_leases = PathLeaseService(self.session)
        self.runner_pool = RunnerPoolService(self.session)
        return self






    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.session:
            try:
                if exc_type is not None:
                    # Rollback changes if an exception occurs
                    await self.session.rollback()
                    # Persist buffered calls in a clean independent transaction post-rollback
                    await self._persist_pending_model_calls()
                else:
                    # Commit changes on success
                    await self.session.commit()
            finally:
                from localforge.services.model_calls import ModelCallLedgerService
                ModelCallLedgerService._pending_calls.clear()
                await self.session.close()

    async def _persist_pending_model_calls(self) -> None:
        from localforge.services.model_calls import ModelCallLedgerService
        if not ModelCallLedgerService._pending_calls:
            return
        try:
            from localforge.storage.orm import ModelCallLedgerORM
            async with self.db_manager.session_factory() as session:
                for call in ModelCallLedgerService._pending_calls:
                    orm_obj = ModelCallLedgerORM.from_domain(call)
                    session.add(orm_obj)
                await session.commit()
        except Exception as e:
            import logging
            logging.getLogger("localforge").error(f"Failed to persist pending model calls post-rollback: {e}")

