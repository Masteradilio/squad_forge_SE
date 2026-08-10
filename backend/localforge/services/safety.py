from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.services.tenant_context import session_tenant
from localforge.storage.orm import ActionApprovalORM, ProjectORM


class SafetyService:
    """Service layer managing action safety approvals queues."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _tenant_id(self) -> str:
        return session_tenant(self.session)

    async def create_approval(self, approval: domain.ActionApproval) -> domain.ActionApproval:
        """Create a new safety action approval request."""
        orm_obj = ActionApprovalORM.from_domain(approval)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_approval(self, approval_id: int) -> domain.ActionApproval | None:
        """Retrieve a specific action approval request by ID."""
        result = await self.session.execute(
            select(ActionApprovalORM)
            .join(ProjectORM, ProjectORM.id == ActionApprovalORM.project_id)
            .where(
                ActionApprovalORM.id == approval_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def update_approval(self, approval: domain.ActionApproval) -> domain.ActionApproval:
        """Update status, decisions, or metadata of an action approval request."""
        if not approval.id:
            raise ValueError("Cannot update an action approval without an ID.")

        result = await self.session.execute(
            select(ActionApprovalORM)
            .join(ProjectORM, ProjectORM.id == ActionApprovalORM.project_id)
            .where(
                ActionApprovalORM.id == approval.id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Action approval request with ID {approval.id} not found.")

        orm_obj.status = approval.status.value
        orm_obj.decided_at = approval.decided_at
        orm_obj.decided_by = approval.decided_by
        orm_obj.payload_json = approval.payload
        orm_obj.expires_at = approval.expires_at
        orm_obj.decision_nonce = approval.decision_nonce
        orm_obj.decision_reason = approval.decision_reason
        orm_obj.idempotency_key = approval.idempotency_key

        await self.session.flush()
        return orm_obj.to_domain()

    async def list_pending_approvals(self, project_id: int) -> list[domain.ActionApproval]:
        """List all pending action approvals for a specific project."""
        result = await self.session.execute(
            select(ActionApprovalORM)
            .join(ProjectORM, ProjectORM.id == ActionApprovalORM.project_id)
            .where(
                ActionApprovalORM.project_id == project_id,
                ActionApprovalORM.status == domain.ActionApprovalStatus.PENDING.value,
                ProjectORM.tenant_id == self._tenant_id(),
            )
            .order_by(ActionApprovalORM.created_at.asc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def list_approvals_for_project(self, project_id: int) -> list[domain.ActionApproval]:
        """List the complete approval history for a project."""
        result = await self.session.execute(
            select(ActionApprovalORM)
            .join(ProjectORM, ProjectORM.id == ActionApprovalORM.project_id)
            .where(
                ActionApprovalORM.project_id == project_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
            .order_by(ActionApprovalORM.created_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def list_approvals_for_run(self, run_id: int) -> list[domain.ActionApproval]:
        """List all action approvals generated during a specific run."""
        result = await self.session.execute(
            select(ActionApprovalORM)
            .join(ProjectORM, ProjectORM.id == ActionApprovalORM.project_id)
            .where(
                ActionApprovalORM.run_id == run_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
            .order_by(ActionApprovalORM.created_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]
