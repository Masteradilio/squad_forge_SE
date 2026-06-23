from dataclasses import dataclass

from localforge.core.config import load_config
from localforge.models import domain
from localforge.models.enums import AgentRole
from localforge.skills import SkillRegistry
from localforge.storage import UnitOfWork

ROLE_RESPONSIBILITIES: dict[AgentRole, str] = {
    AgentRole.PLANNER: "Define execution plan and sequencing.",
    AgentRole.SPECIFIER: "Clarify acceptance criteria and edge cases.",
    AgentRole.CODER: "Produce implementation evidence and changed-file summary.",
    AgentRole.CLEANER: "Reduce unnecessary churn and verify maintainability.",
    AgentRole.TESTER: "Define targeted verification and test evidence.",
    AgentRole.FIXER: "Summarize repair decisions after test feedback.",
    AgentRole.REVIEWER: "Review risks, regressions, and readiness.",
    AgentRole.ARCHITECT: "Check architectural fit and dependency boundaries.",
    AgentRole.HARDENER: "Check security and operational hardening.",
    AgentRole.QA: "Confirm release-quality acceptance evidence.",
    AgentRole.PR_WRITER: "Prepare PR-ready summary and checklist.",
    AgentRole.SAFETY_AUDITOR: "Validate sensitive actions and policy compliance.",
}


@dataclass(frozen=True)
class RoleContext:
    role: AgentRole
    model_profile_id: str
    rendered: str
    consumed_handoffs: list[domain.Handoff]


class RoleContextBuilder:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def build(
        self,
        *,
        project: domain.Project,
        task: domain.Task,
        task_run: domain.TaskRun,
        role: AgentRole,
        consumed_handoffs: list[domain.Handoff],
    ) -> RoleContext:
        assert self.uow.routing is not None
        model_profile_id = (
            await self.uow.routing.get_model_for_role(project.id or 0, role)
            or _configured_model_for_role(role)
        )
        selected_skills = SkillRegistry(project.root_path).select_for_task(task)
        relevant_memory: list[domain.MemoryFact] = []
        if self.uow.memory is not None:
            relevant_memory = await self.uow.memory.retrieve_relevant(
                task.project_id,
                query=f"{role.value} {task.key} {task.title} {task.description}",
            )
        recent_comments: list[domain.TaskComment] = []
        if self.uow.coordination is not None and task.id is not None:
            recent_comments = await self.uow.coordination.recent_comments_for_context(
                task.id,
                limit=5,
            )
        handoff_lines = [
            f"- {handoff.from_role.value}->{handoff.to_role.value}: "
            f"{handoff.kind.value} priority={handoff.priority}"
            for handoff in consumed_handoffs
        ]
        comment_lines = [
            f"- {comment.author}: {comment.body[:300]}"
            for comment in recent_comments
        ]
        contract_lines = _render_task_contract(task)
        rendered = "\n".join(
            [
                f"Role: {role.value}",
                f"Model: {model_profile_id}",
                f"Responsibility: {ROLE_RESPONSIBILITIES.get(role, 'Execute assigned role.')}",
                f"Task: {task.key} {task.title}",
                f"Description: {task.description}",
                f"Acceptance: {'; '.join(task.acceptance_criteria) or 'not specified'}",
                f"Risk: {task.risk_level}",
                f"Branch: {task_run.branch_name or 'pending'}",
                "Selected skills:",
                *([f"- {skill.name}: {skill.purpose}" for skill in selected_skills] or ["- none"]),
                "Relevant memory:",
                *([f"- {fact.kind.value}: {fact.fact}" for fact in relevant_memory] or ["- none"]),
                "Recent comments:",
                *(comment_lines or ["- none"]),
                "Consumed handoffs:",
                *(handoff_lines or ["- none"]),
                "Task contract:",
                *(contract_lines or ["- none"]),
            ]
        )
        return RoleContext(
            role=role,
            model_profile_id=model_profile_id,
            rendered=rendered,
            consumed_handoffs=consumed_handoffs,
        )


def _configured_model_for_role(role: AgentRole) -> str:
    try:
        config = load_config()
    except Exception:
        return f"{role.value.lower()}-local"
    return (
        config.models.roles.get(role.value)
        or config.models.default_model
        or f"{role.value.lower()}-local"
    )


def _render_task_contract(task: domain.Task) -> list[str]:
    contract = task.metadata.get("task_contract")
    if not isinstance(contract, dict):
        return []
    lines: list[str] = []
    for key in (
        "allowed_files",
        "required_public_apis",
        "forbidden_dependencies",
        "canonical_test_command",
        "risk_level",
        "implementation_notes",
    ):
        value = contract.get(key)
        if value:
            lines.append(f"- {key}: {value}")
    return lines
