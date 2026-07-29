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

    If 'docker' is configured but fails to initialize or import, it falls back to
    the 'local' sandbox and logs a warning.
    """
    sandbox_type = config.sandbox.type.lower()

    if sandbox_type == "docker":
        image = image_override or config.sandbox.image
        network_enabled = (
            config.sandbox.network_enabled if network_override is None else network_override
        )

        try:
            # Check if docker package can be imported
            import docker  # noqa: F401

            return DockerSandbox(
                worktree_path=worktree_path,
                image=image,
                network_enabled=network_enabled,
            )
        except ImportError:
            logger.warning(
                "Docker Python SDK is not installed. Falling back to local restricted sandbox."
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize Docker sandbox: {e}. "
                "Falling back to local restricted sandbox."
            )

    return LocalSandbox(worktree_path=worktree_path)
