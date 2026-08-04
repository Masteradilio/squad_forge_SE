import os
from typing import Any
from urllib.parse import urlsplit

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
        "provider": "omniroute",
        "base_url": "http://localhost:20128/v1",
        "api_key": None,
        "default_model": "auto/best-free",
        "fallback_models": [
            "auto/coding:free",
            "oc/nemotron-3-ultra-free",
            "oc/mimo-v2.5-free",
        ],
        "roles": {},
    },
    "chief_engineer": {
        "provider": "omniroute",
        "base_url": "http://localhost:20128/v1",
        "model": "auto/best-free",
        "api_key": None,
        "fallback_models": [
            "auto/coding:free",
            "oc/nemotron-3-ultra-free",
            "oc/mimo-v2.5-free",
            "oc/north-mini-code-free",
        ],
        "visual_fallback_models": [
            "oc/mimo-v2.5-free",
            "oc/north-mini-code-free",
            "auto/best-free",
        ],
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
        # Visual tasks may replace a complete HTML/CSS document. Keep the
        # ordinary code diff budget strict while allowing one bounded page
        # rewrite to pass through to the visual fidelity gate.
        "max_visual_diff_growth": 100000,
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
    provider: str = Field(default="omniroute")
    base_url: str = Field(default="http://localhost:20128/v1")
    api_key: str | None = Field(default=None)
    default_model: str = Field(default="auto/best-free")
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "auto/coding:free",
            "oc/nemotron-3-ultra-free",
            "oc/mimo-v2.5-free",
        ]
    )
    roles: dict[str, str] = Field(default_factory=dict)


class ChiefEngineerConfig(BaseModel):
    provider: str = Field(default="omniroute")
    base_url: str = Field(default="http://localhost:20128/v1")
    model: str | None = Field(default="auto/best-free")
    visual_model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "auto/coding:free",
            "oc/nemotron-3-ultra-free",
            "oc/mimo-v2.5-free",
            "oc/north-mini-code-free",
        ]
    )
    visual_fallback_models: list[str] = Field(
        default_factory=lambda: [
            "oc/mimo-v2.5-free",
            "oc/north-mini-code-free",
            "auto/best-free",
        ]
    )
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
    cpu_limit: float = Field(default=1.0, gt=0, le=8)
    memory_limit_mb: int = Field(default=1024, gt=64, le=16384)
    pids_limit: int = Field(default=256, gt=16, le=4096)
    read_only_root: bool = Field(default=True)
    egress_allowlist: list[str] = Field(default_factory=list)


class BudgetsConfig(BaseModel):
    max_run_time: float = Field(default=5400.0)
    max_task_duration: float = Field(default=900.0)
    max_repair_attempts: int = Field(default=5)
    max_parallel_tasks: int = Field(default=2)
    max_active_model_calls: int = Field(default=4)
    max_diff_growth: int = Field(default=4000)
    max_visual_diff_growth: int = Field(default=100000)
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


def _validate_omniroute_endpoint(value: str, section: str) -> None:
    """Reject direct provider URLs while keeping private gateway hosts valid.

    Provider names alone are not a sufficient guard: a legacy environment can
    still set ``provider=omniroute`` alongside an OpenRouter or NVIDIA URL.
    ForgeOS Cloud must reach upstream models through the OmniRoute gateway.
    """
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError(f"{section}.base_url must be an HTTP(S) OmniRoute endpoint")

    known_gateway_host = host in {
        "localhost",
        "127.0.0.1",
        "::1",
        "omniroute",
        "forgeos-omniroute",
        "gateway",
    }
    configured_hosts = {
        item.strip().lower()
        for item in os.getenv("LOCALFORGE_OMNIROUTE_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    gateway_named = host.endswith(".omniroute") or host.endswith(".forgeos")
    if not (known_gateway_host or gateway_named or host in configured_hosts):
        raise ValueError(
            f"{section}.base_url must point to the OmniRoute gateway, not public host '{host}'"
        )


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
    env_file_values: dict[str, str | None] = {}
    if env_file_path and os.path.exists(env_file_path):
        # Vendor keys may still exist in legacy workspaces, but ForgeOS Cloud
        # never infers a direct provider from them. Upstreams are configured in
        # and reached exclusively through OmniRoute.
        env_file_values = {
            str(key): value
            for key, value in dotenv_values(env_file_path).items()
            if key is not None
        }

    def env_value(name: str) -> str | None:
        value = os.getenv(name)
        return value if value is not None else env_file_values.get(name)

    # OmniRoute is the only gateway boundary. Support its canonical aliases
    # directly so a .env containing OMNIROUTE_URL/API_KEY cannot be silently
    # ignored by the OpenAI-compatible transport.
    omniroute_url = env_value("OMNIROUTE_URL")
    if omniroute_url:
        config_dict["models"]["base_url"] = omniroute_url
        config_dict["chief_engineer"]["base_url"] = omniroute_url
    omniroute_api_key = env_value("OMNIROUTE_API_KEY")
    if omniroute_api_key:
        config_dict["models"]["api_key"] = omniroute_api_key
        config_dict["chief_engineer"]["api_key"] = omniroute_api_key

    # 3. Load from Environment Variables
    env_mappings = {
        "LOCALFORGE_PROJECT_NAME": ("project", "name"),
        "LOCALFORGE_DEFAULT_BRANCH": ("git", "default_branch"),
        "LOCALFORGE_REMOTE_URL": ("git", "remote_url"),
        "LOCALFORGE_MODEL_PROVIDER": ("models", "provider"),
        "LOCALFORGE_MODEL_BASE_URL": ("models", "base_url"),
        "LOCALFORGE_MODEL_API_KEY": ("models", "api_key"),
        "LOCALFORGE_DEFAULT_MODEL": ("models", "default_model"),
        "LOCALFORGE_SANDBOX_TYPE": ("sandbox", "type"),
        "LOCALFORGE_SANDBOX_IMAGE": ("sandbox", "image"),
        "LOCALFORGE_CHIEF_PROVIDER": ("chief_engineer", "provider"),
        "LOCALFORGE_CHIEF_BASE_URL": ("chief_engineer", "base_url"),
        "LOCALFORGE_CHIEF_MODEL": ("chief_engineer", "model"),
        "LOCALFORGE_CHIEF_VISUAL_MODEL": ("chief_engineer", "visual_model"),
        "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS": (
            "chief_engineer",
            "visual_fallback_models",
        ),
        "LOCALFORGE_CHIEF_API_KEY": ("chief_engineer", "api_key"),
        "LOCALFORGE_CHIEF_FALLBACK_MODELS": ("chief_engineer", "fallback_models"),
        "LOCALFORGE_CHIEF_FALLBACK_PROVIDER": ("chief_engineer", "fallback_provider"),
        "LOCALFORGE_CHIEF_FALLBACK_BASE_URL": ("chief_engineer", "fallback_base_url"),
        "LOCALFORGE_CHIEF_FALLBACK_MODEL": ("chief_engineer", "fallback_model"),
        "LOCALFORGE_CHIEF_FALLBACK_API_KEY": ("chief_engineer", "fallback_api_key"),
        "LOCALFORGE_CHIEF_FALLBACK_AFTER_SECONDS": (
            "chief_engineer",
            "fallback_after_seconds",
        ),
        "LOCALFORGE_MAX_TASK_DURATION": ("budgets", "max_task_duration"),
        "LOCALFORGE_MAX_REPAIR_ATTEMPTS": ("budgets", "max_repair_attempts"),
        "LOCALFORGE_MAX_ACTIVE_MODEL_CALLS": ("budgets", "max_active_model_calls"),
        "LOCALFORGE_MAX_PAID_CALLS": ("budgets", "max_paid_calls"),
        "LOCALFORGE_MAX_PAID_INPUT_TOKENS": ("budgets", "max_paid_input_tokens"),
        "LOCALFORGE_MAX_PAID_OUTPUT_TOKENS": ("budgets", "max_paid_output_tokens"),
        "LOCALFORGE_MAX_PAID_USD": ("budgets", "max_paid_usd"),
        "LOCALFORGE_MAX_PAID_USD_ABSOLUTE": ("budgets", "max_paid_usd_absolute"),
        "LOCALFORGE_MAX_RUN_RECOVERY_CYCLES": ("budgets", "max_run_recovery_cycles"),
    }
    for env_var, path in env_mappings.items():
        val = env_value(env_var)
        if val is not None:
            section, key = path
            config_dict[section][key] = val
    fallback_models = os.getenv("LOCALFORGE_FALLBACK_MODELS")
    if fallback_models is not None:
        config_dict["models"]["fallback_models"] = [
            model.strip() for model in fallback_models.split(",") if model.strip()
        ]
    chief_fallback_models = os.getenv("LOCALFORGE_CHIEF_FALLBACK_MODELS")
    if chief_fallback_models is not None:
        config_dict["chief_engineer"]["fallback_models"] = [
            model.strip() for model in chief_fallback_models.split(",") if model.strip()
        ]
    chief_visual_fallback_models = os.getenv("LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS")
    if chief_visual_fallback_models is not None:
        config_dict["chief_engineer"]["visual_fallback_models"] = [
            model.strip()
            for model in chief_visual_fallback_models.split(",")
            if model.strip()
        ]
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

    for section in ("models", "chief_engineer"):
        provider = str(config_dict[section].get("provider", "")).lower()
        if provider not in {"omniroute", "omni_route"}:
            raise ValueError(
                "ForgeOS Cloud is OmniRoute-only; "
                f"{section}.provider cannot be '{provider or 'unset'}'."
            )
        config_dict[section]["provider"] = "omniroute"

    # 5. Validate with Pydantic
    try:
        config = LocalForgeConfig.model_validate(config_dict)
        _validate_omniroute_endpoint(config.models.base_url, "models")
        _validate_omniroute_endpoint(config.chief_engineer.base_url, "chief_engineer")
        if config.chief_engineer.fallback_provider not in (None, "", "omniroute", "omni_route"):
            raise ValueError(
                "chief_engineer.fallback_provider must be omitted; ForgeOS Cloud is OmniRoute-only"
            )
        if config.chief_engineer.fallback_base_url:
            _validate_omniroute_endpoint(
                config.chief_engineer.fallback_base_url, "chief_engineer.fallback"
            )
        return config
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
