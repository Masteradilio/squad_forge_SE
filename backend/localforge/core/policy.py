import os

import yaml
from pydantic import BaseModel, Field, ValidationError


class PolicyRules(BaseModel):
    name: str = Field(default="default_policy")
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=list)
    approval_required_patterns: list[str] = Field(default_factory=list)
    max_repair_attempts: int = Field(default=3, ge=0)
    max_files_touched: int = Field(default=10, ge=1)
    max_run_duration: int | None = Field(default=None, ge=1)  # in minutes
    allowed_directories: list[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    version: int = Field(default=1)
    policy: PolicyRules = Field(default_factory=PolicyRules)


def load_policy(policy_path: str) -> PolicyConfig:
    """Load and validate policy file from disk.

    Raises ValueError with formatting errors if parsing or validation fails.
    """
    if not os.path.exists(policy_path):
        raise FileNotFoundError(f"Policy file not found at: {policy_path}")

    try:
        with open(policy_path, encoding="utf-8") as f:
            file_data = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse policy YAML file at {policy_path}: {e}") from e

    if not isinstance(file_data, dict):
        raise ValueError(f"Invalid policy structure at {policy_path}: Expected YAML dictionary.")

    try:
        return PolicyConfig.model_validate(file_data)
    except ValidationError as e:
        # Generate clean error message
        errors = []
        for err in e.errors():
            loc = " -> ".join(str(loc) for loc in err["loc"])
            errors.append(f"Field '{loc}': {err['msg']}")
        raise ValueError("Policy validation failed:\n" + "\n".join(errors)) from e
