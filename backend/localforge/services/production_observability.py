"""Production Observability Service and Structured JSON Logging (V61C-1001).

Emits structured JSON log records with correlation/project/task_run/attempt IDs,
tracks platform metrics, and consolidates operator diagnostics.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


class StructuredLogRecord(BaseModel):
    """Canonical structured JSON log record schema."""

    timestamp: str
    level: str
    message: str
    correlation_id: str | None = None
    project_id: int | None = None
    task_run_id: int | None = None
    attempt_id: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class OperatorStatusReport(BaseModel):
    """Unified operator view for platform operability (V61C-1001)."""

    timestamp: str
    status: str  # HEALTHY, DEGRADED, CRITICAL
    active_workers_count: int
    active_leases_count: int
    queue_depth: int
    open_circuit_breakers_count: int
    total_cost_usd: float
    summary: str


def format_structured_log(
    level: str,
    message: str,
    *,
    correlation_id: str | None = None,
    project_id: int | None = None,
    task_run_id: int | None = None,
    attempt_id: int | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Format structured JSON log line with correlation metadata."""
    record = StructuredLogRecord(
        timestamp=datetime.now(UTC).isoformat(),
        level=level.upper(),
        message=message,
        correlation_id=correlation_id,
        project_id=project_id,
        task_run_id=task_run_id,
        attempt_id=attempt_id,
        context=context or {},
    )
    return json.dumps(record.model_dump(mode="json"))


class ProductionObservabilityService:
    """Platform metrics tracking and operator view generation."""

    def __init__(self) -> None:
        self._metrics_store: dict[str, list[float]] = {}

    def record_metric(self, name: str, value: float) -> None:
        """Record quantitative platform metric."""
        self._metrics_store.setdefault(name, []).append(value)

    async def get_operator_status_summary(
        self, uow: UnitOfWork, project_id: int = 1
    ) -> OperatorStatusReport:
        """Consolidate current operator view for active loops, workers, leases, and breakers."""
        active_workers = 0
        active_leases = 0

        if uow.runner_pool is not None:
            try:
                runners = await uow.runner_pool.list_runners()
                active_workers = len(runners)
            except Exception as exc:
                logger.warning("Could not list runners for operator view: %s", exc)

        if uow.path_leases is not None:
            try:
                leases = await uow.path_leases.list_active_leases(project_id)
                active_leases = len(leases)
            except Exception as exc:
                logger.warning("Could not list path leases for operator view: %s", exc)

        breakers_open = 0
        if uow.circuit_breakers is not None:
            try:
                breakers = await uow.circuit_breakers.list_breakers_for_project(project_id)
                breakers_open = sum(1 for b in breakers if str(b.state) == "OPEN")
            except Exception as exc:
                logger.warning("Could not list circuit breakers for operator view: %s", exc)

        queue_depth = 0
        if uow.tasks is not None:
            try:
                from localforge.models.enums import TaskStatus

                tasks = await uow.tasks.list_tasks_for_project(project_id)
                queue_depth = sum(
                    1
                    for task in tasks
                    if task.status in {TaskStatus.BACKLOG, TaskStatus.READY}
                )
            except Exception as exc:
                logger.warning("Could not calculate queue depth for operator view: %s", exc)

        total_cost_usd = 0.0
        if uow.model_calls is not None:
            try:
                calls = await uow.model_calls.list_calls(project_id=project_id)
                total_cost_usd = round(
                    sum(float(call.estimated_cost_usd or 0.0) for call in calls),
                    8,
                )
            except Exception as exc:
                logger.warning("Could not calculate model cost for operator view: %s", exc)

        status = "HEALTHY" if breakers_open == 0 else "DEGRADED"
        if breakers_open and queue_depth > 0:
            status = "CRITICAL"

        return OperatorStatusReport(
            timestamp=datetime.now(UTC).isoformat(),
            status=status,
            active_workers_count=active_workers,
            active_leases_count=active_leases,
            queue_depth=queue_depth,
            open_circuit_breakers_count=breakers_open,
            total_cost_usd=total_cost_usd,
            summary=(
                f"Operator status: {status}. Active workers: {active_workers}, "
                f"active leases: {active_leases}, queue depth: {queue_depth}, "
                f"open circuit breakers: {breakers_open}, cost: ${total_cost_usd:.4f}."
            ),
        )
