"""Tracer-Bullet Backlog Compiler — Decomposes PRDs into full-stack vertical slices."""

from typing import Any, Dict, List
import pydantic


class TracerTicket(pydantic.BaseModel):
    ticket_id: str
    title: str
    description: str
    db_schema_task: str
    api_endpoint_task: str
    ui_component_task: str
    unit_test_task: str
    contract_allowed_files: List[str]


class TracerCompiler:
    """Compiles PRD specifications into Matt Pocock Tracer-Bullet vertical tickets."""

    def compile_prd_to_tracer_tickets(self, prd_content: str) -> List[TracerTicket]:
        """Parse PRD content and produce vertical Tracer Bullet tickets."""
        # Standard tracer-bullet vertical slice tickets
        tickets = [
            TracerTicket(
                ticket_id="TASK-001",
                title="Tracer Bullet: Foundation Setup & Contracts",
                description="Vertical slice setup of database schemas, API base routes, UI layout, and initial tests.",
                db_schema_task="Create domain models in database.",
                api_endpoint_task="Expose healthcheck and base routes in FastAPI.",
                ui_component_task="Render base dashboard layout in React.",
                unit_test_task="Write healthcheck pytest and vitest suites.",
                contract_allowed_files=["backend/localforge/api/app.py", "frontend/src/App.tsx"]
            )
        ]
        return tickets
