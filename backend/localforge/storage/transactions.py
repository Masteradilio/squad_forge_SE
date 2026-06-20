from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession

from localforge.services.audit import AuditService
from localforge.services.execution import ExecutionService
from localforge.services.project import ProjectService
from localforge.services.safety import SafetyService
from localforge.services.task import TaskService
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

    async def __aenter__(self) -> Self:
        self.session = await self.db_manager.get_session()
        self.projects = ProjectService(self.session)
        self.tasks = TaskService(self.session)
        self.executions = ExecutionService(self.session)
        self.audits = AuditService(self.session)
        self.safety = SafetyService(self.session)
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
                else:
                    # Commit changes on success
                    await self.session.commit()
            finally:
                await self.session.close()
