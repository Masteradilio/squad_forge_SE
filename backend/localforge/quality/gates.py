from dataclasses import dataclass
import os
import re

from localforge.models.enums import ActionApprovalStatus, TaskStatus
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reasons: list[str]


class QualityGateEvaluator:
    def __init__(self, uow: UnitOfWork, *, project_id: int, run_id: int):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id

    async def evaluate(
        self,
        *,
        task_id: int,
        task_run_id: int,
        test_results: list[dict[str, object]],
    ) -> GateResult:
        assert self.uow.tasks is not None
        task = await self.uow.tasks.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")

        reasons: list[str] = []
        if any(result.get("exit_code") != 0 for result in test_results):
            reasons.append("failed tests")
        if not test_results and not task.metadata.get("quality_risk_note"):
            reasons.append("missing tests")
        if await self._has_unapproved_protected_changes(task.metadata):
            reasons.append("protected file approval required")
        if await self._has_likely_secret_changes(task_run_id, task.metadata):
            reasons.append("likely secret detected")

        allowed = not reasons
        if allowed:
            await self._move_to_review(task_id)
        elif "failed tests" in reasons and task.status != TaskStatus.BLOCKED:
            await self._block_task(task_id)

        await self._write_risk_artifact(task_run_id, task.key, allowed, reasons)
        return GateResult(allowed=allowed, reasons=reasons)

    async def _has_unapproved_protected_changes(self, metadata: dict[str, object]) -> bool:
        changed_files = metadata.get("changed_files", [])
        if not isinstance(changed_files, list):
            return False
        protected = [path for path in changed_files if isinstance(path, str) and ".env" in path]
        if not protected:
            return False
        assert self.uow.safety is not None
        approvals = await self.uow.safety.list_approvals_for_run(self.run_id)
        return not any(
            approval.status == ActionApprovalStatus.APPROVED
            and approval.task_id is not None
            and approval.payload.get("path") in protected
            for approval in approvals
        )

    async def _has_likely_secret_changes(
        self, task_run_id: int, metadata: dict[str, object]
    ) -> bool:
        changed_files = metadata.get("changed_files", [])
        if not isinstance(changed_files, list):
            return False
        assert self.uow.tasks is not None
        task_run = await self.uow.tasks.get_task_run(task_run_id)
        if not task_run or not task_run.worktree_path:
            return False
        patterns = [
            re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
            re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
        ]
        for rel_path in changed_files:
            if not isinstance(rel_path, str):
                continue
            target = os.path.realpath(os.path.abspath(os.path.join(task_run.worktree_path, rel_path)))
            root = os.path.realpath(os.path.abspath(task_run.worktree_path))
            try:
                if os.path.commonpath([root, target]) != root:
                    continue
            except ValueError:
                continue
            if not os.path.isfile(target):
                continue
            try:
                content = open(target, encoding="utf-8").read(64_000)
            except OSError:
                continue
            if any(pattern.search(content) for pattern in patterns):
                return True
        return False

    async def _move_to_review(self, task_id: int) -> None:
        task = await self.uow.tasks.get_task(task_id)  # type: ignore[union-attr]
        if not task:
            return
        if task.status == TaskStatus.TESTING:
            await self.uow.tasks.update_task_status(task_id, TaskStatus.REVIEWING)  # type: ignore[union-attr]

    async def _block_task(self, task_id: int) -> None:
        task = await self.uow.tasks.get_task(task_id)  # type: ignore[union-attr]
        if not task:
            return
        if task.status == TaskStatus.TESTING:
            await self.uow.tasks.update_task_status(task_id, TaskStatus.BLOCKED)  # type: ignore[union-attr]

    async def _write_risk_artifact(
        self,
        task_run_id: int,
        task_key: str,
        allowed: bool,
        reasons: list[str],
    ) -> None:
        assert self.uow.projects is not None
        project = await self.uow.projects.get_project(self.project_id)
        if not project:
            return
        content = (
            "# Quality Gate\n\n"
            f"Allowed: {allowed}\n\n"
            f"Reasons: {', '.join(reasons) if reasons else 'none'}\n"
        )
        await ArtifactStore(self.uow).write_artifact(
            project_root=project.root_path,
            task_run_id=task_run_id,
            task_key=task_key,
            run_id=self.run_id,
            filename="risk.md",
            content=content,
            summary="Quality gate evaluation",
        )
