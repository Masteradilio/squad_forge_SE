import subprocess
from dataclasses import dataclass

from localforge.models.enums import FailureClass
from localforge.repair.classifier import FailureClassifier
from localforge.runtime.compression import compress_tool_output
from localforge.safety.command_validator import command_to_argv


@dataclass(frozen=True)
class IntegrationResult:
    passed: bool
    task_keys: list[str]
    command: str
    output_summary: str
    failure_class: FailureClass | None = None


class IntegrationBranchValidator:
    def validate(
        self,
        *,
        worktree_path: str,
        task_keys: list[str],
        test_command: str,
        timeout_seconds: float = 120.0,
    ) -> IntegrationResult:
        try:
            completed = subprocess.run(
                command_to_argv(test_command),
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            output = completed.stdout + completed.stderr
        except ValueError as exc:
            return IntegrationResult(
                passed=False,
                task_keys=task_keys,
                command=test_command,
                output_summary=compress_tool_output(str(exc), max_chars=1000),
                failure_class=FailureClass.CONTRACT_DRIFT,
            )
        except subprocess.TimeoutExpired as exc:
            output = _text(exc.stdout) + _text(exc.stderr) + "\nTimeout expired."
            return IntegrationResult(
                passed=False,
                task_keys=task_keys,
                command=test_command,
                output_summary=compress_tool_output(output, max_chars=1000),
                failure_class=FailureClass.TIMEOUT,
            )
        if completed.returncode == 0:
            return IntegrationResult(
                passed=True,
                task_keys=task_keys,
                command=test_command,
                output_summary=compress_tool_output(output, max_chars=1000),
            )
        classified = FailureClassifier().classify(
            output=output,
            task_contract={"allowed_files": task_keys},
            attempt_count=2,
        )
        return IntegrationResult(
            passed=False,
            task_keys=task_keys,
            command=test_command,
            output_summary=compress_tool_output(output, max_chars=1000),
            failure_class=classified.failure_class,
        )


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
