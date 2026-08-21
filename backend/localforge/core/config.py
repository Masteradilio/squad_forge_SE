import os
from typing import Any
from urllib.parse import urlsplit

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, ValidationError, field_validator

from localforge.models.enums import ReleasePromotionMode
from localforge.services.pricing import DEFAULT_MAX_GATEWAY_CALLS, is_free_gateway_model

DEFAULT_LLAMACPP_URL = "http://localhost:8080/v1"
DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_OMNIROUTE_URL = "http://localhost:20128/v1"
DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_NVIDIA_URL = "https://integrate.api.nvidia.com/v1"
SUPPORTED_LLM_PROVIDERS = {
    "llamacpp",
    "llama.cpp",
    "local",
    "ollama",
    "omniroute",
    "openrouter",
    "nvidia",
}

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
        "provider": "llamacpp",
        "base_url": "http://localhost:8080/v1",
        "api_key": None,
        "default_model": "qwen3.8-27b",
        "fallback_models": [
            "qwen3.8-27b",
            "auto/best-free",
            "auto/coding:free",
        ],
        "fallback_routes": [],
        "roles": {},
    },
    "chief_engineer": {
        "provider": "llamacpp",
        "base_url": "http://localhost:8080/v1",
        "model": "qwen3.8-27b",
        "api_key": None,
        "fallback_models": [
            "qwen3.8-27b",
            "auto/coding:free",
            "auto/best-free",
        ],
        "visual_fallback_models": [
            "qwen3.8-27b",
            "auto/coding:free",
            "auto/best-free",
        ],
        "fallback_provider": None,
        "fallback_base_url": None,
        "fallback_model": None,
        "fallback_api_key": None,
        "fallback_routes": [],
        "fallback_after_seconds": 30.0,
        "timeout": 240.0,
        "omniroute_structured_timeout": 120.0,
        "max_input_tokens_per_call": 32000,
        "max_output_tokens_per_call": 8000,
    },
    "context7": {
        "enabled": True,
        "endpoint": "https://mcp.context7.com/mcp",
        "api_key": None,
        "timeout": 30.0,
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
        "max_gateway_calls": DEFAULT_MAX_GATEWAY_CALLS,
        "max_paid_calls": 30,
        "max_paid_input_tokens": 400000,
        "max_paid_output_tokens": 60000,
        "max_paid_usd": 4.0,
        "max_repair_attempts_absolute": 10,
        "max_run_recovery_cycles": 3,
        "max_paid_usd_absolute": 6.0,
    },
    "release": {
        "promotion_mode": ReleasePromotionMode.HUMAN_APPROVAL.value,
        "target_branch": None,
        "post_merge_agents": ["Tester", "SafetyAuditor"],
        "tester_command": "python -m pytest -q",
        "security_command": "python scripts/check_security_scans.py",
        "post_merge_timeout": 600.0,
        "require_clean_target": True,
        "operational_profiles": [],
        "require_release_tree_audit": False,
        "require_semantic_review": False,
    },
}


class ProjectConfig(BaseModel):
    name: str = Field(default="Default Project")


class GitConfig(BaseModel):
    default_branch: str = Field(default="main")
    remote_url: str | None = Field(default=None)


class ProviderRouteConfig(BaseModel):
    """One explicit provider/model lane used after the primary route."""

    provider: str
    base_url: str | None = Field(default=None)
    model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)


class ModelsConfig(BaseModel):
    provider: str = Field(default="llamacpp")
    base_url: str = Field(default="http://localhost:8080/v1")
    api_key: str | None = Field(default=None)
    default_model: str = Field(default="qwen3.8-27b")
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "qwen3.8-27b",
            "auto/best-free",
            "auto/coding:free",
        ]
    )
    fallback_routes: list[ProviderRouteConfig] = Field(default_factory=list)
    roles: dict[str, str] = Field(default_factory=dict)


class ChiefEngineerConfig(BaseModel):
    provider: str = Field(default="llamacpp")
    base_url: str = Field(default="http://localhost:8080/v1")
    model: str | None = Field(default="qwen3.8-27b")
    visual_model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    fallback_models: list[str] = Field(
        default_factory=lambda: [
            "qwen3.8-27b",
            "auto/coding:free",
            "auto/best-free",
        ]
    )
    visual_fallback_models: list[str] = Field(
        default_factory=lambda: [
            "qwen3.8-27b",
            "auto/coding:free",
            "auto/best-free",
        ]
    )
    fallback_provider: str | None = Field(default=None)
    fallback_base_url: str | None = Field(default=None)
    fallback_model: str | None = Field(default=None)
    fallback_api_key: str | None = Field(default=None)
    fallback_routes: list[ProviderRouteConfig] = Field(default_factory=list)
    fallback_after_seconds: float = Field(default=30.0)
    enabled: bool = Field(default=True)
    timeout: float = Field(default=240.0)
    # OmniRoute streaming routes can spend longer than the generic request
    # timeout in hidden reasoning before emitting a complete structured plan.
    # Keep this explicit and bounded instead of silently hard-capping repairs.
    omniroute_structured_timeout: float = Field(default=120.0, ge=30.0, le=600.0)
    max_input_tokens_per_call: int = Field(default=32000)
    max_output_tokens_per_call: int = Field(default=8000)


class Context7Config(BaseModel):
    """Configuration for the optional Context7 documentation boundary."""

    enabled: bool = Field(default=True)
    endpoint: str = Field(default="https://mcp.context7.com/mcp", min_length=1)
    api_key: str | None = Field(default=None)
    timeout: float = Field(default=30.0, gt=0, le=120)


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
    # OmniRoute is a gateway, not proof that every upstream route is free.
    # Bound gateway calls separately; the default is finite and can be
    # overridden with LOCALFORGE_MAX_GATEWAY_CALLS or workspace YAML.
    max_gateway_calls: int = Field(default=DEFAULT_MAX_GATEWAY_CALLS, ge=0)
    max_paid_calls: int = Field(default=30)
    max_paid_input_tokens: int = Field(default=400000)
    max_paid_output_tokens: int = Field(default=60000)
    max_paid_usd: float = Field(default=4.0)
    # Absolute ceilings enforced by the scheduler recovery loop:
    max_repair_attempts_absolute: int = Field(default=10)
    max_run_recovery_cycles: int = Field(default=3)
    max_paid_usd_absolute: float = Field(default=6.0)


class ReleaseConfig(BaseModel):
    """Promotion policy applied after implementation reaches PR_READY."""

    promotion_mode: ReleasePromotionMode = Field(default=ReleasePromotionMode.HUMAN_APPROVAL)
    target_branch: str | None = Field(default=None, min_length=1)
    post_merge_agents: list[str] = Field(
        default_factory=lambda: ["Tester", "SafetyAuditor"], min_length=2
    )
    tester_command: str = Field(default="python -m pytest -q", min_length=1)
    security_command: str = Field(
        default="python scripts/check_security_scans.py", min_length=1
    )
    post_merge_timeout: float = Field(default=600.0, gt=0, le=3600.0)
    require_clean_target: bool = Field(default=True)
    operational_profiles: list[str] = Field(default_factory=list)
    require_release_tree_audit: bool = Field(default=False)
    require_semantic_review: bool = Field(default=False)

    @field_validator("operational_profiles")
    @classmethod
    def validate_operational_profiles(cls, value: list[str]) -> list[str]:
        from localforge.services.operational_profiles import normalize_profile_names

        return normalize_profile_names(value)

    @field_validator("post_merge_agents")
    @classmethod
    def validate_post_merge_agents(cls, value: list[str]) -> list[str]:
        normalized = [item.lower().replace("_", "").replace("-", "") for item in value]
        if normalized != ["tester", "safetyauditor"]:
            raise ValueError("post_merge_agents must contain exactly Tester and SafetyAuditor")
        return value


class LocalForgeConfig(BaseModel):
    version: int = Field(default=1)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    chief_engineer: ChiefEngineerConfig = Field(default_factory=ChiefEngineerConfig)
    context7: Context7Config = Field(default_factory=Context7Config)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    release: ReleaseConfig = Field(default_factory=ReleaseConfig)


def configured_free_gateway_models(config: LocalForgeConfig) -> list[str]:
    """Return the configured OmniRoute-only free route ladder.

    Runtime discovery may replace this list with routes verified by the live
    gateway. The configuration fallback must still be deterministic, must not
    contain direct-provider identifiers, and must never advertise a paid or
    unknown route as a free one.
    """
    candidates = [
        config.models.default_model,
        *config.chief_engineer.fallback_models,
        *config.chief_engineer.visual_fallback_models,
        *config.models.fallback_models,
        *config.models.roles.values(),
    ]
    routes = [
        route
        for route in dict.fromkeys(candidates)
        if route and is_free_gateway_model(route)
    ]
    return routes or ["auto/best-free"]


def _find_env_file(start_dir: str) -> str | None:
    """Return only the workspace-local dotenv file.

    Walking all parent directories makes a root project's credentials leak
    into unrelated temporary workspaces (and into isolated test projects)
    whenever the process is started below that root. ForgeOS documents the
    project-root ``.env`` convention, so the current working directory is the
    only implicit source; callers that need another workspace must change
    directory before loading configuration.
    """
    candidate = os.path.join(os.path.abspath(start_dir), ".env")
    return candidate if os.path.exists(candidate) else None


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
    workspace_config: dict[str, Any] = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                file_data = yaml.safe_load(f)
                if isinstance(file_data, dict):
                    workspace_config = file_data
                    merge_dicts(config_dict, file_data)
        except Exception as e:
            raise ValueError(f"Failed to parse workspace config file at {config_path}: {e}") from e

    # 2. Load from .env without mutating process environment or logging secrets.
    env_file_path = _find_env_file(cwd)
    env_file_values: dict[str, str | None] = {}
    if env_file_path and os.path.exists(env_file_path):
        # Read vendor settings locally without exporting them to the process
        # environment or including them in configuration diagnostics.
        env_file_values = {
            str(key): value
            for key, value in dotenv_values(env_file_path).items()
            if key is not None
        }

    def env_value(name: str) -> str | None:
        value = os.getenv(name)
        value = value if value is not None else env_file_values.get(name)
        return value.strip() if isinstance(value, str) else value

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

    # Context7 is an optional documentation boundary. It may be configured
    # with its canonical names or the legacy URL alias, without exporting
    # credentials into the process environment.
    context7_endpoint = env_value("CONTEXT7_MCP_ENDPOINT") or env_value("CONTEXT7_MCP_URL")
    if context7_endpoint:
        config_dict["context7"]["endpoint"] = context7_endpoint

    # 3. Load from Environment Variables
    env_mappings = {
        "LOCALFORGE_PROJECT_NAME": ("project", "name"),
        "LOCALFORGE_DEFAULT_BRANCH": ("git", "default_branch"),
        "LOCALFORGE_REMOTE_URL": ("git", "remote_url"),
        "LOCALFORGE_RELEASE_PROMOTION_MODE": ("release", "promotion_mode"),
        "LOCALFORGE_RELEASE_TARGET_BRANCH": ("release", "target_branch"),
        "LOCALFORGE_RELEASE_TESTER_COMMAND": ("release", "tester_command"),
        "LOCALFORGE_RELEASE_SECURITY_COMMAND": ("release", "security_command"),
        "LOCALFORGE_RELEASE_POST_MERGE_TIMEOUT": ("release", "post_merge_timeout"),
        "LOCALFORGE_RELEASE_REQUIRE_CLEAN_TARGET": ("release", "require_clean_target"),
        "LOCALFORGE_RELEASE_OPERATIONAL_PROFILES": ("release", "operational_profiles"),
        "LOCALFORGE_RELEASE_REQUIRE_TREE_AUDIT": ("release", "require_release_tree_audit"),
        "LOCALFORGE_RELEASE_REQUIRE_SEMANTIC_REVIEW": (
            "release",
            "require_semantic_review",
        ),
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
        "CONTEXT7_API_KEY": ("context7", "api_key"),
        "CONTEXT7_ENABLED": ("context7", "enabled"),
        "CONTEXT7_TIMEOUT": ("context7", "timeout"),
        "LOCALFORGE_OMNIROUTE_STRUCTURED_TIMEOUT": (
            "chief_engineer",
            "omniroute_structured_timeout",
        ),
        # The CLI benchmark flag exports this canonical budget override before
        # starting the monitor. Keep it in the generic env-to-config boundary
        # so the monitor and scheduler receive the same value.
        "LOCALFORGE_MAX_RUN_TIME": ("budgets", "max_run_time"),
        "LOCALFORGE_MAX_TASK_DURATION": ("budgets", "max_task_duration"),
        "LOCALFORGE_MAX_PARALLEL_TASKS": ("budgets", "max_parallel_tasks"),
        "LOCALFORGE_MAX_REPAIR_ATTEMPTS": ("budgets", "max_repair_attempts"),
        "LOCALFORGE_MAX_ACTIVE_MODEL_CALLS": ("budgets", "max_active_model_calls"),
        "LOCALFORGE_MAX_DIFF_GROWTH": ("budgets", "max_diff_growth"),
        "LOCALFORGE_MAX_VISUAL_DIFF_GROWTH": ("budgets", "max_visual_diff_growth"),
        "LOCALFORGE_MAX_GATEWAY_CALLS": ("budgets", "max_gateway_calls"),
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
    fallback_models = env_value("LOCALFORGE_FALLBACK_MODELS")
    if fallback_models is not None:
        config_dict["models"]["fallback_models"] = [
            model.strip() for model in fallback_models.split(",") if model.strip()
        ]
    chief_fallback_models = env_value("LOCALFORGE_CHIEF_FALLBACK_MODELS")
    if chief_fallback_models is not None:
        config_dict["chief_engineer"]["fallback_models"] = [
            model.strip() for model in chief_fallback_models.split(",") if model.strip()
        ]
    chief_visual_fallback_models = env_value("LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS")
    if chief_visual_fallback_models is not None:
        config_dict["chief_engineer"]["visual_fallback_models"] = [
            model.strip()
            for model in chief_visual_fallback_models.split(",")
            if model.strip()
        ]
    release_profiles = env_value("LOCALFORGE_RELEASE_OPERATIONAL_PROFILES")
    if release_profiles is not None:
        config_dict["release"]["operational_profiles"] = [
            profile.strip() for profile in release_profiles.split(",") if profile.strip()
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

    chief_file_config = workspace_config.get("chief_engineer", {})
    if not isinstance(chief_file_config, dict):
        chief_file_config = {}
    chief_model_explicit = (
        "model" in chief_file_config or env_value("LOCALFORGE_CHIEF_MODEL") is not None
    )
    chief_base_url_explicit = (
        "base_url" in chief_file_config
        or env_value("LOCALFORGE_CHIEF_BASE_URL") is not None
    )
    chief_api_key_explicit = (
        "api_key" in chief_file_config
        or env_value("LOCALFORGE_CHIEF_API_KEY") is not None
    )

    # OPENROUTER_PAID_MODEL is the canonical paid lane. Keep the old name as
    # a compatibility alias so existing installations do not silently lose
    # their route during the migration.
    openrouter_paid_model = env_value("OPENROUTER_PAID_MODEL") or env_value(
        "OPENROUTER_MODEL"
    )
    openrouter_free_model = env_value("OPENROUTER_FREE_MODEL")
    openrouter_api_key = env_value("OPENROUTER_API_KEY")
    openrouter_url = env_value("OPENROUTER_URL")
    nvidia_model = env_value("NVIDIA_LLM_MODEL")
    nvidia_api_key = env_value("NVIDIA_API_KEY")
    nvidia_url = env_value("NVIDIA_URL") or DEFAULT_NVIDIA_URL

    configured_chief_provider = str(
        config_dict["chief_engineer"].get("provider", "")
    ).strip().lower()

    # 4-Tier LLM Administration Ladder:
    # Tier 1: Local llama.cpp / Ollama (Primary)
    # Tier 2: OmniRoute Gateway (:20128 auto/best-free)
    # Tier 3: NVIDIA API (if configured)
    # Tier 4: OpenRouter Paid (last-resort critical fallback from .env)
    cascade_routes: list[dict[str, str | None]] = []
    
    # Tier 2: OmniRoute gateway fallback
    if configured_chief_provider in {"llamacpp", "llama.cpp", "local", "ollama"}:
        cascade_routes.append(
            {
                "provider": "omniroute",
                "base_url": DEFAULT_OMNIROUTE_URL,
                "model": "auto/best-free",
                "api_key": None,
            }
        )

    # Tier 3: NVIDIA direct API route
    if nvidia_model and nvidia_api_key:
        cascade_routes.append(
            {
                "provider": "nvidia",
                "base_url": nvidia_url,
                "model": nvidia_model,
                "api_key": nvidia_api_key,
            }
        )

    # Tier 4: OpenRouter Paid (last-resort critical fallback)
    if openrouter_paid_model and openrouter_api_key:
        cascade_routes.append(
            {
                "provider": "openrouter",
                "base_url": openrouter_url or DEFAULT_OPENROUTER_URL,
                "model": openrouter_paid_model,
                "api_key": openrouter_api_key,
            }
        )
    elif openrouter_free_model and openrouter_api_key:
        cascade_routes.append(
            {
                "provider": "openrouter",
                "base_url": openrouter_url or DEFAULT_OPENROUTER_URL,
                "model": openrouter_free_model,
                "api_key": openrouter_api_key,
            }
        )

    if cascade_routes:
        config_dict["models"]["fallback_routes"] = [
            *config_dict["models"].get("fallback_routes", []),
            *cascade_routes,
        ]
        config_dict["chief_engineer"]["fallback_routes"] = [
            *config_dict["chief_engineer"].get("fallback_routes", []),
            *cascade_routes,
        ]

    for section in ("models", "chief_engineer"):
        provider = str(config_dict[section].get("provider", "")).strip().lower()
        if provider == "omni_route":
            provider = "omniroute"
        if provider not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(
                f"{section}.provider must be one of "
                f"{', '.join(sorted(SUPPORTED_LLM_PROVIDERS))}; "
                f"got '{provider or 'unset'}'."
            )
        config_dict[section]["provider"] = provider

    fallback_provider = config_dict["chief_engineer"].get("fallback_provider")
    fallback_provider_name = str(fallback_provider or "").strip().lower()
    fallback_route_explicit = any(
        field in chief_file_config or env_value(env_name) is not None
        for field, env_name in {
            "fallback_provider": "LOCALFORGE_CHIEF_FALLBACK_PROVIDER",
            "fallback_base_url": "LOCALFORGE_CHIEF_FALLBACK_BASE_URL",
            "fallback_model": "LOCALFORGE_CHIEF_FALLBACK_MODEL",
            "fallback_api_key": "LOCALFORGE_CHIEF_FALLBACK_API_KEY",
        }.items()
    )
    if (
        not fallback_route_explicit
        and configured_chief_provider.replace("_", "") == "omniroute"
        and openrouter_paid_model
        and openrouter_api_key
    ):
        fallback_provider_name = "openrouter"
        config_dict["chief_engineer"]["fallback_provider"] = fallback_provider_name

    if fallback_provider_name == "omni_route":
        fallback_provider_name = "omniroute"
    if fallback_provider_name:
        if fallback_provider_name not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(
                "chief_engineer.fallback_provider must be one of "
                f"{', '.join(sorted(SUPPORTED_LLM_PROVIDERS))}; "
                f"got '{fallback_provider_name}'."
            )
        config_dict["chief_engineer"]["fallback_provider"] = fallback_provider_name
        if fallback_provider_name == "openrouter":
            # Explicit fallback fields retain precedence over the canonical
            # OpenRouter dotenv values. A missing key/model remains a factory
            # error when the fallback is actually constructed.
            if config_dict["chief_engineer"].get("fallback_base_url") is None:
                config_dict["chief_engineer"]["fallback_base_url"] = (
                    openrouter_url or DEFAULT_OPENROUTER_URL
                )
            if config_dict["chief_engineer"].get("fallback_model") is None:
                config_dict["chief_engineer"]["fallback_model"] = openrouter_paid_model
            if config_dict["chief_engineer"].get("fallback_api_key") is None:
                config_dict["chief_engineer"]["fallback_api_key"] = openrouter_api_key
        elif fallback_provider_name == "nvidia":
            if config_dict["chief_engineer"].get("fallback_base_url") is None:
                config_dict["chief_engineer"]["fallback_base_url"] = nvidia_url
            if config_dict["chief_engineer"].get("fallback_model") is None:
                config_dict["chief_engineer"]["fallback_model"] = nvidia_model
            if config_dict["chief_engineer"].get("fallback_api_key") is None:
                config_dict["chief_engineer"]["fallback_api_key"] = nvidia_api_key
    else:
        config_dict["chief_engineer"]["fallback_provider"] = None

    # 5. Validate with Pydantic
    try:
        config = LocalForgeConfig.model_validate(config_dict)
        if config.models.provider == "omniroute":
            _validate_omniroute_endpoint(config.models.base_url, "models")
        if config.chief_engineer.provider == "omniroute":
            _validate_omniroute_endpoint(config.chief_engineer.base_url, "chief_engineer")
        if config.chief_engineer.fallback_provider == "omniroute" and config.chief_engineer.fallback_base_url:
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
