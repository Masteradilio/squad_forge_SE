import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from localforge.llm.base import BaseLLMProvider, LLMError

# Type variable for Pydantic models
T = TypeVar("T", bound=BaseModel)


def clean_json_str(content: str) -> str:
    """Extract and clean raw JSON substring out of LLM response.

    Strips markdown formatting blocks (e.g. ```json ... ```).
    """
    content = content.strip()
    # Try to find content within backticks
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return content


async def chat_completion_validated(  # noqa: UP047
    provider: BaseLLMProvider,
    messages: list[dict[str, str]],
    schema_model: type[T],
    max_retries: int = 1,
    timeout: float = 30.0,
    model: str | None = None,
) -> T:
    """Execute a chat completion request and enforce validation of the output.

    If validation or parsing fails, requests a self-repair attempt from the
    model.
    """
    local_messages = list(messages)  # Copy to avoid side-effects on input list
    schema = schema_model.model_json_schema()

    for attempt in range(max_retries + 1):
        raw_response = await provider.chat_completion(
            messages=local_messages,
            response_schema=schema,
            stream=False,
            timeout=timeout,
            model=model,
        )

        # We only expect non-streaming results for structured validation
        if not isinstance(raw_response, str):
            raise LLMError("Structured validation calls do not support streaming response mode.")

        cleaned = clean_json_str(raw_response)

        try:
            parsed = json.loads(cleaned)
            return schema_model.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            if attempt >= max_retries:
                # Exhausted all attempts
                error_msg = f"Failed to validate LLM output after {max_retries} retries."
                if isinstance(e, ValidationError):
                    # Format Pydantic validation errors nicely
                    err_details = []
                    for err in e.errors():
                        loc = " -> ".join(str(loc_val) for loc_val in err["loc"])
                        err_details.append(f"Field '{loc}': {err['msg']}")
                    details_str = "; ".join(err_details)
                else:
                    details_str = str(e)
                raise ValueError(f"{error_msg} Details: {details_str}") from e

            # Append the failed output and the repair instructions to the message history
            local_messages.append({"role": "assistant", "content": raw_response})

            is_json_err = isinstance(e, json.JSONDecodeError)
            error_type = "JSON formatting error" if is_json_err else "Schema validation error"
            repair_prompt = (
                f"Your previous response had a {error_type}: {e}.\n"
                f"Please correct the response and return ONLY valid JSON conforming strictly "
                f"to the following JSON Schema:\n{json.dumps(schema, indent=2)}"
            )
            local_messages.append({"role": "user", "content": repair_prompt})

    # Fallback exception (should not be reached)
    raise LLMError("Structured validation failed due to retry logic completion error.")
