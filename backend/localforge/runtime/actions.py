import json
import sys
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator


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
    return command
