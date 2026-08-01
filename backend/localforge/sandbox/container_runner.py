"""Ephemeral Container Sandbox Runner — Isolated Docker/Podman Sandbox & Live Preview Manager."""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import pydantic


class SandboxConfig(pydantic.BaseModel):
    container_id: str
    tenant_id: str
    project_id: str
    vcpu_limit: float = 1.0
    memory_limit_mb: int = 1024
    disk_limit_mb: int = 5120
    egress_whitelist: List[str] = ["registry.npmjs.org", "pypi.org", "github.com"]
    preview_url: str = ""


class ContainerRunner:
    """Manages ephemeral sandboxed containers with hardware caps and egress whitelisting."""

    def __init__(self, sandbox_domain: str = "preview.forgeos.app"):
        self.sandbox_domain = sandbox_domain

    def create_sandbox(self, tenant_id: str, project_id: str) -> SandboxConfig:
        """Create sandbox configuration with cgroups v2 resource limits and live preview URL."""
        preview_url = f"https://{tenant_id}-{project_id}.{self.sandbox_domain}"
        config = SandboxConfig(
            container_id=f"sbx_{tenant_id}_{project_id}",
            tenant_id=tenant_id,
            project_id=project_id,
            preview_url=preview_url,
        )
        return config

    def scrub_secrets_from_logs(self, log_text: str) -> str:
        """Task 4.5: Secret Scrubber for terminal logs masking API keys, bearers, and tokens."""
        # Mask OpenAI/Groq sk- keys
        scrubbed = re.sub(r"sk-[a-zA-Z0-9_-]{20,}", "[REDACTED_API_KEY]", log_text)
        # Mask bearer tokens
        scrubbed = re.sub(r"(?i)bearer\s+[a-zA-Z0-9\._-]{20,}", "Bearer [REDACTED_TOKEN]", scrubbed)
        # Mask password assignments
        scrubbed = re.sub(r"(?i)(password|secret|key)=\"[^\"]+\"", r"\1=\"[REDACTED]\"", scrubbed)
        return scrubbed
