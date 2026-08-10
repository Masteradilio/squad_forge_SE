"""Governed operational and SaaS capability profiles.

Profiles are a registry, not an implicit second scheduler.  They make optional
Context7, Redis, Kubernetes/Helm, GitHub, Key Vault, security and load checks
selectable by an explicit release or compliance run while keeping the local
default deterministic and dependency-light.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OperationalCapability:
    key: str
    title: str
    kind: str
    entrypoint: str
    default_enabled: bool = False
    requires_external_service: bool = False


@dataclass(frozen=True)
class OperationalProfile:
    key: str
    title: str
    purpose: str
    capabilities: tuple[str, ...]
    entrypoint: str | None = None


CAPABILITIES: tuple[OperationalCapability, ...] = (
    OperationalCapability(
        "release_tree_audit",
        "Release tree integrity and secret scan",
        "release_gate",
        "backend.localforge.services.release_audit.ReleaseTreeAuditor",
    ),
    OperationalCapability(
        "semantic_final_review",
        "Chief Engineer semantic final PR review",
        "release_gate",
        "backend.localforge.chief_engineer.final_review.FinalReviewService",
    ),
    OperationalCapability(
        "failure_fingerprints",
        "Failure fingerprints and repair progress signals",
        "pipeline",
        "backend.localforge.services.fingerprint",
        default_enabled=True,
    ),
    OperationalCapability(
        "compiler_feedback",
        "Line-precise TypeScript compiler feedback",
        "pipeline",
        "backend.localforge.repair.compiler_feedback.CompilerFeedbackLoop",
        default_enabled=True,
    ),
    OperationalCapability(
        "light_swarm_typed_workers",
        "Typed Light Swarm dispatch, aggregation and recovery",
        "orchestration",
        "backend.localforge.services.light_swarm_dispatcher",
        default_enabled=True,
    ),
    OperationalCapability(
        "production_observability",
        "Structured logs and operator status",
        "operations",
        "backend.localforge.services.production_observability",
        default_enabled=True,
    ),
    OperationalCapability(
        "context7",
        "Versioned documentation lookup through Context7 MCP",
        "saas_optional",
        "backend.localforge.connectors.context7_mcp.Context7MCPConnector",
        requires_external_service=True,
    ),
    OperationalCapability(
        "redis",
        "Cache, Pub/Sub and distributed lock primitives",
        "saas_optional",
        "backend.localforge.services.redis_manager.RedisManager",
        requires_external_service=True,
    ),
    OperationalCapability(
        "kubernetes_helm",
        "Kubernetes/Helm deployment and recovery compliance profile",
        "operations_optional",
        "scripts.run_benchmark_full_coverage",
        requires_external_service=True,
    ),
    OperationalCapability(
        "github_draft_pr",
        "Least-privilege GitHub read and draft-PR boundary",
        "saas_optional",
        "backend.localforge.connectors.github_connector.GitHubRepositoryConnector",
        requires_external_service=True,
    ),
    OperationalCapability(
        "tenant_key_vault",
        "Tenant-scoped AES-GCM BYOK key boundary",
        "saas_optional",
        "backend.localforge.services.key_vault.KeyVaultService",
        requires_external_service=True,
    ),
    OperationalCapability(
        "security_and_load",
        "Security runtime and bounded load probes",
        "operations_optional",
        "scripts.run_security_runtime_probe",
        requires_external_service=True,
    ),
    OperationalCapability(
        "ci_pr_compliance",
        "Governed CI and draft-PR compliance evidence",
        "operations_optional",
        "scripts.run_ci_pr_compliance",
        requires_external_service=True,
    ),
    OperationalCapability(
        "frontend_release_compliance",
        "Frontend lint, typecheck, tests, build and browser evidence",
        "operations_optional",
        "scripts.run_benchmark_full_coverage",
    ),
)

PROFILES: tuple[OperationalProfile, ...] = (
    OperationalProfile(
        "reference",
        "Reference release",
        "Deterministic local task pipeline plus release evidence.",
        ("failure_fingerprints", "compiler_feedback", "production_observability"),
    ),
    OperationalProfile(
        "full_coverage",
        "Full coverage compliance",
        "Runs the governed Context7, Redis, Kubernetes, frontend, security, CI and load evidence stages.",
        tuple(item.key for item in CAPABILITIES),
        entrypoint="scripts/run_benchmark_full_coverage.py",
    ),
    OperationalProfile(
        "saas",
        "SaaS operations",
        "Enables optional tenant, provider, GitHub and hosted-infrastructure boundaries.",
        (
            "context7",
            "redis",
            "github_draft_pr",
            "tenant_key_vault",
            "production_observability",
            "security_and_load",
        ),
    ),
)

_CAPABILITY_MAP = {item.key: item for item in CAPABILITIES}
_PROFILE_MAP = {item.key: item for item in PROFILES}


def normalize_profile_names(names: list[str] | tuple[str, ...] | None) -> list[str]:
    """Validate and normalize user-selected profile names deterministically."""

    normalized: list[str] = []
    for raw in names or []:
        name = str(raw).strip().lower().replace("-", "_")
        if not name:
            continue
        if name not in _PROFILE_MAP:
            allowed = ", ".join(sorted(_PROFILE_MAP))
            raise ValueError(f"Unknown operational profile '{raw}'. Allowed: {allowed}")
        if name not in normalized:
            normalized.append(name)
    return normalized


def profile_manifest(names: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Return a serializable manifest used in release evidence and API output."""

    selected = normalize_profile_names(names)
    profiles = [_PROFILE_MAP[name] for name in selected]
    capability_names: list[str] = []
    for profile in profiles:
        for key in profile.capabilities:
            if key not in capability_names:
                capability_names.append(key)
    return {
        "selected_profiles": [item.key for item in profiles],
        "profiles": [
            {
                "key": item.key,
                "title": item.title,
                "purpose": item.purpose,
                "capabilities": list(item.capabilities),
                "entrypoint": item.entrypoint,
            }
            for item in profiles
        ],
        "capabilities": [
            {
                "key": _CAPABILITY_MAP[key].key,
                "title": _CAPABILITY_MAP[key].title,
                "kind": _CAPABILITY_MAP[key].kind,
                "entrypoint": _CAPABILITY_MAP[key].entrypoint,
                "default_enabled": _CAPABILITY_MAP[key].default_enabled,
                "requires_external_service": _CAPABILITY_MAP[key].requires_external_service,
            }
            for key in capability_names
        ],
    }


def available_profile_manifest() -> dict[str, Any]:
    """Return all profiles without selecting or executing any external stage."""

    return profile_manifest([item.key for item in PROFILES])
