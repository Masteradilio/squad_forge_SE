from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from localforge.services.audit import AuditService
from localforge.services.autonomy import AutonomyService
from localforge.services.circuit_breaker import CircuitBreakerService
from localforge.services.coordination import CoordinationService
from localforge.services.cost_benchmark import CostBenchmarkService
from localforge.services.deepcode_capabilities import (
    AutomationService,
    ModelCatalogService,
    SkillBindingService,
)
from localforge.services.engineering import EngineeringContinuityService
from localforge.services.execution import ExecutionService
from localforge.services.light_swarm import LightSwarmService
from localforge.services.loop_coordinator import LoopCoordinator
from localforge.services.loop_service import LoopService
from localforge.services.maker_checker import MakerCheckerService
from localforge.services.memory import MemoryService
from localforge.services.model_calls import ModelCallLedgerService
from localforge.services.path_lease import PathLeaseService
from localforge.services.project import ProjectService
from localforge.services.reference_continuity import ReferenceContinuityService
from localforge.services.routing import ModelRoutingService
from localforge.services.runner_pool import RunnerPoolService
from localforge.services.safety import SafetyService
from localforge.services.simulation import APISimulationService
from localforge.services.task import TaskService
from localforge.services.task_graph import TaskGraphService
from localforge.services.tenant_context import current_context
from localforge.services.typed_handoff import TypedHandoffService
from localforge.services.worktree import WorktreeService
from localforge.storage.database import DatabaseManager, db_manager


class UnitOfWork:
    """Context manager for managing transactions and grouping service layers.

    Guarantees ACID atomic execution across all services.
    """

    def __init__(self, manager: DatabaseManager | None = None, *, read_only: bool = False):
        self.db_manager = manager or db_manager
        self.session: AsyncSession | None = None
        self.read_only = read_only

        # Bind placeholders for atomic services
        self.projects: ProjectService | None = None
        self.tasks: TaskService | None = None
        self.executions: ExecutionService | None = None
        self.engineering: EngineeringContinuityService | None = None
        # Alias used by callers that name this bounded runtime "continuity".
        self.continuity: EngineeringContinuityService | None = None
        self.model_catalog: ModelCatalogService | None = None
        self.skill_bindings: SkillBindingService | None = None
        self.automations: AutomationService | None = None
        self.references: ReferenceContinuityService | None = None
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
        self.typed_handoffs: TypedHandoffService | None = None
        self.light_swarm: LightSwarmService | None = None
        self.task_graph: TaskGraphService | None = None

    async def __aenter__(self) -> Self:
        self.session = await self.db_manager.get_session()
        self.session.info["tenant_id"] = current_context().tenant_id
        self.session.info["user_id"] = current_context().user_id
        self.session.info["tenant_roles"] = current_context().roles
        self.projects = ProjectService(self.session)
        self.tasks = TaskService(self.session)
        self.executions = ExecutionService(self.session)
        self.engineering = EngineeringContinuityService(self.session)
        self.continuity = self.engineering
        self.model_catalog = ModelCatalogService(self.session)
        self.skill_bindings = SkillBindingService(self.session)
        self.automations = AutomationService(self.session)
        self.references = ReferenceContinuityService(self.session)
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
        self.typed_handoffs = TypedHandoffService(self.session)
        self.light_swarm = LightSwarmService(self.session)
        self.task_graph = TaskGraphService(self.session)
        return self

    async def commit(self) -> None:
        """Explicitly commit the current session transaction."""
        if self.session:
            await self.session.commit()

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
                    # Persist buffered calls after rollback using this same
                    # session. Opening a second SQLite writer here can race
                    # with the recovery transaction on Windows.
                    await self._persist_pending_model_calls()
                elif self.read_only:
                    # Monitoring/query-only sessions must never compete with
                    # a scheduler writer by attempting a needless commit.
                    await self.session.rollback()
                else:
                    # Commit changes on success
                    await self.session.commit()
            finally:
                from localforge.services.model_calls import ModelCallLedgerService

                ModelCallLedgerService._pending_calls.clear()
                await self.session.close()

    async def _persist_pending_model_calls(self) -> None:
        from localforge.services.model_calls import ModelCallLedgerService

        pending_calls = list(ModelCallLedgerService._pending_calls)
        if not pending_calls or self.session is None:
            return
        try:
            from localforge.storage.orm import ModelCallLedgerORM

            for call in pending_calls:
                orm_obj = ModelCallLedgerORM.from_domain(call)
                self.session.add(orm_obj)
            await self.session.commit()
        except Exception as e:
            import logging

            logging.getLogger("localforge").error(
                f"Failed to persist pending model calls post-rollback: {e}"
            )

    async def persist_pending_model_calls(self) -> None:
        """Persist paid/local call evidence after a handled task failure.

        The scheduler catches task exceptions inside the UnitOfWork context so
        it can mark the task ``FAILED_SAFE`` and continue the run. In that
        path ``__aexit__`` sees no exception, therefore a rollback performed by
        the scheduler would otherwise discard the model-cost ledger. Expose a
        narrow public hook for that recovery path.
        """
        await self._persist_pending_model_calls()
