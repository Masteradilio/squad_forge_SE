import os
from dataclasses import dataclass
from typing import Protocol

from localforge.healing.classifier import FailureClass, FailureClassifier
from localforge.healing.policy import RepairPolicy, RepairPolicyState
from localforge.models import domain
from localforge.models.enums import AuditEventActorType, AuditEventType, TaskStatus
from localforge.quality.runner import FocusedTestRunner, TestRunResult
from localforge.runtime.file_tools import SafeFileEditor
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@dataclass(frozen=True)
class RepairAction:
    path: str
    content: str
    failure_class: FailureClass | None = None


@dataclass(frozen=True)
class RepairResult:
    repaired: bool
    reason: str
    attempts: int


class RepairTestRunner(Protocol):
    async def run(
        self,
        *,
        task_id: int,
        task_run_id: int,
        worktree_path: str,
        command: str,
        timeout: float,
    ) -> TestRunResult:
        pass


class SelfHealingEngine:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        project_id: int,
        run_id: int,
        runner: RepairTestRunner | None = None,
        policy: RepairPolicy | None = None,
        classifier: FailureClassifier | None = None,
    ):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id
        self.runner = runner or FocusedTestRunner(uow, project_id=project_id, run_id=run_id)
        self.policy = policy or RepairPolicy()
        self.classifier = classifier or FailureClassifier()

    async def repair_task(
        self,
        *,
        task_id: int,
        task_run_id: int,
        worktree_path: str,
        test_command: str,
    ) -> RepairResult:
        assert self.uow.tasks is not None
        task = await self.uow.tasks.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")
        if task.status == TaskStatus.TESTING:
            await self.uow.tasks.update_task_status(task_id, TaskStatus.REPAIRING)

        state = RepairPolicyState()
        first_result = await self.runner.run(
            task_id=task_id,
            task_run_id=task_run_id,
            worktree_path=worktree_path,
            command=test_command,
            timeout=60.0,
        )
        if first_result.exit_code == 0:
            await self._return_to_testing(task_id)
            return RepairResult(True, "tests already pass", 0)

        failure_class = self.classifier.classify(
            first_result.command, first_result.stdout, first_result.stderr
        )
        actions = self._actions_for(task.metadata, failure_class)
        if not actions:
            await self._fail_safe(task_id, task_run_id, task.key, worktree_path, "no repair action")
            return RepairResult(False, "no repair action", state.attempt_count)

        for action in actions:
            diff_growth = len(action.content)
            decision = self.policy.can_attempt(state, failure_class, diff_growth)
            if not decision.allowed:
                await self._fail_safe(
                    task_id, task_run_id, task.key, worktree_path, decision.reason
                )
                return RepairResult(False, decision.reason, state.attempt_count)

            checkpoint = self._checkpoint(worktree_path, [action.path])
            edit = await SafeFileEditor(
                self.uow,
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=task_id,
            ).write_text(
                worktree_path,
                action.path,
                action.content,
                task_run_id=task_run_id,
                task_key=task.key,
            )
            state = state.record(failure_class, len(edit.diff))
            await self._write_repair_artifact(
                task_run_id, task.key, worktree_path, action, failure_class
            )

            result = await self.runner.run(
                task_id=task_id,
                task_run_id=task_run_id,
                worktree_path=worktree_path,
                command=test_command,
                timeout=60.0,
            )
            if result.exit_code == 0:
                await self._return_to_testing(task_id)
                return RepairResult(True, "repair succeeded", state.attempt_count)

            next_failure = self.classifier.classify(result.command, result.stdout, result.stderr)
            if next_failure != failure_class:
                await self._rollback(worktree_path, checkpoint, task_id, action.path)
                await self._fail_safe(
                    task_id,
                    task_run_id,
                    task.key,
                    worktree_path,
                    "repair made failure worse",
                )
                return RepairResult(False, "repair made failure worse", state.attempt_count)

            failure_class = next_failure

        await self._fail_safe(
            task_id, task_run_id, task.key, worktree_path, "repair attempts exhausted"
        )
        return RepairResult(False, "repair attempts exhausted", state.attempt_count)

    def _actions_for(
        self, metadata: dict[str, object], failure_class: FailureClass
    ) -> list[RepairAction]:
        raw_actions = metadata.get("repair_actions", [])
        if not isinstance(raw_actions, list):
            return []
        actions: list[RepairAction] = []
        for raw in raw_actions:
            if not isinstance(raw, dict):
                continue
            path = raw.get("path")
            content = raw.get("content")
            raw_class = raw.get("failure_class")
            if not isinstance(path, str) or not isinstance(content, str):
                continue
            if isinstance(raw_class, str) and raw_class != failure_class.value:
                continue
            actions.append(RepairAction(path=path, content=content, failure_class=failure_class))
        return actions

    def _checkpoint(self, worktree_path: str, paths: list[str]) -> dict[str, str | None]:
        checkpoint: dict[str, str | None] = {}
        for rel_path in paths:
            target = os.path.realpath(os.path.abspath(os.path.join(worktree_path, rel_path)))
            if os.path.exists(target):
                with open(target, encoding="utf-8") as handle:
                    checkpoint[rel_path] = handle.read()
            else:
                checkpoint[rel_path] = None
        return checkpoint

    async def _rollback(
        self,
        worktree_path: str,
        checkpoint: dict[str, str | None],
        task_id: int,
        reason_path: str,
    ) -> None:
        for rel_path, content in checkpoint.items():
            target = os.path.realpath(os.path.abspath(os.path.join(worktree_path, rel_path)))
            if content is None:
                if os.path.exists(target):
                    os.unlink(target)
            else:
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(content)
        assert self.uow.audits is not None
        await self.uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=task_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="self-healing-engine",
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={"action": "repair_rollback", "path": reason_path},
            )
        )

    async def _return_to_testing(self, task_id: int) -> None:
        task = await self.uow.tasks.get_task(task_id)  # type: ignore[union-attr]
        if task and task.status == TaskStatus.REPAIRING:
            await self.uow.tasks.update_task_status(task_id, TaskStatus.TESTING)  # type: ignore[union-attr]

    async def _fail_safe(
        self,
        task_id: int,
        task_run_id: int,
        task_key: str,
        worktree_path: str,
        reason: str,
    ) -> None:
        task = await self.uow.tasks.get_task(task_id)  # type: ignore[union-attr]
        if task and task.status == TaskStatus.REPAIRING:
            await self.uow.tasks.update_task_status(task_id, TaskStatus.FAILED_SAFE)  # type: ignore[union-attr]
        await ArtifactStore(self.uow).write_artifact(
            project_root=worktree_path,
            task_run_id=task_run_id,
            task_key=task_key,
            run_id=self.run_id,
            filename="blocker.md",
            content=f"# Repair Blocker\n\n{reason}\n",
            summary="Self-healing blocker",
        )

    async def _write_repair_artifact(
        self,
        task_run_id: int,
        task_key: str,
        worktree_path: str,
        action: RepairAction,
        failure_class: FailureClass,
    ) -> None:
        await ArtifactStore(self.uow).write_artifact(
            project_root=worktree_path,
            task_run_id=task_run_id,
            task_key=task_key,
            run_id=self.run_id,
            filename="repair.md",
            content=(
                f"# Repair Attempt\n\nFailure class: {failure_class.value}\n\nPath: {action.path}\n"
            ),
            summary=f"Repair attempt for {failure_class.value}",
        )
