import asyncio
import asyncio
import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from localforge.llm.base import BaseLLMProvider, LLMError, LLMMessage, LLMTimeoutError

# Type variable for Pydantic models
T = TypeVar("T", bound=BaseModel)


def clean_json_str(content: str) -> str:
    """Extract and clean raw JSON substring out of LLM response.

    Strips markdown formatting blocks (e.g. ```json ... ```) and ignores
    trailing commentary or a second JSON object emitted by weaker models.
    """
    content = content.strip()
    # Try to find content within backticks
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
    start = content.find("{")
    if start >= 0:
        candidate = content[start:]
        try:
            _, end = json.JSONDecoder().raw_decode(candidate)
        except json.JSONDecodeError:
            return content
        return candidate[:end]
    return content


async def chat_completion_validated(  # noqa: UP047
    provider: BaseLLMProvider,
    messages: list[LLMMessage],
    schema_model: type[T],
    max_retries: int = 1,
    timeout: float = 30.0,
    model: str | None = None,
    stream: bool | None = None,
) -> T:
    """Execute a chat completion request and enforce validation of the output.

    If validation or parsing fails, requests a self-repair attempt from the
    model.
    """
    local_messages = list(messages)  # Copy to avoid side-effects on input list
    schema = schema_model.model_json_schema()
    use_gateway_stream = (
        str(getattr(provider, "provider_name", "")).lower() == "omniroute"
        if stream is None
        else stream
    )

    for attempt in range(max_retries + 1):
        try:
            raw_response = await asyncio.wait_for(
                provider.chat_completion(
                    messages=local_messages,
                    response_schema=schema,
                    stream=use_gateway_stream,
                    timeout=timeout,
                    model=model,
                ),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise LLMTimeoutError(
                f"Structured completion call timed out after {timeout}s"
            ) from exc

        if not isinstance(raw_response, str):
            async def consume_stream(stream_response=raw_response) -> tuple[T | None, str]:
                chunks: list[str] = []
                try:
                    async for chunk in stream_response:
                        chunks.append(chunk)
                        candidate = clean_json_str("".join(chunks))
                        try:
                            return schema_model.model_validate(json.loads(candidate, strict=False)), ""
                        except (json.JSONDecodeError, ValidationError):
                            continue
                finally:
                    close = getattr(stream_response, "aclose", None)
                    if callable(close):
                        await close()
                return None, "".join(chunks)

            try:
                streamed_result, streamed_content = await asyncio.wait_for(
                    consume_stream(), timeout=timeout
                )
            except TimeoutError as exc:
                raise LLMTimeoutError(
                    f"Structured stream completion call timed out after {timeout}s"
                ) from exc
            if streamed_result is not None:
                return streamed_result
            raw_response = streamed_content

        cleaned = clean_json_str(raw_response)

        try:
            # Some gateway routes escape JSON correctly except for literal
            # control characters inside a generated code string. Pydantic
            # still validates the schema; accepting those characters here
            # avoids discarding an otherwise complete Chief artifact.
            parsed = json.loads(cleaned, strict=False)
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
            local_messages.append({"role": "assistant", "content": raw_response[:4000]})

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
