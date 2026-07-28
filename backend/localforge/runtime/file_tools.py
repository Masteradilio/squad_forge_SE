import difflib
import os
from dataclasses import dataclass

from localforge.models import domain
from localforge.models.enums import ActionKind, AuditEventActorType, AuditEventType
from localforge.safety.kernel import ActionRequest, SafetyDecision, SafetyKernel, is_path_safe
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@dataclass(frozen=True)
class FileEditResult:
    path: str
    diff: str


class SafeFileEditor:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        project_id: int,
        run_id: int | None = None,
        task_id: int | None = None,
    ):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id
        self.task_id = task_id

    async def read_text(self, worktree_root: str, relative_path: str) -> str:
        target = self._resolve(worktree_root, relative_path)
        await self._evaluate(ActionKind.READ_FILE, target, worktree_root)
        with open(target, encoding="utf-8") as handle:
            return handle.read()

    async def write_text(
        self,
        worktree_root: str,
        relative_path: str,
        content: str,
        *,
        task_run_id: int | None = None,
        task_key: str | None = None,
    ) -> FileEditResult:
        target = self._resolve(worktree_root, relative_path)
        await self._evaluate(ActionKind.WRITE_FILE, target, worktree_root)
        old_content = ""
        if os.path.exists(target):
            with open(target, encoding="utf-8") as handle:
                old_content = handle.read()

        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)

        rel_display = os.path.relpath(target, worktree_root).replace("\\", "/")
        diff = "".join(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{rel_display}",
                tofile=f"b/{rel_display}",
            )
        )
        if task_run_id and task_key and self.run_id is not None:
            await ArtifactStore(self.uow).write_artifact(
                project_root=worktree_root,
                task_run_id=task_run_id,
                task_key=task_key,
                run_id=self.run_id,
                filename="diff.patch",
                content=diff,
                summary=f"Diff for {rel_display}",
            )
        # Check budgets limits
        from localforge.core.config import load_config
        try:
            config = load_config()
            max_files = config.budgets.max_file_count
            max_diff = config.budgets.max_diff_growth
        except Exception:
            max_files = 10
            max_diff = 2000

        # Load overrides from run if available
        if self.run_id is not None:
            assert self.uow.executions is not None
            run = await self.uow.executions.get_run(self.run_id)
            if run and run.resource_limits:
                max_files = run.resource_limits.get("max_file_count", max_files)
                max_diff = run.resource_limits.get("max_diff_growth", max_diff)

        # Run git checks in worktree_root
        import subprocess
        try:
            toplevel_res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=worktree_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            toplevel = os.path.realpath(toplevel_res.stdout.strip())
            if toplevel != os.path.realpath(worktree_root):
                raise subprocess.SubprocessError()

            # Check file count
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            modified_files = [
                line[3:].strip()
                for line in (status_res.stdout or "").splitlines()
                if line.strip()
            ]
            if len(modified_files) > max_files:
                raise ValueError(
                    f"Workspace file count budget exceeded: {len(modified_files)} "
                    f"files modified/created (Limit: {max_files})."
                )

            # Check diff size
            diff_res = subprocess.run(
                ["git", "diff"],
                cwd=worktree_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            diff_len = len(diff_res.stdout or "")
            if diff_len > max_diff:
                raise ValueError(
                    f"Workspace diff growth budget exceeded: {diff_len} "
                    f"characters generated (Limit: {max_diff})."
                )
        except subprocess.SubprocessError:
            pass

        await self._audit("write_file", {"path": target, "decision": "ALLOW"})
        return FileEditResult(path=target, diff=diff)

    def _resolve(self, worktree_root: str, relative_path: str) -> str:
        target = os.path.realpath(os.path.abspath(os.path.join(worktree_root, relative_path)))
        if not is_path_safe(target, worktree_root):
            raise ValueError(f"Path outside worktree is blocked: {relative_path}")
        return target

    async def _evaluate(self, kind: ActionKind, target: str, worktree_root: str) -> None:
        request = ActionRequest(
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=self.task_id,
            kind=kind,
            payload={"path": target},
            purpose=f"{kind.value}: {target}",
        )
        decision, reason = await SafetyKernel.evaluate(request, self.uow, worktree_root)
        if decision != SafetyDecision.ALLOW:
            await self._audit(
                kind.value,
                {"path": target, "decision": decision.value, "reason": reason},
            )
            raise ValueError(reason)

    async def _audit(self, action: str, payload: dict[str, object]) -> None:
        assert self.uow.audits is not None
        await self.uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=self.task_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="runtime-file-tool",
                event_type=AuditEventType.SAFETY_DECISION,
                payload_redacted={"action": action, **payload},
            )
        )
