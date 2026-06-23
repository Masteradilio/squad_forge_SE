from enum import StrEnum

from localforge.models.enums import AgentRole


class PipelineMode(StrEnum):
    FAST = "fast"
    DEFAULT = "default"
    STRICT = "strict"


PIPELINES: dict[PipelineMode, tuple[AgentRole, ...]] = {
    PipelineMode.FAST: (
        AgentRole.CODER,
        AgentRole.TESTER,
        AgentRole.REVIEWER,
        AgentRole.PR_WRITER,
    ),
    PipelineMode.DEFAULT: (
        AgentRole.PLANNER,
        AgentRole.SPECIFIER,
        AgentRole.CODER,
        AgentRole.TESTER,
        AgentRole.FIXER,
        AgentRole.REVIEWER,
        AgentRole.PR_WRITER,
    ),
    PipelineMode.STRICT: (
        AgentRole.PLANNER,
        AgentRole.SPECIFIER,
        AgentRole.CODER,
        AgentRole.CLEANER,
        AgentRole.ARCHITECT,
        AgentRole.HARDENER,
        AgentRole.QA,
        AgentRole.PR_WRITER,
    ),
}
