from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import AuditEventActorType, AuditEventType, HandoffKind, TaskStatus
from localforge.services.tenant_context import session_tenant
from localforge.storage.orm import (
    ArtifactORM,
    AuditEventORM,
    EpicORM,
    HandoffORM,
    ProjectORM,
    TaskORM,
    TaskRunORM,
    WorktreeAttemptManifestORM,
)

# Explicit task status state machine
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.READY: {
        TaskStatus.CLAIMED,
        TaskStatus.BACKLOG,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.CLAIMED: {
        TaskStatus.PLANNING,
        TaskStatus.READY,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED_SAFE,
    },
    TaskStatus.PLANNING: {
        TaskStatus.IMPLEMENTING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED_SAFE,
    },
    TaskStatus.IMPLEMENTING: {
        TaskStatus.TESTING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED_SAFE,
    },
    TaskStatus.TESTING: {
        TaskStatus.REVIEWING,
        TaskStatus.REPAIRING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED_SAFE,
    },
    TaskStatus.REPAIRING: {
        TaskStatus.TESTING,
        TaskStatus.FAILED_SAFE,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.REVIEWING: {
        TaskStatus.PR_READY,
        TaskStatus.REPAIRING,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED_SAFE,
    },
    TaskStatus.PR_READY: {TaskStatus.DONE, TaskStatus.FAILED_SAFE, TaskStatus.CANCELLED},
    TaskStatus.BLOCKED: {
        TaskStatus.READY,
        TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
        TaskStatus.CANCELLED,
    },
    TaskStatus.FAILED_SAFE: {
        TaskStatus.READY,
        TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW: {
        TaskStatus.READY,
        TaskStatus.CANCELLED,
    },
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


class TaskService:
    """Service layer for Epic, Task, and TaskRun persistence and state transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _tenant_id(self) -> str:
        return session_tenant(self.session)

    async def _project_is_visible(self, project_id: int) -> bool:
        result = await self.session.execute(
            select(ProjectORM.id).where(
                ProjectORM.id == project_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        return result.scalar_one_or_none() is not None

    # Epic Operations
    async def create_epic(self, epic: domain.Epic) -> domain.Epic:
        """Create a new epic."""
        orm_obj = EpicORM.from_domain(epic)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_epic(self, epic_id: int) -> domain.Epic | None:
        """Retrieve an epic by its ID."""
        result = await self.session.execute(select(EpicORM).where(EpicORM.id == epic_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_epics_for_project(self, project_id: int) -> list[domain.Epic]:
        """List all epics for a project."""
        result = await self.session.execute(
            select(EpicORM)
            .where(EpicORM.project_id == project_id)
            .order_by(EpicORM.priority.desc(), EpicORM.id)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    # Task Operations
    async def create_task(self, task: domain.Task) -> domain.Task:
        """Create a new task."""
        if not await self._project_is_visible(task.project_id):
            raise ValueError("Project is not accessible in the current tenant")
        orm_obj = TaskORM.from_domain(task)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_task(self, task_id: int) -> domain.Task | None:
        """Retrieve a task by database ID."""
        result = await self.session.execute(
            select(TaskORM)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskORM.id == task_id, ProjectORM.tenant_id == self._tenant_id())
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_task_by_key(self, key: str) -> domain.Task | None:
        """Retrieve a task by its unique key (e.g. LF-0101)."""
        result = await self.session.execute(
            select(TaskORM)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskORM.key == key, ProjectORM.tenant_id == self._tenant_id())
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_tasks_for_project(self, project_id: int) -> list[domain.Task]:
        """List all tasks in a project."""
        result = await self.session.execute(
            select(TaskORM)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(
                TaskORM.project_id == project_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
            .order_by(TaskORM.created_at)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_task_status(self, task_id: int, new_status: TaskStatus) -> domain.Task:
        """Update the status of a task after validating state transitions."""
        if new_status == TaskStatus.PR_READY:
            raise ValueError("Use mark_pr_ready() for the server-owned PR_READY transition")
        return await self._update_task_status(task_id, new_status, allow_pr_ready=False)

    async def _update_task_status(
        self, task_id: int, new_status: TaskStatus, *, allow_pr_ready: bool
    ) -> domain.Task:
        """Update task status after validating state transitions.

        PR_READY is intentionally private to mark_pr_ready(), where evidence is
        persisted atomically before the state transition.
        """
        result = await self.session.execute(
            select(TaskORM)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskORM.id == task_id, ProjectORM.tenant_id == self._tenant_id())
        )
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Task with ID {task_id} not found")

        current_status = TaskStatus(orm_obj.status)

        if current_status == new_status:
            return orm_obj.to_domain()

        if new_status == TaskStatus.PR_READY and not allow_pr_ready:
            raise ValueError("Use mark_pr_ready() for the server-owned PR_READY transition")

        allowed_next = VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            raise ValueError(f"Illegal state transition from {current_status} to {new_status}")

        orm_obj.status = new_status.value

        # Create and persist AuditEvent
        audit = domain.AuditEvent(
            project_id=orm_obj.project_id,
            actor_type=AuditEventActorType.SYSTEM,
            actor_id="task-service",
            event_type=AuditEventType.STATE_CHANGE,
            payload_redacted={
                "task_key": orm_obj.key,
                "from_status": current_status.value,
                "to_status": new_status.value,
            },
        )
        audit_orm = AuditEventORM.from_domain(audit)
        self.session.add(audit_orm)

        await self.session.flush()
        return orm_obj.to_domain()

    async def mark_pr_ready(
        self,
        task_id: int,
        *,
        gate_evidence: dict[str, object],
    ) -> domain.Task:
        """Central server-owned transition to PR_READY with persisted gate evidence."""
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task with ID {task_id} not found")
        if not gate_evidence:
            raise ValueError("PR_READY transition requires explicit gate evidence")
        evidence = await self._validate_pr_ready_evidence(task_id, gate_evidence)
        normalized_evidence = evidence.model_dump(mode="json", by_alias=True)
        if task.status == TaskStatus.PR_READY:
            existing_gate = (task.metadata or {}).get("pr_ready_gate")
            existing_evidence = (
                existing_gate.get("evidence") if isinstance(existing_gate, dict) else None
            )
            if isinstance(existing_evidence, dict) and existing_evidence == normalized_evidence:
                return task
            raise ValueError("PR_READY transition has already been recorded for this task")

        metadata = dict(task.metadata or {})
        metadata["pr_ready_gate"] = {
            "passed": True,
            "evidence": normalized_evidence,
        }
        task.metadata = metadata
        task.updated_at = domain.utc_now()
        await self.update_task(task)
        return await self._update_task_status(task_id, TaskStatus.PR_READY, allow_pr_ready=True)

    async def _validate_pr_ready_evidence(
        self, task_id: int, gate_evidence: dict[str, object]
    ) -> domain.PRReadyEvidence:
        evidence = domain.PRReadyEvidence.model_validate(gate_evidence)
        task_run = await self.get_task_run(evidence.task_run_id)
        if task_run is None:
            raise ValueError(f"TaskRun with ID {evidence.task_run_id} not found")
        if task_run.task_id != task_id:
            raise ValueError("PR_READY evidence task_run_id does not belong to task")
        if evidence.branch_name and evidence.branch_name != task_run.branch_name:
            raise ValueError("PR_READY evidence branch_name does not match task run")
        if evidence.worktree_path and evidence.worktree_path != task_run.worktree_path:
            raise ValueError("PR_READY evidence worktree_path does not match task run")
        await self._validate_pr_ready_handoff(evidence)
        await self._validate_pr_ready_commit_binding(task_id, evidence)

        result = await self.session.execute(
            select(ArtifactORM)
            .join(TaskRunORM, TaskRunORM.id == ArtifactORM.task_run_id)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(ArtifactORM.task_run_id == evidence.task_run_id, ProjectORM.tenant_id == self._tenant_id())
            .order_by(ArtifactORM.created_at)
        )
        artifacts = result.scalars().all()
        if not artifacts:
            raise ValueError("PR_READY evidence requires at least one persisted artifact")
        artifact_paths = [artifact.path for artifact in artifacts]
        if evidence.artifact_paths:
            missing = sorted(set(evidence.artifact_paths) - set(artifact_paths))
            if missing:
                raise ValueError(f"PR_READY evidence references unknown artifact paths: {missing}")
            artifact_paths = evidence.artifact_paths

        return evidence.model_copy(
            update={
                "artifact_paths": artifact_paths,
                "branch_name": evidence.branch_name or task_run.branch_name,
                "worktree_path": evidence.worktree_path or task_run.worktree_path,
            }
        )

    async def _validate_pr_ready_handoff(self, evidence: domain.PRReadyEvidence) -> None:
        result = await self.session.execute(
            select(HandoffORM).where(HandoffORM.id == evidence.handoff_id)
        )
        handoff = result.scalar_one_or_none()
        if handoff is None:
            raise ValueError("PR_READY evidence references unknown handoff")
        if handoff.task_run_id != evidence.task_run_id:
            raise ValueError("PR_READY evidence handoff does not belong to task run")
        if HandoffKind(handoff.kind) != HandoffKind.PR_READY:
            raise ValueError("PR_READY evidence handoff kind must be PR_READY")

    async def _validate_pr_ready_commit_binding(
        self, task_id: int, evidence: domain.PRReadyEvidence
    ) -> None:
        task = await self.get_task(task_id)
        metadata = dict(task.metadata or {}) if task else {}
        expected_source = metadata.get("current_source_commit") or metadata.get("source_commit")
        expected_target = metadata.get("current_target_commit") or metadata.get("target_commit")
        if expected_source is not None and str(expected_source) != evidence.source_commit:
            raise ValueError("PR_READY evidence source_commit is stale")
        if expected_target is not None and str(expected_target) != evidence.target_commit:
            raise ValueError("PR_READY evidence target_commit is stale")

        result = await self.session.execute(
            select(WorktreeAttemptManifestORM)
            .where(WorktreeAttemptManifestORM.task_run_id == evidence.task_run_id)
            .order_by(WorktreeAttemptManifestORM.updated_at.desc())
        )
        manifest = result.scalars().first()
        if manifest:
            if manifest.task_id != task_id:
                raise ValueError("PR_READY evidence worktree manifest does not belong to task")
            if manifest.branch_name != evidence.branch_name:
                raise ValueError("PR_READY evidence branch_name does not match worktree manifest")
            if manifest.source_commit != evidence.source_commit:
                raise ValueError("PR_READY evidence source_commit does not match worktree manifest")

    async def update_task(self, task: domain.Task) -> domain.Task:
        """Update general task fields (except status validation)."""
        if not task.id:
            raise ValueError("Cannot update a task without an ID")

        result = await self.session.execute(
            select(TaskORM)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskORM.id == task.id, ProjectORM.tenant_id == self._tenant_id())
        )
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Task with ID {task.id} not found")

        orm_obj.epic_id = task.epic_id
        orm_obj.title = task.title
        orm_obj.description = task.description
        orm_obj.acceptance_criteria = task.acceptance_criteria
        orm_obj.dependency_task_ids = task.dependency_task_ids
        orm_obj.risk_level = task.risk_level
        orm_obj.assigned_agent_id = task.assigned_agent_id
        orm_obj.metadata_json = task.metadata
        orm_obj.updated_at = task.updated_at

        # If status is modified, trigger state validation
        if orm_obj.status != task.status.value:
            await self.update_task_status(task.id, task.status)

        await self.session.flush()
        return orm_obj.to_domain()

    # Task Run Operations
    async def create_task_run(self, task_run: domain.TaskRun) -> domain.TaskRun:
        """Record the start of a task execution run."""
        if await self.get_task(task_run.task_id) is None:
            raise ValueError("Task run task is not accessible in the current tenant")
        orm_obj = TaskRunORM.from_domain(task_run)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_task_run(self, task_run_id: int) -> domain.TaskRun | None:
        """Retrieve task run by ID."""
        result = await self.session.execute(
            select(TaskRunORM)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskRunORM.id == task_run_id, ProjectORM.tenant_id == self._tenant_id())
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_runs_for_task(self, task_id: int) -> list[domain.TaskRun]:
        """List all execution runs for a specific task."""
        result = await self.session.execute(
            select(TaskRunORM)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskRunORM.task_id == task_id, ProjectORM.tenant_id == self._tenant_id())
            .order_by(TaskRunORM.id.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def list_runs_for_tasks(self, task_ids: list[int]) -> dict[int, list[domain.TaskRun]]:
        """List execution runs for several tasks using a single query."""
        if not task_ids:
            return {}
        result = await self.session.execute(
            select(TaskRunORM)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskRunORM.task_id.in_(task_ids), ProjectORM.tenant_id == self._tenant_id())
            .order_by(TaskRunORM.task_id, TaskRunORM.id.desc())
        )
        runs_by_task: dict[int, list[domain.TaskRun]] = {}
        for orm_obj in result.scalars().all():
            runs_by_task.setdefault(orm_obj.task_id, []).append(orm_obj.to_domain())
        return runs_by_task

    async def list_runs_for_run(self, run_id: int) -> list[domain.TaskRun]:
        """List all task runs belonging to a single execution run."""
        result = await self.session.execute(
            select(TaskRunORM)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskRunORM.run_id == run_id, ProjectORM.tenant_id == self._tenant_id())
            .order_by(TaskRunORM.started_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_task_run(self, task_run: domain.TaskRun) -> domain.TaskRun:
        """Update a task run's status or details."""
        if not task_run.id:
            raise ValueError("Cannot update a task run without an ID")

        result = await self.session.execute(
            select(TaskRunORM)
            .join(TaskORM, TaskORM.id == TaskRunORM.task_id)
            .join(ProjectORM, ProjectORM.id == TaskORM.project_id)
            .where(TaskRunORM.id == task_run.id, ProjectORM.tenant_id == self._tenant_id())
        )
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"TaskRun with ID {task_run.id} not found")

        orm_obj.status = task_run.status.value
        orm_obj.worktree_path = task_run.worktree_path
        orm_obj.branch_name = task_run.branch_name
        orm_obj.sandbox_id = task_run.sandbox_id
        orm_obj.attempt_count = task_run.attempt_count
        orm_obj.heartbeat_at = task_run.heartbeat_at
        orm_obj.ended_at = task_run.ended_at
        orm_obj.final_summary = task_run.final_summary

        await self.session.flush()
        return orm_obj.to_domain()

    async def is_task_runnable(self, task_id: int, project_tasks: list[domain.Task]) -> bool:
        """Verify if a task is runnable based on its dependencies.

        A task is runnable only when all its dependency task IDs are in DONE or PR_READY.
        If a dependency is BLOCKED, FAILED_SAFE, or CANCELLED,
        this task itself transitions to BLOCKED.
        """
        task = next((t for t in project_tasks if t.id == task_id), None)
        if not task:
            task = await self.get_task(task_id)
            if not task:
                return False

        if not task.dependency_task_ids:
            return True

        tasks_by_id = {t.id: t for t in project_tasks if t.id is not None}

        for dep_id in task.dependency_task_ids:
            dep = tasks_by_id.get(dep_id)
            if not dep:
                dep = await self.get_task(dep_id)
                if not dep:
                    return False

            if dep.status in (TaskStatus.FAILED_SAFE, TaskStatus.CANCELLED, TaskStatus.BLOCKED):
                if task.status != TaskStatus.BLOCKED:
                    assert task.id is not None
                    await self.update_task_status(task.id, TaskStatus.BLOCKED)
                return False

            if dep.status not in (TaskStatus.DONE, TaskStatus.PR_READY):
                return False

        return True
