import os
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError

# Default configuration dictionary used as baseline
DEFAULT_CONFIG = {
    "version": 1,
    "project": {
        "name": "Default Project",
    },
    "git": {
        "default_branch": "main",
        "remote_url": None,
    },
    "models": {
        "provider": "ollama",
        "base_url": "http://localhost:11434/v1",
        "default_model": "gemma4:12b",
        "fallback_models": ["granite4.1:8b", "nemotron-3-nano:4b"],
        "roles": {},
    },
    "chief_engineer": {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": None,
        "api_key": None,
        "fallback_provider": None,
        "fallback_base_url": None,
        "fallback_model": None,
        "fallback_api_key": None,
        "fallback_after_seconds": 30.0,
        "timeout": 240.0,
        "max_input_tokens_per_call": 32000,
        "max_output_tokens_per_call": 8000,
    },
    "sandbox": {
        "type": "local",
        "image": "python:3.12-slim",
        "network_enabled": False,
    },
    "budgets": {
        "max_run_time": 5400.0,
        "max_task_duration": 900.0,
        "max_repair_attempts": 5,
        "max_parallel_tasks": 2,
        "max_active_model_calls": 4,
        "max_diff_growth": 4000,
        "max_file_count": 12,
        "max_paid_calls": 30,
        "max_paid_input_tokens": 400000,
        "max_paid_output_tokens": 60000,
        "max_paid_usd": 4.0,
        "max_repair_attempts_absolute": 10,
        "max_run_recovery_cycles": 3,
        "max_paid_usd_absolute": 6.0,
    },
}

class ProjectConfig(BaseModel):
    name: str = Field(default="Default Project")


class GitConfig(BaseModel):
    default_branch: str = Field(default="main")
    remote_url: str | None = Field(default=None)


class ModelsConfig(BaseModel):
    provider: str = Field(default="ollama")
    base_url: str = Field(default="http://localhost:11434/v1")
    default_model: str = Field(default="gemma4:12b")
    fallback_models: list[str] = Field(
        default_factory=lambda: ["granite4.1:8b", "nemotron-3-nano:4b"]
    )
    roles: dict[str, str] = Field(default_factory=dict)


class ChiefEngineerConfig(BaseModel):
    provider: str = Field(default="openrouter")
    base_url: str = Field(default="https://openrouter.ai/api/v1")
    model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    fallback_provider: str | None = Field(default=None)
    fallback_base_url: str | None = Field(default=None)
    fallback_model: str | None = Field(default=None)
    fallback_api_key: str | None = Field(default=None)
    fallback_after_seconds: float = Field(default=30.0)
    enabled: bool = Field(default=True)
    timeout: float = Field(default=240.0)
    max_input_tokens_per_call: int = Field(default=32000)
    max_output_tokens_per_call: int = Field(default=8000)


class SandboxConfig(BaseModel):
    type: str = Field(default="local")
    image: str = Field(default="python:3.12-slim")
    network_enabled: bool = Field(default=False)

class BudgetsConfig(BaseModel):
    max_run_time: float = Field(default=5400.0)
    max_task_duration: float = Field(default=900.0)
    max_repair_attempts: int = Field(default=5)
    max_parallel_tasks: int = Field(default=2)
    max_active_model_calls: int = Field(default=4)
    max_diff_growth: int = Field(default=4000)
    max_file_count: int = Field(default=12)
    max_paid_calls: int = Field(default=30)
    max_paid_input_tokens: int = Field(default=400000)
    max_paid_output_tokens: int = Field(default=60000)
    max_paid_usd: float = Field(default=4.0)
    # Absolute ceilings enforced by the scheduler recovery loop:
    max_repair_attempts_absolute: int = Field(default=10)
    max_run_recovery_cycles: int = Field(default=3)
    max_paid_usd_absolute: float = Field(default=6.0)


class LocalForgeConfig(BaseModel):
    version: int = Field(default=1)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    chief_engineer: ChiefEngineerConfig = Field(default_factory=ChiefEngineerConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)


def _find_env_file(start_dir: str) -> str | None:
    curr = start_dir
    while True:
        candidate = os.path.join(curr, ".env")
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent
    return None


def load_config(cli_args: dict[str, Any] | None = None) -> LocalForgeConfig:
    """Load configuration with the following precedence order:

    1. CLI flags (passed as cli_args dict)
    2. Environment variables prefixed with LOCALFORGE_
    3. Workspace configuration file (.localforge/config.yaml)
    4. Default settings
    """
    # Start with baseline defaults
    config_dict = copy_dict_structure(DEFAULT_CONFIG)

    # 1. Load from .localforge/config.yaml if it exists
    cwd = os.getcwd()
    config_path = os.path.join(cwd, ".localforge", "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                file_data = yaml.safe_load(f)
                if isinstance(file_data, dict):
                    merge_dicts(config_dict, file_data)
        except Exception as e:
            raise ValueError(f"Failed to parse workspace config file at {config_path}: {e}") from e

    # 2. Load from .env without mutating process environment or logging secrets.
    env_file_path = _find_env_file(cwd)
    if env_file_path and os.path.exists(env_file_path):
        env_file_values = dotenv_values(env_file_path)
        if env_file_values.get("NVIDIA_LLM_MODEL") and env_file_values.get("NVIDIA_API_KEY"):
            config_dict["chief_engineer"]["provider"] = "nvidia"
            config_dict["chief_engineer"]["base_url"] = "https://integrate.api.nvidia.com/v1"
            config_dict["chief_engineer"]["model"] = env_file_values["NVIDIA_LLM_MODEL"]
            config_dict["chief_engineer"]["api_key"] = env_file_values["NVIDIA_API_KEY"]
            if env_file_values.get("OPENROUTER_MODEL") and env_file_values.get("OPENROUTER_API_KEY"):
                config_dict["chief_engineer"]["fallback_provider"] = "openrouter"
                config_dict["chief_engineer"]["fallback_base_url"] = "https://openrouter.ai/api/v1"
                config_dict["chief_engineer"]["fallback_model"] = env_file_values["OPENROUTER_MODEL"]
                config_dict["chief_engineer"]["fallback_api_key"] = env_file_values["OPENROUTER_API_KEY"]
        else:
            if env_file_values.get("OPENROUTER_MODEL"):
                config_dict["chief_engineer"]["model"] = env_file_values["OPENROUTER_MODEL"]
            if env_file_values.get("OPENROUTER_API_KEY"):
                config_dict["chief_engineer"]["api_key"] = env_file_values["OPENROUTER_API_KEY"]

    # 3. Load from Environment Variables
    env_mappings = {
        "LOCALFORGE_PROJECT_NAME": ("project", "name"),
        "LOCALFORGE_DEFAULT_BRANCH": ("git", "default_branch"),
        "LOCALFORGE_REMOTE_URL": ("git", "remote_url"),
        "LOCALFORGE_MODEL_PROVIDER": ("models", "provider"),
        "LOCALFORGE_MODEL_BASE_URL": ("models", "base_url"),
        "LOCALFORGE_DEFAULT_MODEL": ("models", "default_model"),
        "NVIDIA_LLM_MODEL": ("chief_engineer", "model"),
        "NVIDIA_API_KEY": ("chief_engineer", "api_key"),
        "OPENROUTER_MODEL": ("chief_engineer", "model"),
        "OPENROUTER_API_KEY": ("chief_engineer", "api_key"),
    }
    for env_var, path in env_mappings.items():
        val = os.getenv(env_var)
        if val is not None:
            section, key = path
            if env_var.startswith("NVIDIA_"):
                config_dict["chief_engineer"]["provider"] = "nvidia"
                config_dict["chief_engineer"]["base_url"] = "https://integrate.api.nvidia.com/v1"
            config_dict[section][key] = val
    nvidia_model = os.getenv("NVIDIA_LLM_MODEL")
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if nvidia_model and nvidia_key:
        config_dict["chief_engineer"]["provider"] = "nvidia"
        config_dict["chief_engineer"]["base_url"] = "https://integrate.api.nvidia.com/v1"
        config_dict["chief_engineer"]["model"] = nvidia_model
        config_dict["chief_engineer"]["api_key"] = nvidia_key
        if os.getenv("OPENROUTER_MODEL") and os.getenv("OPENROUTER_API_KEY"):
            config_dict["chief_engineer"]["fallback_provider"] = "openrouter"
            config_dict["chief_engineer"]["fallback_base_url"] = "https://openrouter.ai/api/v1"
            config_dict["chief_engineer"]["fallback_model"] = os.environ["OPENROUTER_MODEL"]
            config_dict["chief_engineer"]["fallback_api_key"] = os.environ["OPENROUTER_API_KEY"]

    # 4. Load from CLI arguments
    if cli_args:
        cli_mappings = {
            "project_name": ("project", "name"),
            "default_branch": ("git", "default_branch"),
            "remote_url": ("git", "remote_url"),
            "model_provider": ("models", "provider"),
            "model_base_url": ("models", "base_url"),
            "default_model": ("models", "default_model"),
        }
        for arg_key, path in cli_mappings.items():
            val = cli_args.get(arg_key)
            if val is not None:
                section, key = path
                config_dict[section][key] = val

    # 5. Validate with Pydantic
    try:
        return LocalForgeConfig.model_validate(config_dict)
    except ValidationError as e:
        # Generate clean error message
        errors = []
        for err in e.errors():
            loc = " -> ".join(str(loc) for loc in err["loc"])
            errors.append(f"Field '{loc}': {err['msg']}")
        raise ValueError("Configuration validation failed:\n" + "\n".join(errors)) from e


def copy_dict_structure(d: dict[str, Any]) -> dict[str, Any]:
    """Helper to perform deep copies of nested dictionaries."""
    res = {}
    for k, v in d.items():
        if isinstance(v, dict):
            res[k] = copy_dict_structure(v)
        else:
            res[k] = v
    return res


def merge_dicts(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Helper to deeply merge source dict into target dict."""
    for k, v in source.items():
        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            merge_dicts(target[k], v)
        else:
            target[k] = v
