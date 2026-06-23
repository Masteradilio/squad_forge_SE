from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import AuditEventActorType, AuditEventType, TaskStatus
from localforge.storage.orm import AuditEventORM, EpicORM, TaskORM, TaskRunORM

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
    TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.FAILED_SAFE: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


class TaskService:
    """Service layer for Epic, Task, and TaskRun persistence and state transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

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
        orm_obj = TaskORM.from_domain(task)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_task(self, task_id: int) -> domain.Task | None:
        """Retrieve a task by database ID."""
        result = await self.session.execute(select(TaskORM).where(TaskORM.id == task_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_task_by_key(self, key: str) -> domain.Task | None:
        """Retrieve a task by its unique key (e.g. LF-0101)."""
        result = await self.session.execute(select(TaskORM).where(TaskORM.key == key))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_tasks_for_project(self, project_id: int) -> list[domain.Task]:
        """List all tasks in a project."""
        result = await self.session.execute(
            select(TaskORM).where(TaskORM.project_id == project_id).order_by(TaskORM.created_at)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_task_status(self, task_id: int, new_status: TaskStatus) -> domain.Task:
        """Update the status of a task after validating state transitions."""
        result = await self.session.execute(select(TaskORM).where(TaskORM.id == task_id))
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Task with ID {task_id} not found")

        current_status = TaskStatus(orm_obj.status)

        if current_status == new_status:
            return orm_obj.to_domain()

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

    async def update_task(self, task: domain.Task) -> domain.Task:
        """Update general task fields (except status validation)."""
        if not task.id:
            raise ValueError("Cannot update a task without an ID")

        result = await self.session.execute(select(TaskORM).where(TaskORM.id == task.id))
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
        orm_obj = TaskRunORM.from_domain(task_run)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_task_run(self, task_run_id: int) -> domain.TaskRun | None:
        """Retrieve task run by ID."""
        result = await self.session.execute(select(TaskRunORM).where(TaskRunORM.id == task_run_id))
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_runs_for_task(self, task_id: int) -> list[domain.TaskRun]:
        """List all execution runs for a specific task."""
        result = await self.session.execute(
            select(TaskRunORM)
            .where(TaskRunORM.task_id == task_id)
            .order_by(TaskRunORM.started_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def list_runs_for_tasks(self, task_ids: list[int]) -> dict[int, list[domain.TaskRun]]:
        """List execution runs for several tasks using a single query."""
        if not task_ids:
            return {}
        result = await self.session.execute(
            select(TaskRunORM)
            .where(TaskRunORM.task_id.in_(task_ids))
            .order_by(TaskRunORM.task_id, TaskRunORM.started_at.desc())
        )
        runs_by_task: dict[int, list[domain.TaskRun]] = {}
        for orm_obj in result.scalars().all():
            runs_by_task.setdefault(orm_obj.task_id, []).append(orm_obj.to_domain())
        return runs_by_task

    async def list_runs_for_run(self, run_id: int) -> list[domain.TaskRun]:
        """List all task runs belonging to a single execution run."""
        result = await self.session.execute(
            select(TaskRunORM)
            .where(TaskRunORM.run_id == run_id)
            .order_by(TaskRunORM.started_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_task_run(self, task_run: domain.TaskRun) -> domain.TaskRun:
        """Update a task run's status or details."""
        if not task_run.id:
            raise ValueError("Cannot update a task run without an ID")

        result = await self.session.execute(select(TaskRunORM).where(TaskRunORM.id == task_run.id))
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"TaskRun with ID {task_run.id} not found")

        orm_obj.status = task_run.status.value
        orm_obj.worktree_path = task_run.worktree_path
        orm_obj.branch_name = task_run.branch_name
        orm_obj.sandbox_id = task_run.sandbox_id
        orm_obj.attempt_count = task_run.attempt_count
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
