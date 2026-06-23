from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import AgentRole
from localforge.storage.orm import ModelRouteORM


class ModelRoutingService:
    """Persist role-to-model routing for a project."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_routes(self, project_id: int) -> list[domain.ModelRoute]:
        result = await self.session.execute(
            select(ModelRouteORM)
            .where(ModelRouteORM.project_id == project_id)
            .order_by(ModelRouteORM.role)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def upsert_route(self, route: domain.ModelRoute) -> domain.ModelRoute:
        result = await self.session.execute(
            select(ModelRouteORM).where(
                ModelRouteORM.project_id == route.project_id,
                ModelRouteORM.role == route.role.value,
            )
        )
        orm_obj = result.scalar_one_or_none()
        if orm_obj is None:
            orm_obj = ModelRouteORM.from_domain(route)
            self.session.add(orm_obj)
        else:
            orm_obj.provider = route.provider
            orm_obj.model_profile_id = route.model_profile_id
            orm_obj.endpoint_url = route.endpoint_url
            orm_obj.fallback_model_profile_id = route.fallback_model_profile_id
            orm_obj.updated_at = datetime.now(UTC)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_model_for_role(self, project_id: int, role: AgentRole) -> str | None:
        result = await self.session.execute(
            select(ModelRouteORM.model_profile_id).where(
                ModelRouteORM.project_id == project_id,
                ModelRouteORM.role == role.value,
            )
        )
        return result.scalar_one_or_none()
