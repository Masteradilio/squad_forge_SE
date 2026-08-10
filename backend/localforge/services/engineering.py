"""Shared durable runtime for DPC-001, DPC-002, and DPC-003.

The API and CLI are deliberately thin adapters around this service.  All
resource lookups carry the current tenant and every child resource derives its
tenant from the visible project/session rather than trusting request data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import (
    ActionApprovalStatus,
    ActionKind,
    AuditEventActorType,
    AuditEventType,
    EngineeringSessionStatus,
    EngineeringTurnKind,
    ExecutionMode,
    ProfileDecision,
)
from localforge.services.audit import AuditService
from localforge.services.security_controls import redact_secrets_recursive
from localforge.services.tenant_context import session_tenant
from localforge.storage.orm import (
    ActionApprovalORM,
    EngineeringGoalORM,
    EngineeringSessionORM,
    EngineeringTurnORM,
    ExecutionProfileORM,
    ProjectORM,
)


class EngineeringError(ValueError):
    """Base error for invalid or inaccessible engineering operations."""


class EngineeringNotFound(EngineeringError):
    """A resource is absent or outside the current tenant."""


class EngineeringInvalidTransition(EngineeringError):
    """A session state transition is not allowed."""


class EngineeringLimitExceeded(EngineeringError):
    """A durable continuation limit prevents admission of another turn."""


class EngineeringImmutableTurn(EngineeringError):
    """Admitted turns are append-only and cannot be edited or removed."""


class EngineeringContinuityService:
    """Session, goal, turn, profile, and policy operations for one DB session."""

    _TRANSITIONS: dict[EngineeringSessionStatus, set[EngineeringSessionStatus]] = {
        EngineeringSessionStatus.DRAFT: {
            EngineeringSessionStatus.ACTIVE,
            EngineeringSessionStatus.CANCELLED,
        },
        EngineeringSessionStatus.ACTIVE: {
            EngineeringSessionStatus.PAUSED,
            EngineeringSessionStatus.BLOCKED,
            EngineeringSessionStatus.COMPLETED,
            EngineeringSessionStatus.CANCELLED,
        },
        EngineeringSessionStatus.PAUSED: {
            EngineeringSessionStatus.ACTIVE,
            EngineeringSessionStatus.CANCELLED,
        },
        EngineeringSessionStatus.BLOCKED: {
            EngineeringSessionStatus.ACTIVE,
            EngineeringSessionStatus.CANCELLED,
        },
        EngineeringSessionStatus.COMPLETED: set(),
        EngineeringSessionStatus.CANCELLED: set(),
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    def _tenant_id(self) -> str:
        return session_tenant(self.session)

    def _actor_id(self) -> str:
        return str(self.session.info.get("user_id") or "system")

    @staticmethod
    def _new_id() -> str:
        return uuid4().hex

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    async def _project(self, project_id: int) -> ProjectORM:
        result = await self.session.execute(
            select(ProjectORM).where(
                ProjectORM.id == project_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise EngineeringNotFound("Project is not accessible in the current tenant")
        return project

    async def _session(self, session_id: str) -> EngineeringSessionORM:
        result = await self.session.execute(
            select(EngineeringSessionORM).where(
                EngineeringSessionORM.id == session_id,
                EngineeringSessionORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise EngineeringNotFound("Engineering session not found")
        return resource

    async def _goal(self, goal_id: str) -> EngineeringGoalORM:
        result = await self.session.execute(
            select(EngineeringGoalORM).where(
                EngineeringGoalORM.id == goal_id,
                EngineeringGoalORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise EngineeringNotFound("Engineering goal not found")
        return resource

    async def _profile_by_id(self, profile_id: str) -> ExecutionProfileORM:
        result = await self.session.execute(
            select(ExecutionProfileORM).where(
                ExecutionProfileORM.id == profile_id,
                ExecutionProfileORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise EngineeringNotFound("Execution profile not found")
        return resource

    async def _audit(
        self,
        project_id: int,
        *,
        event_type: AuditEventType,
        payload: dict[str, Any],
        actor_id: str | None = None,
    ) -> None:
        await AuditService(self.session).append_audit_event(
            domain.AuditEvent(
                project_id=project_id,
                actor_type=AuditEventActorType.USER
                if actor_id or self._actor_id() != "system"
                else AuditEventActorType.SYSTEM,
                actor_id=actor_id or self._actor_id(),
                event_type=event_type,
                payload_redacted=payload,
            )
        )

    async def create_session(
        self,
        session: domain.EngineeringSession | None = None,
        *,
        project_id: int | None = None,
        title: str = "Engineering Session",
        default_model: str | None = None,
        max_turns: int | None = None,
        max_wall_seconds: float | None = None,
        max_retries: int = 0,
        quality_gate_names: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> domain.EngineeringSession:
        if session is None:
            if project_id is None:
                raise ValueError("project_id is required")
            session = domain.EngineeringSession(
                project_id=project_id,
                title=title,
                default_model=default_model,
                max_turns=max_turns,
                max_wall_seconds=max_wall_seconds,
                max_retries=max_retries,
                quality_gate_names=quality_gate_names or [],
                metadata=metadata or {},
            )
        project = await self._project(session.project_id)
        session = session.model_copy(
            update={
                "id": session.id or self._new_id(),
                "tenant_id": project.tenant_id,
                "project_id": project.id,
            }
        )
        orm_obj = EngineeringSessionORM.from_domain(session)
        self.session.add(orm_obj)
        await self.session.flush()

        # Existing projects created before DPC still receive a conservative,
        # persisted project profile when a continuity session is opened.
        await self._ensure_project_profile(project.id, project.tenant_id)
        await self._audit(
            project.id,
            event_type=AuditEventType.STATE_CHANGE,
            payload={
                "resource": "engineering_session",
                "operation": "create",
                "session_id": orm_obj.id,
                "status": orm_obj.status,
            },
        )
        return orm_obj.to_domain()

    async def get_session(self, session_id: str) -> domain.EngineeringSession | None:
        result = await self.session.execute(
            select(EngineeringSessionORM).where(
                EngineeringSessionORM.id == session_id,
                EngineeringSessionORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        return resource.to_domain() if resource else None

    async def list_sessions(
        self,
        project_id: int,
        *,
        status: EngineeringSessionStatus | None = None,
    ) -> list[domain.EngineeringSession]:
        # A project from another tenant is intentionally indistinguishable
        # from a project with no engineering sessions.  Collection endpoints
        # return an empty result instead of disclosing the project's existence.
        project_result = await self.session.execute(
            select(ProjectORM.id).where(
                ProjectORM.id == project_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        if project_result.scalar_one_or_none() is None:
            return []
        stmt = select(EngineeringSessionORM).where(
            EngineeringSessionORM.project_id == project_id,
            EngineeringSessionORM.tenant_id == self._tenant_id(),
        )
        if status is not None:
            stmt = stmt.where(EngineeringSessionORM.status == status.value)
        result = await self.session.execute(
            stmt.order_by(EngineeringSessionORM.created_at.desc())
        )
        return [item.to_domain() for item in result.scalars().all()]

    async def transition_session(
        self,
        session_id: str,
        status: EngineeringSessionStatus,
        *,
        reason: str = "",
        result: str | None = None,
        actor_id: str | None = None,
    ) -> domain.EngineeringSession:
        resource = await self._session(session_id)
        current = EngineeringSessionStatus(resource.status)
        if status == current or status not in self._TRANSITIONS[current]:
            raise EngineeringInvalidTransition(
                f"Invalid engineering session transition {current.value} -> {status.value}"
            )
        now = datetime.now(UTC)
        resource.status = status.value
        resource.revision += 1
        resource.updated_at = now
        if result is not None:
            resource.result = result
        if status in {
            EngineeringSessionStatus.COMPLETED,
            EngineeringSessionStatus.CANCELLED,
        }:
            resource.closed_at = now
        if resource.current_goal_id:
            goal = await self._goal(resource.current_goal_id)
            goal.status = status.value
            goal.updated_at = now
        await self.session.flush()
        await self._audit(
            resource.project_id,
            event_type=AuditEventType.STATE_CHANGE,
            payload={
                "resource": "engineering_session",
                "operation": "transition",
                "session_id": resource.id,
                "from": current.value,
                "to": status.value,
                "reason": reason,
            },
            actor_id=actor_id,
        )
        return resource.to_domain()

    async def close_session(
        self, session_id: str, *, result: str | None = None, reason: str = "closed"
    ) -> domain.EngineeringSession:
        return await self.transition_session(
            session_id,
            EngineeringSessionStatus.COMPLETED,
            reason=reason,
            result=result,
        )

    async def pause_session(self, session_id: str, *, reason: str = "user_pause") -> domain.EngineeringSession:
        return await self.transition_session(session_id, EngineeringSessionStatus.PAUSED, reason=reason)

    async def resume_session(self, session_id: str, *, reason: str = "user_resume") -> domain.EngineeringSession:
        return await self.transition_session(session_id, EngineeringSessionStatus.ACTIVE, reason=reason)

    async def cancel_session(self, session_id: str, *, reason: str = "user_cancel") -> domain.EngineeringSession:
        return await self.transition_session(session_id, EngineeringSessionStatus.CANCELLED, reason=reason)

    async def block_session(self, session_id: str, *, reason: str = "blocked") -> domain.EngineeringSession:
        return await self.transition_session(session_id, EngineeringSessionStatus.BLOCKED, reason=reason)

    async def create_goal(
        self, goal: domain.EngineeringGoal | None = None, *, session_id: str | None = None,
        objective: str = "", acceptance_criteria: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> domain.EngineeringGoal:
        if goal is None:
            if session_id is None or not objective.strip():
                raise ValueError("session_id and a non-empty objective are required")
            goal = domain.EngineeringGoal(
                session_id=session_id,
                project_id=0,
                objective=objective,
                acceptance_criteria=acceptance_criteria or [],
                metadata=metadata or {},
            )
        session = await self._session(goal.session_id)
        if session.current_goal_id:
            raise EngineeringError("Engineering session already has a goal; revise it instead")
        if EngineeringSessionStatus(session.status) in {
            EngineeringSessionStatus.COMPLETED,
            EngineeringSessionStatus.CANCELLED,
        }:
            raise EngineeringInvalidTransition("Cannot create a goal in a closed session")
        goal = goal.model_copy(
            update={
                "id": goal.id or self._new_id(),
                "project_id": session.project_id,
                "tenant_id": session.tenant_id,
                "status": EngineeringSessionStatus(session.status),
                "revision": 1,
            }
        )
        orm_obj = EngineeringGoalORM.from_domain(goal)
        self.session.add(orm_obj)
        session.current_goal_id = orm_obj.id
        session.revision += 1
        session.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self._audit(
            session.project_id,
            event_type=AuditEventType.SYSTEM_EVENT,
            payload={
                "resource": "engineering_goal",
                "operation": "create",
                "session_id": session.id,
                "goal_id": orm_obj.id,
                "revision": orm_obj.revision,
            },
        )
        return orm_obj.to_domain()

    async def get_goal(self, goal_id: str) -> domain.EngineeringGoal | None:
        result = await self.session.execute(
            select(EngineeringGoalORM).where(
                EngineeringGoalORM.id == goal_id,
                EngineeringGoalORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        return resource.to_domain() if resource else None

    async def get_current_goal(self, session_id: str) -> domain.EngineeringGoal | None:
        session = await self._session(session_id)
        if not session.current_goal_id:
            return None
        return await self.get_goal(session.current_goal_id)

    async def revise_goal(
        self,
        goal_id: str,
        objective: str,
        acceptance_criteria: list[str] | None = None,
        *,
        expected_revision: int | None = None,
        metadata: dict[str, Any] | None = None,
        reason: str = "goal_revision",
    ) -> domain.EngineeringGoal:
        goal = await self._goal(goal_id)
        session = await self._session(goal.session_id)
        if EngineeringSessionStatus(session.status) in {
            EngineeringSessionStatus.COMPLETED,
            EngineeringSessionStatus.CANCELLED,
        }:
            raise EngineeringInvalidTransition("Cannot revise a goal in a closed session")
        if expected_revision is not None and expected_revision != goal.revision:
            raise EngineeringError(
                f"Goal revision conflict: expected {expected_revision}, current {goal.revision}"
            )
        if not objective.strip():
            raise ValueError("objective must be non-empty")
        history = list(goal.revision_history_json or [])
        history.append(
            {
                "revision": goal.revision,
                "objective": goal.objective,
                "acceptance_criteria": list(goal.acceptance_criteria_json or []),
                "updated_at": self._aware(goal.updated_at).isoformat(),
            }
        )
        old_revision = goal.revision
        goal.objective = objective
        goal.acceptance_criteria_json = list(acceptance_criteria or [])
        goal.revision += 1
        goal.revision_history_json = history
        if metadata is not None:
            goal.metadata_json = dict(metadata)
        goal.updated_at = datetime.now(UTC)
        session.revision += 1
        session.updated_at = datetime.now(UTC)
        await self.session.flush()
        await self._audit(
            session.project_id,
            event_type=AuditEventType.STATE_CHANGE,
            payload={
                "resource": "engineering_goal",
                "operation": "revise",
                "session_id": session.id,
                "goal_id": goal.id,
                "from_revision": old_revision,
                "to_revision": goal.revision,
                "reason": reason,
            },
        )
        return goal.to_domain()

    async def _turn_for_key(self, session_id: str, idempotency_key: str) -> EngineeringTurnORM | None:
        result = await self.session.execute(
            select(EngineeringTurnORM).where(
                EngineeringTurnORM.session_id == session_id,
                EngineeringTurnORM.tenant_id == self._tenant_id(),
                EngineeringTurnORM.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def _resolve_profile_for_session(
        self, project_id: int, session_id: str | None = None, *, name: str = "default"
    ) -> domain.ExecutionProfile:
        project = await self._project(project_id)
        if session_id is not None:
            session = await self._session(session_id)
            if session.project_id != project.id:
                raise EngineeringNotFound("Engineering session does not belong to the project")
            result = await self.session.execute(
                select(ExecutionProfileORM).where(
                    ExecutionProfileORM.project_id == project.id,
                    ExecutionProfileORM.tenant_id == project.tenant_id,
                    ExecutionProfileORM.session_id == session.id,
                    ExecutionProfileORM.name == name,
                )
            )
            profile = result.scalar_one_or_none()
            if profile is not None:
                return profile.to_domain()
        result = await self.session.execute(
            select(ExecutionProfileORM).where(
                ExecutionProfileORM.project_id == project.id,
                ExecutionProfileORM.tenant_id == project.tenant_id,
                ExecutionProfileORM.session_id.is_(None),
                ExecutionProfileORM.name == name,
            )
        )
        profile = result.scalar_one_or_none()
        if profile is not None:
            return profile.to_domain()
        return domain.ExecutionProfile(
            project_id=project.id,
            tenant_id=project.tenant_id,
            name=name,
            mode=ExecutionMode.ASK,
            tool_policies={},
        )

    async def _ensure_project_profile(self, project_id: int, tenant_id: str) -> domain.ExecutionProfile:
        result = await self.session.execute(
            select(ExecutionProfileORM).where(
                ExecutionProfileORM.project_id == project_id,
                ExecutionProfileORM.tenant_id == tenant_id,
                ExecutionProfileORM.session_id.is_(None),
                ExecutionProfileORM.name == "default",
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing.to_domain()
        profile = domain.ExecutionProfile(
            id=self._new_id(),
            project_id=project_id,
            tenant_id=tenant_id,
            mode=ExecutionMode.ASK,
        )
        orm_obj = ExecutionProfileORM.from_domain(profile)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def create_or_update_profile(
        self, profile: domain.ExecutionProfile | None = None, *, project_id: int | None = None,
        session_id: str | None = None, name: str = "default", trust: str = "standard",
        mode: ExecutionMode = ExecutionMode.ASK,
        tool_policies: dict[str, ProfileDecision | str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> domain.ExecutionProfile:
        if profile is None:
            if project_id is None:
                raise ValueError("project_id is required")
            profile = domain.ExecutionProfile(
                project_id=project_id,
                session_id=session_id,
                name=name,
                trust=trust,
                mode=mode,
                tool_policies={
                    key: ProfileDecision(str(value).lower())
                    for key, value in (tool_policies or {}).items()
                },
                metadata=metadata or {},
            )
        project = await self._project(profile.project_id)
        if profile.session_id is not None:
            owner = await self._session(profile.session_id)
            if owner.project_id != project.id:
                raise EngineeringNotFound("Engineering session does not belong to the project")
        normalized_policies = {
            str(key).strip().lower(): ProfileDecision(str(value).lower())
            for key, value in profile.tool_policies.items()
        }
        existing: ExecutionProfileORM | None = None
        if profile.id:
            existing = await self._profile_by_id(profile.id)
            if existing.project_id != project.id or existing.session_id != profile.session_id:
                raise EngineeringError("Execution profile scope cannot be changed")
        if existing is None:
            result = await self.session.execute(
                select(ExecutionProfileORM).where(
                    ExecutionProfileORM.project_id == project.id,
                    ExecutionProfileORM.tenant_id == project.tenant_id,
                    ExecutionProfileORM.session_id == profile.session_id,
                    ExecutionProfileORM.name == profile.name,
                )
            )
            existing = result.scalar_one_or_none()
        if existing is None:
            profile = profile.model_copy(
                update={
                    "id": profile.id or self._new_id(),
                    "tenant_id": project.tenant_id,
                    "project_id": project.id,
                    "tool_policies": normalized_policies,
                    "revision": 1,
                }
            )
            orm_obj = ExecutionProfileORM.from_domain(profile)
            self.session.add(orm_obj)
        else:
            existing.revision += 1
            existing.trust = profile.trust
            existing.mode = profile.mode.value
            existing.tool_policies_json = {
                key: value.value for key, value in normalized_policies.items()
            }
            existing.metadata_json = dict(profile.metadata)
            existing.updated_at = datetime.now(UTC)
            orm_obj = existing
        await self.session.flush()
        await self._audit(
            project.id,
            event_type=AuditEventType.STATE_CHANGE,
            payload={
                "resource": "execution_profile",
                "operation": "upsert",
                "profile_id": orm_obj.id,
                "session_id": orm_obj.session_id,
                "revision": orm_obj.revision,
                "mode": orm_obj.mode,
            },
        )
        return orm_obj.to_domain()

    # Short aliases keep the shared service ergonomic for API/CLI adapters.
    upsert_execution_profile = create_or_update_profile
    create_profile = create_or_update_profile

    async def get_profile(self, profile_id: str) -> domain.ExecutionProfile | None:
        result = await self.session.execute(
            select(ExecutionProfileORM).where(
                ExecutionProfileORM.id == profile_id,
                ExecutionProfileORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        return resource.to_domain() if resource else None

    async def list_profiles(self, project_id: int) -> list[domain.ExecutionProfile]:
        await self._project(project_id)
        result = await self.session.execute(
            select(ExecutionProfileORM)
            .where(
                ExecutionProfileORM.project_id == project_id,
                ExecutionProfileORM.tenant_id == self._tenant_id(),
            )
            .order_by(ExecutionProfileORM.session_id, ExecutionProfileORM.name)
        )
        return [resource.to_domain() for resource in result.scalars().all()]

    async def resolve_profile(
        self, project_id: int, *, session_id: str | None = None, turn_id: str | None = None,
        name: str = "default",
    ) -> domain.ExecutionProfile:
        if turn_id is not None:
            turn = await self._turn(turn_id)
            if turn.project_id != project_id:
                raise EngineeringNotFound("Engineering turn does not belong to the project")
            if turn.profile_snapshot_json:
                return domain.ExecutionProfile.model_validate(turn.profile_snapshot_json)
            session_id = turn.session_id
        return await self._resolve_profile_for_session(project_id, session_id, name=name)

    async def _turn(self, turn_id: str) -> EngineeringTurnORM:
        result = await self.session.execute(
            select(EngineeringTurnORM).where(
                EngineeringTurnORM.id == turn_id,
                EngineeringTurnORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        if resource is None:
            raise EngineeringNotFound("Engineering turn not found")
        return resource

    async def _check_turn_limits(
        self, session: EngineeringSessionORM, *, existing_turns: int, retry_count: int,
        metadata: dict[str, Any], now: datetime,
    ) -> None:
        # Import lazily: runtime/__init__ imports Safety Kernel, whose public
        # type boundary imports UnitOfWork.  Loading this only after the
        # transaction module is initialized avoids a storage/runtime cycle.
        from localforge.runtime.run_control import RunContinuationPolicy

        policy = RunContinuationPolicy(
            max_turns=session.max_turns or (2**31 - 1),
            max_wall_seconds=session.max_wall_seconds,
            max_retries=session.max_retries,
            quality_gate_names=list(session.quality_gate_names_json or []),
        )
        elapsed = max((now - self._aware(session.created_at)).total_seconds(), 0.0)
        retries = retry_count if retry_count > 0 else None
        quality_gates = metadata.get("quality_gates")
        if not policy.should_continue(
            turns=existing_turns,
            elapsed_seconds=elapsed,
            retries=retries,
            quality_gates=quality_gates,
        ):
            await self._audit(
                session.project_id,
                event_type=AuditEventType.STATE_CHANGE,
                payload={
                    "resource": "engineering_session",
                    "operation": "turn_limit_rejected",
                    "session_id": session.id,
                    "turns": existing_turns,
                    "retry_count": retry_count,
                    "elapsed_seconds": elapsed,
                },
            )
            raise EngineeringLimitExceeded("Engineering continuation policy rejected the turn")

    async def admit_turn(
        self, turn: domain.EngineeringTurn | None = None, *, session_id: str | None = None,
        input_text: str = "", kind: EngineeringTurnKind = EngineeringTurnKind.USER,
        idempotency_key: str | None = None, model: str | None = None,
        result: str | None = None, retry_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> domain.EngineeringTurn:
        if turn is not None:
            session_id = turn.session_id
            input_text = turn.input_text
            kind = turn.kind
            idempotency_key = turn.idempotency_key
            model = turn.model_snapshot
            result = turn.result
            retry_count = turn.retry_count
            metadata = turn.metadata
        if not session_id or not idempotency_key:
            raise ValueError("session_id and idempotency_key are required")
        session = await self._session(session_id)
        existing = await self._turn_for_key(session.id, idempotency_key)
        if existing is not None:
            return existing.to_domain()
        state = EngineeringSessionStatus(session.status)
        if state in {EngineeringSessionStatus.COMPLETED, EngineeringSessionStatus.CANCELLED}:
            raise EngineeringInvalidTransition("Cannot admit a turn into a closed session")
        now = datetime.now(UTC)
        count_result = await self.session.execute(
            select(func.count(EngineeringTurnORM.id)).where(
                EngineeringTurnORM.session_id == session.id,
                EngineeringTurnORM.tenant_id == self._tenant_id(),
            )
        )
        existing_turns = int(count_result.scalar_one())
        metadata_value = dict(metadata or {})
        await self._check_turn_limits(
            session,
            existing_turns=existing_turns,
            retry_count=retry_count,
            metadata=metadata_value,
            now=now,
        )
        goal = await self.get_current_goal(session.id)
        profile = await self._resolve_profile_for_session(session.project_id, session.id)
        sequence_result = await self.session.execute(
            select(func.max(EngineeringTurnORM.sequence)).where(
                EngineeringTurnORM.session_id == session.id,
                EngineeringTurnORM.tenant_id == self._tenant_id(),
            )
        )
        sequence = int(sequence_result.scalar_one() or 0) + 1
        turn_domain = domain.EngineeringTurn(
            id=self._new_id(),
            session_id=session.id,
            project_id=session.project_id,
            tenant_id=session.tenant_id,
            goal_id=goal.id if goal else None,
            goal_revision_snapshot=goal.revision if goal else None,
            sequence=sequence,
            kind=kind,
            input_text=input_text,
            result=result,
            status="ADMITTED",
            idempotency_key=idempotency_key,
            model_snapshot=model or session.default_model,
            profile_id_snapshot=profile.id,
            profile_revision_snapshot=profile.revision,
            profile_snapshot=profile.model_dump(mode="json"),
            retry_count=retry_count,
            metadata=metadata_value,
            admitted_at=now,
        )
        orm_obj = EngineeringTurnORM.from_domain(turn_domain)
        self.session.add(orm_obj)
        if state == EngineeringSessionStatus.DRAFT:
            session.status = EngineeringSessionStatus.ACTIVE.value
            session.revision += 1
            session.updated_at = now
            if goal:
                goal_orm = await self._goal(goal.id or "")
                goal_orm.status = EngineeringSessionStatus.ACTIVE.value
                goal_orm.updated_at = now
        await self.session.flush()
        await self._audit(
            session.project_id,
            event_type=AuditEventType.STATE_CHANGE,
            payload={
                "resource": "engineering_turn",
                "operation": "admit",
                "session_id": session.id,
                "turn_id": orm_obj.id,
                "sequence": sequence,
                "idempotency_key": idempotency_key,
                "goal_revision": turn_domain.goal_revision_snapshot,
                "profile_revision": profile.revision,
            },
        )
        return orm_obj.to_domain()

    async def steer(
        self, session_id: str, instruction: str, *, idempotency_key: str | None = None
    ) -> domain.EngineeringTurn:
        if not instruction.strip():
            raise ValueError("steering instruction must be non-empty")
        key = idempotency_key or self._derived_key("steer", session_id, instruction)
        return await self.admit_turn(
            session_id=session_id,
            input_text=instruction,
            kind=EngineeringTurnKind.STEER,
            idempotency_key=key,
            metadata={"steering": True},
        )

    async def list_turns(self, session_id: str) -> list[domain.EngineeringTurn]:
        await self._session(session_id)
        result = await self.session.execute(
            select(EngineeringTurnORM)
            .where(
                EngineeringTurnORM.session_id == session_id,
                EngineeringTurnORM.tenant_id == self._tenant_id(),
            )
            .order_by(EngineeringTurnORM.sequence.asc())
        )
        return [resource.to_domain() for resource in result.scalars().all()]

    async def timeline(self, session_id: str) -> list[domain.EngineeringTurn]:
        return await self.list_turns(session_id)

    async def get_turn(self, turn_id: str) -> domain.EngineeringTurn | None:
        result = await self.session.execute(
            select(EngineeringTurnORM).where(
                EngineeringTurnORM.id == turn_id,
                EngineeringTurnORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        return resource.to_domain() if resource else None

    async def update_turn(self, *_: Any, **__: Any) -> None:
        raise EngineeringImmutableTurn("Admitted engineering turns are immutable")

    async def delete_turn(self, *_: Any, **__: Any) -> None:
        raise EngineeringImmutableTurn("Admitted engineering turns cannot be deleted")

    @staticmethod
    def _derived_key(kind: str, session_id: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
        return f"engineering:{kind}:{session_id}:{digest}"

    async def _existing_approval(
        self, project_id: int, idempotency_key: str
    ) -> domain.ActionApproval | None:
        result = await self.session.execute(
            select(ActionApprovalORM)
            .join(ProjectORM, ProjectORM.id == ActionApprovalORM.project_id)
            .where(
                ActionApprovalORM.project_id == project_id,
                ActionApprovalORM.idempotency_key == idempotency_key,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        resource = result.scalar_one_or_none()
        return resource.to_domain() if resource else None

    async def evaluate_action(
        self,
        *,
        project_id: int,
        action_kind: ActionKind | str,
        payload: dict[str, Any] | None = None,
        purpose: str = "engineering turn action",
        risk_level: str = "low",
        session_id: str | None = None,
        turn_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> domain.ProfileEvaluation:
        project = await self._project(project_id)
        kind = action_kind if isinstance(action_kind, ActionKind) else ActionKind(str(action_kind))
        turn = await self._turn(turn_id) if turn_id else None
        if turn is not None:
            if turn.project_id != project.id:
                raise EngineeringNotFound("Engineering turn does not belong to the project")
            session_id = turn.session_id
        profile = await self.resolve_profile(
            project.id,
            session_id=session_id,
            turn_id=turn_id,
        )

        # Safety Kernel is the first authority and can never be bypassed by a
        # FULL_ACCESS profile or an explicit allow rule.
        from localforge.safety.kernel import ActionRequest, SafetyDecision, SafetyKernel

        request = ActionRequest(
            project_id=project.id,
            kind=kind,
            payload=redact_secrets_recursive(payload or {}),
            purpose=purpose,
            risk_level=risk_level,
        )
        safety_decision, safety_reason = await SafetyKernel.evaluate(
            request,
            SimpleNamespace(audits=AuditService(self.session)),
            project.root_path,
        )
        if safety_decision == SafetyDecision.DENY:
            evaluation = domain.ProfileEvaluation(
                decision=ProfileDecision.DENY.value,
                reason=safety_reason,
                profile_id=profile.id,
                profile_revision=profile.revision,
                safety_decision=safety_decision.value,
            )
            await self._audit(
                project.id,
                event_type=AuditEventType.SAFETY_DECISION,
                payload={
                    "resource": "execution_profile",
                    "decision": evaluation.decision,
                    "safety_decision": safety_decision.value,
                    "reason": safety_reason,
                    "profile_id": profile.id,
                    "turn_id": turn.id if turn else None,
                },
            )
            return evaluation

        policy_value = profile.tool_policies.get(kind.value) or profile.tool_policies.get("*")
        policy_decision = ProfileDecision(str(policy_value).lower()) if policy_value else None
        if policy_decision == ProfileDecision.DENY:
            decision = ProfileDecision.DENY
            reason = "Execution profile explicitly denies this tool"
        elif policy_decision == ProfileDecision.ASK:
            decision = ProfileDecision.ASK
            reason = "Execution profile requires ActionApproval for this tool"
        elif policy_decision == ProfileDecision.ALLOW:
            # Explicit allow has higher precedence than a mode's default
            # restriction, while Safety Kernel remains authoritative above it.
            decision = ProfileDecision.ALLOW
            reason = "Execution profile explicitly allows this tool"
        elif profile.mode == ExecutionMode.READ_ONLY:
            decision = ProfileDecision.ALLOW if kind == ActionKind.READ_FILE else ProfileDecision.DENY
            reason = "READ_ONLY mode restricts mutating tools"
        elif profile.mode == ExecutionMode.ASK:
            decision = ProfileDecision.ALLOW if kind == ActionKind.READ_FILE else ProfileDecision.ASK
            reason = "ASK mode requires approval for mutating tools"
        else:
            decision = ProfileDecision.ALLOW
            reason = "FULL_ACCESS mode permits the tool subject to Safety Kernel"

        approval_id: int | None = None
        if decision == ProfileDecision.ASK or safety_decision == SafetyDecision.REQUIRE_APPROVAL:
            key = idempotency_key or self._derived_key(
                "approval", turn.id if turn else session_id or str(project.id),
                json.dumps({"kind": kind.value, "payload": request.payload}, sort_keys=True),
            )
            existing = await self._existing_approval(project.id, key)
            if existing is not None:
                approval_id = existing.id
            else:
                approval_orm = ActionApprovalORM.from_domain(
                    domain.ActionApproval(
                        project_id=project.id,
                        action_kind=kind,
                        payload=request.payload,
                        purpose=purpose,
                        risk_level=risk_level,
                        status=ActionApprovalStatus.PENDING,
                        idempotency_key=key,
                    )
                )
                self.session.add(approval_orm)
                await self.session.flush()
                approval_id = approval_orm.id
            decision = ProfileDecision.ASK
            reason = safety_reason if safety_decision == SafetyDecision.REQUIRE_APPROVAL else reason
        evaluation = domain.ProfileEvaluation(
            decision=decision.value,
            reason=reason,
            profile_id=profile.id,
            profile_revision=profile.revision,
            safety_decision=safety_decision.value,
            approval_id=approval_id,
        )
        await self._audit(
            project.id,
            event_type=AuditEventType.SAFETY_DECISION,
            payload={
                "resource": "execution_profile",
                "decision": evaluation.decision,
                "safety_decision": safety_decision.value,
                "reason": reason,
                "profile_id": profile.id,
                "profile_revision": profile.revision,
                "approval_id": approval_id,
                "turn_id": turn.id if turn else None,
            },
        )
        return evaluation


# The shorter name is useful to integrations that refer to this as the
# continuity service while retaining the explicit DPC-facing class name.
EngineeringService = EngineeringContinuityService
