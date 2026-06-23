from abc import ABC, abstractmethod


class BaseSandbox(ABC):
    """Abstract interface defining the lifecycle and execution model of an execution sandbox."""

    @abstractmethod
    async def create(self) -> None:
        """Create or provision the sandbox environment."""
        pass

    @abstractmethod
    async def execute(self, cmd: str, timeout: float = 60.0) -> tuple[int, str, str]:
        """Execute a shell command inside the sandbox.

        Returns a tuple of (exit_code, stdout, stderr).
        """
        pass

    @abstractmethod
    async def copy_to(self, host_path: str, container_path: str) -> None:
        """Copy a file or directory from the host system into the sandbox."""
        pass

    @abstractmethod
    async def copy_from(self, container_path: str, host_path: str) -> None:
        """Copy a file or directory out of the sandbox onto the host system."""
        pass

    @abstractmethod
    async def destroy(self) -> None:
        """Destroy or clean up the sandbox environment."""
        pass

    @abstractmethod
    async def status(self) -> str:
        """Query and return the execution status of the sandbox (e.g., 'running', 'stopped')."""
        pass
