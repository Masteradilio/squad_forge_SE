import json
import sys
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, model_validator


class RuntimeActionProposal(BaseModel):
    kind: Literal["write_file", "append_content", "run_command"]
    path: str | None = None
    content: str = ""
    command: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_model_aliases(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "kind" not in normalized:
            for alias in ("operation", "action", "type"):
                if alias in normalized:
                    normalized["kind"] = normalized[alias]
                    break
        if normalized.get("kind") in {
            "write_content",
            "create_file",
            "update_file",
            "replace_file",
            "edit_file",
            "patch_file",
            "modify_file",
            "edit",
        }:
            normalized["kind"] = "write_file"
        if normalized.get("kind") in {"command", "shell", "exec", "execute"}:
            normalized["kind"] = "run_command"
        if normalized.get("kind") == "run_command" and "command" not in normalized:
            for alias in ("cmd", "shell_command"):
                if alias in normalized:
                    normalized["command"] = normalized[alias]
                    break
        if "path" not in normalized:
            for alias in ("file", "filename", "file_path"):
                if alias in normalized:
                    normalized["path"] = normalized[alias]
                    break
        if "content" not in normalized:
            for alias in ("code", "body", "text"):
                if alias in normalized:
                    normalized["content"] = normalized[alias]
                    break
        return normalized


def parse_action_proposals(raw: object) -> list[RuntimeActionProposal]:
    """Parse local-model JSON action proposals without executing them."""
    if isinstance(raw, str):
        raw = _loads_action_payload(raw)
    if isinstance(raw, dict):
        if "actions" in raw:
            raw = raw["actions"]
        elif any(key in raw for key in ("kind", "operation", "action", "type")):
            raw = [raw]
        else:
            raw = []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("Runtime action proposal must be a list or {'actions': [...]} payload.")

    proposals: list[RuntimeActionProposal] = []
    for item in raw:
        if isinstance(item, str):
            try:
                decoded = json.loads(item)
                if isinstance(decoded, dict):
                    item = decoded
            except Exception:
                pass
        if not isinstance(item, dict):
            continue
        norm_item = RuntimeActionProposal.normalize_model_aliases(item)
        if isinstance(norm_item, dict):
            item = norm_item
        kind_val = str(item.get("kind") or item.get("action") or item.get("type") or "").lower()
        if kind_val in {"noop", "no_op", "none"}:
            continue

        if kind_val not in ("write_file", "append_content", "run_command"):
            if item.get("command"):
                item["kind"] = "run_command"
            elif item.get("path") or item.get("file") or item.get("filename"):
                item["kind"] = "write_file"
            else:
                continue

        try:
            proposal = RuntimeActionProposal.model_validate(item)
        except ValidationError as exc:
            raise ValueError(f"Invalid runtime action proposal: {exc}") from exc
        if proposal.kind in ("write_file", "append_content") and not proposal.path:
            raise ValueError(f"{proposal.kind} action requires path.")
        if proposal.kind == "run_command" and not proposal.command:
            raise ValueError("run_command action requires command.")
        proposals.append(proposal)
    return proposals


def _loads_action_payload(raw: str) -> object:
    import re

    # Clean the raw string first
    cleaned = raw.strip()
    # Strip markdown code fences if present
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()

    # Fix trailing commas in objects and arrays
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to balance and close truncated JSON
        try:
            open_braces = 0
            open_brackets = 0
            in_string = False
            escape = False
            clean_chars = []
            for char in cleaned:
                if escape:
                    clean_chars.append(char)
                    escape = False
                    continue
                if char == "\\":
                    clean_chars.append(char)
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    clean_chars.append(char)
                    continue
                if not in_string:
                    if char == "{":
                        open_braces += 1
                    elif char == "}":
                        if open_braces > 0:
                            open_braces -= 1
                        else:
                            continue
                    elif char == "[":
                        open_brackets += 1
                    elif char == "]":
                        if open_brackets > 0:
                            open_brackets -= 1
                        else:
                            continue
                clean_chars.append(char)

            reconstructed = "".join(clean_chars)
            if in_string:
                reconstructed += '"'

            nesting_stack = []
            in_string = False
            escape = False
            for char in reconstructed:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if char in "{[":
                        nesting_stack.append(char)
                    elif char in "}]":
                        matching = "{" if char == "}" else "["
                        if nesting_stack and nesting_stack[-1] == matching:
                            nesting_stack.pop()

            for op in reversed(nesting_stack):
                if op == "{":
                    reconstructed += "}"
                elif op == "[":
                    reconstructed += "]"
            return json.loads(reconstructed)
        except Exception:
            pass

    # Fallback to the original raw decode logic
    try:
        return json.loads(raw)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        starts = [index for index, char in enumerate(raw) if char in "[{"]
        for start in starts:
            try:
                payload, _ = decoder.raw_decode(raw[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, (dict, list)):
                return payload
        raise original_error


def proposals_to_metadata(proposals: list[RuntimeActionProposal]) -> list[dict[str, Any]]:
    return [proposal.model_dump(exclude_none=True) for proposal in proposals]


def normalize_runtime_command(command: str) -> str:
    stripped = command.strip()
    if stripped == "pytest":
        return f'"{sys.executable}" -m pytest'
    if stripped.startswith("pytest "):
        return f'"{sys.executable}" -m {stripped}'
    for prefix in ("python -m pytest", "python3 -m pytest"):
        if stripped == prefix:
            return f'"{sys.executable}" -m pytest'
        if stripped.startswith(prefix + " "):
            return f'"{sys.executable}" -m pytest{stripped[len(prefix) :]}'
    return command
