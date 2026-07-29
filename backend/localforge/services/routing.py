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

    async def get_model_capability(
        self, model_name: str, task_class: str
    ) -> domain.ModelCapability | None:
        from localforge.storage.orm import ModelCapabilityORM

        result = await self.session.execute(
            select(ModelCapabilityORM).where(
                ModelCapabilityORM.model_name == model_name,
                ModelCapabilityORM.task_class == task_class,
            )
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def save_model_capability(
        self, capability: domain.ModelCapability
    ) -> domain.ModelCapability:
        from localforge.storage.orm import ModelCapabilityORM

        result = await self.session.execute(
            select(ModelCapabilityORM).where(
                ModelCapabilityORM.model_name == capability.model_name,
                ModelCapabilityORM.task_class == capability.task_class,
            )
        )
        orm_obj = result.scalar_one_or_none()
        if orm_obj is None:
            orm_obj = ModelCapabilityORM.from_domain(capability)
            self.session.add(orm_obj)
        else:
            orm_obj.success_count = capability.success_count
            orm_obj.failure_count = capability.failure_count
            orm_obj.disqualified_until = capability.disqualified_until
            orm_obj.disqualification_reason = capability.disqualification_reason
            orm_obj.metadata_json = capability.metadata
        await self.session.flush()
        return orm_obj.to_domain()

    async def disqualify_model(
        self, model_name: str, task_class: str, reason: str, duration_seconds: int = 3600
    ) -> None:
        from datetime import UTC, datetime, timedelta

        cap = await self.get_model_capability(model_name, task_class)
        if not cap:
            cap = domain.ModelCapability(
                model_name=model_name,
                task_class=task_class,
                success_count=0,
                failure_count=1,
                disqualified_until=datetime.now(UTC) + timedelta(seconds=duration_seconds),
                disqualification_reason=reason,
            )
        else:
            cap.failure_count += 1
            cap.disqualified_until = datetime.now(UTC) + timedelta(seconds=duration_seconds)
            cap.disqualification_reason = reason
        await self.save_model_capability(cap)
