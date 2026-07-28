import io
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from localforge.cli.doctor import check_docker
from localforge.core.config import LocalForgeConfig, SandboxConfig
from localforge.models import domain
from localforge.safety.runner import run_safe_command
from localforge.sandbox.docker import DockerSandbox
from localforge.sandbox.factory import create_sandbox
from localforge.sandbox.local import LocalSandbox
from localforge.storage import UnitOfWork


@pytest.mark.anyio
async def test_local_sandbox_lifecycle(tmp_path):
    """Verify LocalSandbox runs commands locally inside the worktree and manages files."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    sandbox = LocalSandbox(str(worktree))
    assert await sandbox.status() == "stopped"

    with pytest.raises(RuntimeError):
        await sandbox.execute("echo 1")

    await sandbox.create()
    assert await sandbox.status() == "running"

    # Run hello command
    exit_code, stdout, stderr = await sandbox.execute(
        'python -c "print(\'hello\')"'
    )
    assert exit_code == 0
    assert "hello" in stdout

    # Copy file in
    src_file = tmp_path / "src.txt"
    src_file.write_text("hello contents")
    dest_file = worktree / "dest.txt"
    await sandbox.copy_to(str(src_file), str(dest_file))
    assert dest_file.read_text() == "hello contents"

    # Copy file out
    out_file = tmp_path / "out.txt"
    await sandbox.copy_from(str(dest_file), str(out_file))
    assert out_file.read_text() == "hello contents"

    await sandbox.destroy()
    assert await sandbox.status() == "destroyed"


@pytest.mark.anyio
async def test_local_sandbox_timeout(tmp_path):
    """Verify LocalSandbox enforces timeout bounds and kills execution."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    sandbox = LocalSandbox(str(worktree))
    await sandbox.create()

    with pytest.raises(TimeoutError):
        await sandbox.execute(
            'python -c "import time; time.sleep(10)"', timeout=0.1
        )

    await sandbox.destroy()


@pytest.mark.anyio
async def test_local_sandbox_rejects_shell_composition(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    sandbox = LocalSandbox(str(worktree))
    await sandbox.create()

    with pytest.raises(ValueError, match="Shell operators"):
        await sandbox.execute("python -c \"print(1)\" && echo unsafe")

    await sandbox.destroy()


@pytest.mark.anyio
async def test_local_sandbox_blocks_workspace_escape_during_copy(tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("payload")
    sandbox = LocalSandbox(str(worktree))

    with pytest.raises(PermissionError, match="outside its worktree"):
        await sandbox.copy_to(str(source), str(tmp_path / "outside.txt"))


@pytest.mark.anyio
async def test_docker_sandbox_mocked(tmp_path):
    """Verify DockerSandbox calls Docker SDK with correct configuration and local file mapping."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    mock_docker = MagicMock()
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.status = "running"

    mock_docker.from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container

    # Exec result mock
    mock_exec_result = MagicMock()
    mock_exec_result.exit_code = 0
    mock_exec_result.output = (b"docker_out", b"docker_err")
    mock_container.exec_run.return_value = mock_exec_result

    with patch.dict("sys.modules", {"docker": mock_docker}):
        sandbox = DockerSandbox(
            str(worktree), image="custom-python", network_enabled=False
        )
        assert await sandbox.status() == "stopped"

        await sandbox.create()
        assert await sandbox.status() == "running"

        # Check container runs with right specs
        mock_client.containers.run.assert_called_once()
        kwargs = mock_client.containers.run.call_args[1]
        assert kwargs["image"] == "custom-python"
        assert kwargs["network_mode"] == "none"
        assert kwargs["working_dir"] == "/workspace"
        assert str(worktree) in kwargs["volumes"]

        # Run execute command
        exit_code, stdout, stderr = await sandbox.execute(
            "echo something", timeout=5
        )
        assert exit_code == 0
        assert stdout == "docker_out"
        assert stderr == "docker_err"

        # Check volume mount copy shortcut
        src_file = tmp_path / "src.txt"
        src_file.write_text("direct_volume_write")
        dest_in_workspace = "/workspace/sub_folder/dest.txt"

        await sandbox.copy_to(str(src_file), dest_in_workspace)
        copied_host_path = worktree / "sub_folder" / "dest.txt"
        assert copied_host_path.exists()
        assert copied_host_path.read_text() == "direct_volume_write"

        await sandbox.destroy()
        mock_container.stop.assert_called_once_with(timeout=2)
        assert await sandbox.status() == "destroyed"


@pytest.mark.anyio
async def test_docker_sandbox_blocks_workspace_prefix_escape(tmp_path):
    """Verify DockerSandbox rejects sibling paths that only share a string prefix."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    sibling = tmp_path / "worktree_evil"
    sibling.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("payload")

    sandbox = DockerSandbox(str(worktree))
    sandbox._status = "running"
    sandbox.container = MagicMock()

    with pytest.raises(PermissionError):
        await sandbox.copy_to(str(source), f"/workspace/../{sibling.name}/dest.txt")

    with pytest.raises(PermissionError):
        await sandbox.copy_from(f"/workspace/../{sibling.name}/dest.txt", str(tmp_path / "out.txt"))


@pytest.mark.anyio
async def test_docker_sandbox_rejects_unsafe_archive_member(tmp_path):
    """Verify Docker archive fallback rejects path traversal members."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    tar_stream = io.BytesIO()
    payload = b"escape"
    info = tarfile.TarInfo("../escaped.txt")
    info.size = len(payload)
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        tar.addfile(info, io.BytesIO(payload))
    tar_bytes = tar_stream.getvalue()

    sandbox = DockerSandbox(str(worktree))
    sandbox._status = "running"
    sandbox.container = MagicMock()
    sandbox.container.get_archive.return_value = ([tar_bytes], {})

    with pytest.raises(PermissionError):
        await sandbox.copy_from("/tmp/archive.txt", str(tmp_path / "safe" / "archive.txt"))

    assert not (tmp_path / "escaped.txt").exists()


@pytest.mark.anyio
async def test_sandbox_factory_resolution():
    """Verify factory returns appropriate provider according to config & packages."""
    config_local = LocalForgeConfig(
        sandbox=SandboxConfig(
            type="local", image="test:latest", network_enabled=False
        )
    )
    config_docker = LocalForgeConfig(
        sandbox=SandboxConfig(
            type="docker", image="test:latest", network_enabled=False
        )
    )

    # Local config resolves to LocalSandbox
    sandbox = create_sandbox(config_local, "/dummy")
    assert isinstance(sandbox, LocalSandbox)

    # Docker config without SDK falls back to LocalSandbox
    with patch.dict("sys.modules", {"docker": None}):
        sandbox = create_sandbox(config_docker, "/dummy")
        assert isinstance(sandbox, LocalSandbox)

    # Docker config with SDK resolves to DockerSandbox
    mock_docker = MagicMock()
    with patch.dict("sys.modules", {"docker": mock_docker}):
        sandbox = create_sandbox(config_docker, "/dummy")
        assert isinstance(sandbox, DockerSandbox)
        assert sandbox.image == "test:latest"
        assert sandbox.network_enabled is False


@pytest.mark.anyio
async def test_check_docker_cli_variants():
    """Verify check_docker diagnoses Docker daemon & SDK availability configurations."""
    # Case 1: Docker CLI not in PATH
    with patch("shutil.which", return_value=None):
        status, msg, details = await check_docker()
        assert status == "WARN"
        assert "not installed" in msg
        assert details == "not_installed"

    # Case 2: Docker command exists but daemon is stopped
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = (b"", b"connection refused")

    with (
        patch("shutil.which", return_value="/bin/docker"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        patch.dict("sys.modules", {"docker": None}),
    ):
        status, msg, details = await check_docker()
        assert status == "WARN"
        assert "daemon is not running" in msg
        assert details == "inactive"

    # Case 3: Daemon running but python SDK not installed
    mock_proc_ok = AsyncMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.communicate.return_value = (b"active daemon info", b"")

    with (
        patch("shutil.which", return_value="/bin/docker"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc_ok),
        patch.dict("sys.modules", {"docker": None}),
    ):
        status, msg, details = await check_docker()
        assert status == "WARN"
        assert "Python 'docker' SDK is missing" in msg
        assert details == "missing_sdk"

    # Case 4: Fully functional daemon and Python SDK
    mock_docker = MagicMock()
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client

    with (
        patch("shutil.which", return_value="/bin/docker"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc_ok),
        patch.dict("sys.modules", {"docker": mock_docker}),
    ):
        status, msg, details = await check_docker()
        assert status == "PASS"
        assert "functional" in msg
        assert details == "active"
        mock_client.ping.assert_called_once()


@pytest.mark.anyio
async def test_run_safe_command_routes_to_sandbox(tmp_path, db_session):
    """Verify run_safe_command routes executions to sandbox and records audit events."""
    uow = UnitOfWork()
    uow.session = db_session

    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService

    uow.projects = ProjectService(db_session)
    uow.audits = AuditService(db_session)
    uow.tasks = TaskService(db_session)
    uow.safety = SafetyService(db_session)

    proj_data = domain.Project(
        name="CmdSandboxTest", root_path=str(tmp_path), default_branch="main"
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    from localforge.safety.kernel import SafetyDecision

    # Mock the SafetyKernel.evaluate and LocalSandbox.execute methods
    with patch(
        "localforge.safety.runner.SafetyKernel.evaluate",
        return_value=(SafetyDecision.ALLOW, ""),
    ), patch(
        "localforge.sandbox.local.LocalSandbox.execute",
        return_value=(0, "output_from_sandbox_run", ""),
    ) as mock_exec:
        exit_code, out, err = await run_safe_command(
            project_id=project.id,
            command="echo 'sandbox-test'",
            uow=uow,
            timeout=15.0,
        )
        assert exit_code == 0
        assert out == "output_from_sandbox_run"
        mock_exec.assert_called_once_with("echo 'sandbox-test'", timeout=15.0)
