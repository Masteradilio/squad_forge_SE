import logging

from localforge.core.config import LocalForgeConfig
from localforge.sandbox.base import BaseSandbox
from localforge.sandbox.docker import DockerSandbox
from localforge.sandbox.local import LocalSandbox

logger = logging.getLogger(__name__)


def create_sandbox(
    config: LocalForgeConfig,
    worktree_path: str,
    image_override: str | None = None,
    network_override: bool | None = None,
) -> BaseSandbox:
    """Create a sandbox instance based on the application configuration.

    A Docker configuration is a security contract.  It must fail closed when
    Docker cannot be constructed; silently switching to a host subprocess would
    violate the deployment's isolation guarantee.
    """
    sandbox_type = config.sandbox.type.lower()

    if sandbox_type == "docker":
        image = image_override or config.sandbox.image
        network_enabled = (
            config.sandbox.network_enabled if network_override is None else network_override
        )
        if network_enabled:
            raise RuntimeError(
                "Sandbox egress is not enabled by this runner until the allowlist-aware network is provisioned."
            )

        try:
            import docker  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Docker sandbox is configured but the Docker Python SDK is not installed."
            ) from exc
        return DockerSandbox(
            worktree_path=worktree_path,
            image=image,
            network_enabled=network_enabled,
            cpu_limit=config.sandbox.cpu_limit,
            memory_limit_mb=config.sandbox.memory_limit_mb,
            pids_limit=config.sandbox.pids_limit,
            read_only_root=config.sandbox.read_only_root,
            egress_allowlist=config.sandbox.egress_allowlist,
        )

    return LocalSandbox(worktree_path=worktree_path)
