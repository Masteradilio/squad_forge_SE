from localforge.llm.base import BaseLLMProvider
from localforge.llm.validator import chat_completion_validated
from localforge.prd.schemas import ExtractedPlan


async def generate_model_assisted_plan(
    provider: BaseLLMProvider,
    markdown: str,
    *,
    model: str | None = None,
) -> ExtractedPlan:
    messages = [
        {
            "role": "system",
            "content": (
                "Extract small software engineering epics and tasks from the PRD. "
                "Return only structured JSON matching the schema. For each task, preserve "
                "explicit file paths in expected_files. Put explicitly stated contract facts "
                "in metadata keys depends_on, required_public_apis, forbidden_dependencies, "
                "and implementation_notes. Use lists of strings and leave a field empty when "
                "the PRD does not support it; do not invent benchmark- or domain-specific APIs."
            ),
        },
        {"role": "user", "content": markdown},
    ]
    return await chat_completion_validated(
        provider,
        messages,
        ExtractedPlan,
        max_retries=1,
        model=model,
    )
