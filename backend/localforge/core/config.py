import os
from typing import Any

import yaml
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
        "default_model": "llama3",
        "roles": {},
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
    default_model: str = Field(default="llama3")
    roles: dict[str, str] = Field(default_factory=dict)


class LocalForgeConfig(BaseModel):
    version: int = Field(default=1)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)


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

    # 2. Load from Environment Variables
    env_mappings = {
        "LOCALFORGE_PROJECT_NAME": ("project", "name"),
        "LOCALFORGE_DEFAULT_BRANCH": ("git", "default_branch"),
        "LOCALFORGE_REMOTE_URL": ("git", "remote_url"),
        "LOCALFORGE_MODEL_PROVIDER": ("models", "provider"),
        "LOCALFORGE_MODEL_BASE_URL": ("models", "base_url"),
        "LOCALFORGE_DEFAULT_MODEL": ("models", "default_model"),
    }
    for env_var, path in env_mappings.items():
        val = os.getenv(env_var)
        if val is not None:
            section, key = path
            config_dict[section][key] = val

    # 3. Load from CLI arguments
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

    # 4. Validate with Pydantic
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
