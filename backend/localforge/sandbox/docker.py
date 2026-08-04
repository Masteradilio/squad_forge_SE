import asyncio
import io
import os
import shutil
import tarfile
from collections.abc import Callable
from typing import Any

from localforge.sandbox.base import BaseSandbox


class DockerSandbox(BaseSandbox):
    """Containerized sandbox executing commands inside a Docker container."""

    def __init__(
        self,
        worktree_path: str,
        image: str = "python:3.12-slim",
        network_enabled: bool = False,
        cpu_limit: float = 1.0,
        memory_limit_mb: int = 1024,
        pids_limit: int = 256,
        read_only_root: bool = True,
        egress_allowlist: list[str] | None = None,
        operation_timeout_seconds: float = 15.0,
    ):
        self.worktree_path = worktree_path
        self.image = image
        self.network_enabled = network_enabled
        self.cpu_limit = cpu_limit
        self.memory_limit_mb = memory_limit_mb
        self.pids_limit = pids_limit
        self.read_only_root = read_only_root
        self.egress_allowlist = list(egress_allowlist or [])
        self.operation_timeout_seconds = max(operation_timeout_seconds, 1.0)
        self.container: Any = None
        self._status = "stopped"
        self.client: Any = None

    async def create(self) -> None:
        """Provision the Docker container with workspace mounted."""
        if self.network_enabled:
            raise RuntimeError(
                "Docker sandbox network access is unavailable until an allowlist-aware "
                "egress proxy is provisioned."
            )
        try:
            import docker as docker_sdk
        except ImportError as e:
            raise RuntimeError(
                "Docker Python SDK is not installed. "
                "Install the 'docker' package to use Docker sandbox."
            ) from e

        docker_module: Any = docker_sdk
        try:
            self.client = await self._run_sdk_call(
                docker_module.from_env,
                operation="connect to Docker daemon",
            )
            await self._run_sdk_call(self.client.ping, operation="ping Docker daemon")
        except Exception as e:
            self._status = "failed"
            raise RuntimeError(f"Failed to connect to Docker daemon: {e}") from e

        # Ensure target image exists or pull it
        try:
            await self._run_sdk_call(
                lambda: self.client.images.get(self.image),
                operation=f"inspect Docker image '{self.image}'",
            )
        except Exception as exc:
            if exc.__class__.__name__ != "ImageNotFound":
                raise
            try:
                await self._run_sdk_call(
                    lambda: self.client.images.pull(self.image),
                    operation=f"pull Docker image '{self.image}'",
                )
            except Exception as e:
                self._status = "failed"
                raise RuntimeError(f"Failed to pull Docker image '{self.image}': {e}") from e

        # Set up options
        abs_worktree = os.path.abspath(self.worktree_path)
        volumes = {
            abs_worktree: {
                "bind": "/workspace",
                "mode": "rw",
            }
        }
        container_environment: dict[str, str] = {}
        git_metadata = self._linked_worktree_mount(abs_worktree)
        if git_metadata is not None:
            repo_root, container_git_dir = git_metadata
            volumes[repo_root] = {
                "bind": "/forgeos-repo",
                "mode": "rw",
            }
            container_environment = {
                "GIT_DIR": container_git_dir,
                "GIT_WORK_TREE": "/workspace",
            }

        network_mode = "bridge" if self.network_enabled else "none"

        # Create and run container in background (keeps running)
        try:
            self.container = await self._run_sdk_call(
                lambda: self.client.containers.run(
                    image=self.image,
                    command="tail -f /dev/null",  # Keeps container alive
                    detach=True,
                    volumes=volumes,
                    working_dir="/workspace",
                    network_mode=network_mode,
                    nano_cpus=int(self.cpu_limit * 1_000_000_000),
                    mem_limit=f"{self.memory_limit_mb}m",
                    pids_limit=self.pids_limit,
                    security_opt=["no-new-privileges:true"],
                    # Keep the image root read-only while giving test runners a
                    # bounded writable scratch area. Pytest and similar tools
                    # require /tmp even when the product workspace is mounted RW.
                    tmpfs={"/tmp": "rw,noexec,nosuid,size=256m"},
                    read_only=self.read_only_root,
                    environment=container_environment,
                    auto_remove=True,  # Clean up when stopped
                ),
                operation="create Docker sandbox container",
            )
            self._status = "running"
        except Exception as e:
            self._status = "failed"
            raise RuntimeError(f"Failed to start Docker container: {e}") from e

    async def _run_sdk_call(
        self,
        operation_fn: Callable[[], Any],
        *,
        operation: str,
    ) -> Any:
        """Run a blocking Docker SDK operation with a bounded wait.

        Docker Desktop can leave named-pipe calls blocked while it is starting
        or restarting.  The scheduler must receive a deterministic failure
        instead of waiting until its outer task timeout cancels the coroutine.
        """
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, operation_fn),
                timeout=self.operation_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Docker operation '{operation}' timed out after "
                f"{self.operation_timeout_seconds:g} seconds."
            ) from exc

    @staticmethod
    def _linked_worktree_mount(worktree_path: str) -> tuple[str, str] | None:
        """Map a host Git worktree's common repository into the container.

        A linked worktree stores only a ``.git`` pointer in the worktree.  The
        pointer contains a host path that is meaningless inside Docker, so the
        common repository is mounted separately and Git is configured through
        ``GIT_DIR``/``GIT_WORK_TREE``.
        """
        git_pointer = os.path.join(worktree_path, ".git")
        if not os.path.isfile(git_pointer):
            return None
        try:
            with open(git_pointer, encoding="utf-8") as handle:
                pointer = handle.read().strip()
            if not pointer.lower().startswith("gitdir:"):
                return None
            raw_git_dir = pointer.split(":", 1)[1].strip()
            git_dir = raw_git_dir
            if not os.path.isabs(git_dir):
                git_dir = os.path.abspath(os.path.join(worktree_path, git_dir))
            git_dir = os.path.realpath(git_dir)
            common_git_dir = os.path.realpath(os.path.join(git_dir, "..", ".."))
            repo_root = os.path.realpath(os.path.join(common_git_dir, ".."))
            if not os.path.isdir(common_git_dir) or not os.path.isdir(repo_root):
                return None
            relative_git_dir = os.path.relpath(git_dir, repo_root).replace(os.sep, "/")
            return repo_root, f"/forgeos-repo/{relative_git_dir}"
        except (OSError, ValueError):
            return None

    async def execute(self, cmd: str, timeout: float = 60.0) -> tuple[int, str, str]:
        """Execute a shell command inside the Docker container."""
        if self._status != "running" or not self.container:
            raise RuntimeError("Sandbox is not running.")

        loop = asyncio.get_running_loop()

        def run_exec():
            # Exec run under a shell
            exec_cmd = ["/bin/sh", "-c", cmd]
            # demux=True separates stdout and stderr streams in the output tuple
            return self.container.exec_run(
                exec_cmd,
                workdir="/workspace",
                demux=True,
            )

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, run_exec),
                timeout=timeout,
            )
        except TimeoutError as e:
            raise TimeoutError(f"Command execution timed out after {timeout} seconds.") from e

        exit_code = result.exit_code
        stdout_bytes, stderr_bytes = result.output

        stdout_str = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
        stderr_str = stderr_bytes.decode(errors="replace") if stderr_bytes else ""

        return exit_code, stdout_str, stderr_str

    async def copy_to(self, host_path: str, container_path: str) -> None:
        """Copy a file or directory from the host system into the sandbox."""
        if self._status != "running" or not self.container:
            raise RuntimeError("Sandbox is not running.")

        # If it's within /workspace, since it's mounted, copy locally to host path.
        if container_path.startswith("/workspace"):
            rel_path = os.path.relpath(container_path, "/workspace")
            host_dest = os.path.abspath(os.path.join(self.worktree_path, rel_path))

            # Safety check: make sure host_dest is within worktree_path
            real_worktree = os.path.realpath(self.worktree_path)
            real_dest = os.path.realpath(host_dest)
            if os.path.commonpath([real_worktree, real_dest]) != real_worktree:
                raise PermissionError("Path traversal detected; cannot write outside worktree.")

            if os.path.abspath(host_path) == os.path.abspath(host_dest):
                return

            if os.path.isdir(host_path):
                if os.path.exists(host_dest):
                    shutil.rmtree(host_dest)
                shutil.copytree(host_path, host_dest)
            else:
                os.makedirs(os.path.dirname(host_dest), exist_ok=True)
                shutil.copy2(host_path, host_dest)
        else:
            # Fallback to docker SDK put_archive.
            loop = asyncio.get_running_loop()

            def do_put():
                tar_stream = io.BytesIO()
                with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                    tar.add(host_path, arcname=os.path.basename(host_path))
                tar_stream.seek(0)
                dest_dir = os.path.dirname(container_path) or "/"
                self.container.put_archive(dest_dir, tar_stream.read())

            await loop.run_in_executor(None, do_put)

    async def copy_from(self, container_path: str, host_path: str) -> None:
        """Copy a file or directory out of the sandbox onto the host system."""
        if self._status != "running" or not self.container:
            raise RuntimeError("Sandbox is not running.")

        if container_path.startswith("/workspace"):
            rel_path = os.path.relpath(container_path, "/workspace")
            host_src = os.path.abspath(os.path.join(self.worktree_path, rel_path))

            real_worktree = os.path.realpath(self.worktree_path)
            real_src = os.path.realpath(host_src)
            if os.path.commonpath([real_worktree, real_src]) != real_worktree:
                raise PermissionError("Path traversal detected; cannot read outside worktree.")

            if os.path.abspath(host_src) == os.path.abspath(host_path):
                return

            if os.path.isdir(host_src):
                if os.path.exists(host_path):
                    shutil.rmtree(host_path)
                shutil.copytree(host_src, host_path)
            else:
                os.makedirs(os.path.dirname(host_path), exist_ok=True)
                shutil.copy2(host_src, host_path)
        else:
            # Fallback to docker SDK get_archive.
            loop = asyncio.get_running_loop()

            def do_get():
                bits, _ = self.container.get_archive(container_path)
                tar_stream = io.BytesIO()
                for chunk in bits:
                    tar_stream.write(chunk)
                tar_stream.seek(0)
                with tarfile.open(fileobj=tar_stream, mode="r") as tar:
                    self._safe_extract_archive(tar, os.path.dirname(host_path) or ".")

            await loop.run_in_executor(None, do_get)

    @staticmethod
    def _safe_extract_archive(tar: tarfile.TarFile, destination: str) -> None:
        """Extract a Docker archive while rejecting traversal and link attacks."""
        real_destination = os.path.realpath(os.path.abspath(destination))
        for member in tar.getmembers():
            target = os.path.realpath(os.path.abspath(os.path.join(real_destination, member.name)))
            if os.path.commonpath([real_destination, target]) != real_destination:
                raise PermissionError(f"Unsafe archive member path: {member.name}")
            if member.issym() or member.islnk():
                raise PermissionError(f"Archive links are not allowed: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise PermissionError(f"Unsupported archive member type: {member.name}")

        for member in tar.getmembers():
            target = os.path.realpath(os.path.abspath(os.path.join(real_destination, member.name)))
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            source = tar.extractfile(member)
            if source is None:
                raise PermissionError(f"Could not read archive member: {member.name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with source, open(target, "wb") as handle:
                shutil.copyfileobj(source, handle)

    async def destroy(self) -> None:
        """Destroy the Docker container."""
        if self.container:
            loop = asyncio.get_running_loop()
            try:
                # Stop container (auto_remove will delete it)
                await loop.run_in_executor(None, lambda: self.container.stop(timeout=2))
            except Exception:
                try:
                    await loop.run_in_executor(None, lambda: self.container.remove(force=True))
                except Exception:
                    pass
            self.container = None
        self._status = "destroyed"

    async def status(self) -> str:
        """Query the status of the container."""
        if self._status == "running" and self.container:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, self.container.reload)
                state = self.container.status
                if state == "running":
                    self._status = "running"
                else:
                    self._status = "stopped"
            except Exception:
                self._status = "stopped"
        return self._status
