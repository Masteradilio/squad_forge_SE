from dataclasses import dataclass

from localforge.safety.runner import run_safe_command
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@dataclass(frozen=True)
class TestRunResult:
    __test__ = False

    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class FocusedTestRunner:
    def __init__(self, uow: UnitOfWork, *, project_id: int, run_id: int):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id

    async def run(
        self,
        *,
        task_id: int,
        task_run_id: int,
        worktree_path: str,
        command: str,
        timeout: float,
        artifact_root: str | None = None,
    ) -> TestRunResult:
        assert self.uow.tasks is not None
        task = await self.uow.tasks.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")
        try:
            exit_code, stdout, stderr = await run_safe_command(
                project_id=self.project_id,
                command=command,
                uow=self.uow,
                run_id=self.run_id,
                task_id=task_id,
                timeout=timeout,
            )
            result = TestRunResult(command, exit_code, stdout, stderr)
        except TimeoutError as exc:
            result = TestRunResult(command, -1, "", str(exc), timed_out=True)

        await ArtifactStore(self.uow).write_artifact(
            project_root=artifact_root or worktree_path,
            task_run_id=task_run_id,
            task_key=task.key,
            run_id=self.run_id,
            filename="tests.md",
            content=self._format_artifact(result),
            summary=f"Test command `{command}` exited {result.exit_code}",
        )
        return result

    def _format_artifact(self, result: TestRunResult) -> str:
        return (
            f"# Test Result\n\n"
            f"Command: `{result.command}`\n\n"
            f"Exit code: {result.exit_code}\n\n"
            f"Timed out: {result.timed_out}\n\n"
            f"## stdout\n\n```\n{result.stdout}\n```\n\n"
            f"## stderr\n\n```\n{result.stderr}\n```\n"
        )
