"""Security controls shared by API, audit, prompts, and exported artifacts."""

import hmac
import os
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

DEFAULT_MAX_BODY_BYTES = 1_000_000
PUBLIC_PATHS = {"/health", "/ready", "/openapi.json", "/docs", "/redoc"}


@dataclass(frozen=True)
class SecurityPolicy:
    """Runtime security policy derived from environment configuration."""

    api_token: str | None = None
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES

    @classmethod
    def from_environment(cls) -> "SecurityPolicy":
        max_body_raw = os.getenv("LOCALFORGE_MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))
        try:
            max_body_bytes = max(1024, int(max_body_raw))
        except ValueError:
            max_body_bytes = DEFAULT_MAX_BODY_BYTES
        environment = os.getenv("LOCALFORGE_ENV", os.getenv("FORGEOS_ENV", "development")).lower()
        api_token = os.getenv("LOCALFORGE_API_TOKEN") or None
        if environment in {"production", "staging"} and not api_token:
            # Fail closed: a deployment without an auth secret must not expose
            # mutable project, prompt, or execution endpoints.
            api_token = "__missing_production_api_token__"
        return cls(
            api_token=api_token,
            max_body_bytes=max_body_bytes,
        )


SECRET_PATTERNS = (
    re.compile(
        r"(?i)(api[_-]?key|secret|password|token|authorization)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9_\-./:=+]{8,}['\"]?"
    ),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-./:=+]{8,}"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9][A-Za-z0-9_-]{15,}\b"),
    re.compile(r"(?i)\b(?:nvapi|ghp_|github_pat_|xoxb-|xoxp-|AIza)[A-Za-z0-9_-]{16,}\b"),
)


def redact_secrets(text: str) -> str:
    """Redact environment-backed and common inline secret shapes."""
    if not text:
        return text

    redacted = text
    for name, value in os.environ.items():
        if _looks_sensitive_name(name) and value and len(value.strip()) > 3:
            redacted = redacted.replace(value, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_secrets_recursive(value: object) -> object:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {k: redact_secrets_recursive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets_recursive(item) for item in value]
    return value


def ensure_relative_to(root: Path, candidate: Path) -> Path:
    """Resolve a candidate path and fail closed when it escapes root."""
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes configured root: {candidate}") from exc
    return resolved_candidate


def enforce_payload_size(request: Request, policy: SecurityPolicy) -> None:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return
    try:
        size = int(content_length)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc
    if size > policy.max_body_bytes:
        raise HTTPException(status_code=413, detail="Request payload too large")


def enforce_api_auth(request: Request, policy: SecurityPolicy) -> None:
    if not policy.api_token or request.url.path in PUBLIC_PATHS:
        return
    expected = f"Bearer {policy.api_token}"
    if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


def _looks_sensitive_name(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "KEY"))

