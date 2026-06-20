from dataclasses import dataclass

from localforge.models import domain
from localforge.models.enums import AuditEventActorType, AuditEventType, TaskStatus
from localforge.pr_factory.github import GitHubPRAdapter
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore


@dataclass(frozen=True)
class PRFactoryResult:
    ready: bool
    artifact_path: str
    remote_url: str | None = None
    reasons: list[str] | None = None


class LocalPRFactory:
    def __init__(
        self,
        uow: UnitOfWork,
        *,
        project_id: int,
        run_id: int,
        github_adapter: GitHubPRAdapter | None = None,
    ):
        self.uow = uow
        self.project_id = project_id
        self.run_id = run_id
        self.github_adapter = github_adapter or GitHubPRAdapter.from_environment()

    async def generate(self, *, task_id: int, task_run_id: int) -> PRFactoryResult:
        assert self.uow.projects is not None
        assert self.uow.tasks is not None
        assert self.uow.audits is not None
        project = await self.uow.projects.get_project(self.project_id)
        task = await self.uow.tasks.get_task(task_id)
        task_run = await self.uow.tasks.get_task_run(task_run_id)
        if not project or not task or not task_run:
            raise ValueError("Project, task, and task run are required for PR artifact generation.")

        artifacts = await self.uow.audits.list_artifacts_for_task_run(task_run_id)
        artifact_paths = {artifact.path for artifact in artifacts}
        reasons = self._readiness_reasons(task_run.branch_name, artifact_paths)
        pr_body = self._render_pr_body(task, task_run, sorted(artifact_paths), reasons)

        pr_artifact = await ArtifactStore(self.uow).write_artifact(
            project_root=project.root_path,
            task_run_id=task_run_id,
            task_key=task.key,
            run_id=self.run_id,
            filename="pr.md",
            content=pr_body,
            summary=f"Local PR artifact for {task.key}",
        )

        remote_url = self.github_adapter.create_pr(
            title=f"{task.key}: {task.title}",
            body=pr_body,
            branch=task_run.branch_name or "",
        )
        ready = not reasons
        if ready and task.status == TaskStatus.REVIEWING:
            await self.uow.tasks.update_task_status(task_id, TaskStatus.PR_READY)

        await self.uow.audits.append_audit_event(
            domain.AuditEvent(
                project_id=self.project_id,
                run_id=self.run_id,
                task_id=task_id,
                actor_type=AuditEventActorType.SYSTEM,
                actor_id="pr-factory",
                event_type=AuditEventType.SYSTEM_EVENT,
                payload_redacted={
                    "action": "pr_artifact_generated",
                    "ready": ready,
                    "artifact_path": pr_artifact.path,
                    "remote_url": remote_url,
                    "reasons": reasons,
                },
            )
        )
        return PRFactoryResult(
            ready=ready,
            artifact_path=pr_artifact.path,
            remote_url=remote_url,
            reasons=reasons,
        )

    def _readiness_reasons(self, branch_name: str | None, artifact_paths: set[str]) -> list[str]:
        reasons: list[str] = []
        if not branch_name:
            reasons.append("branch missing")
        required_suffixes = ("diff.patch", "tests.md", "risk.md")
        for suffix in required_suffixes:
            if not any(path.endswith(suffix) for path in artifact_paths):
                reasons.append(f"{suffix} missing")
        return reasons

    def _render_pr_body(
        self,
        task: domain.Task,
        task_run: domain.TaskRun,
        artifact_paths: list[str],
        reasons: list[str],
    ) -> str:
        changed_files = task.metadata.get("changed_files", [])
        if not isinstance(changed_files, list):
            changed_files = []
        repair_attempts = [path for path in artifact_paths if path.endswith("repair.md")]
        has_diff = any(path.endswith("diff.patch") for path in artifact_paths)
        has_tests = any(path.endswith("tests.md") for path in artifact_paths)
        branch_label = task_run.branch_name or "missing"
        return "\n".join(
            [
                f"# {task.key}: {task.title}",
                "",
                "## Summary",
                task_run.final_summary or task.description or "No summary recorded.",
                "",
                "## Acceptance Criteria",
                *[f"- {item}" for item in task.acceptance_criteria],
                "",
                "## Changed Files",
                *[f"- {path}" for path in changed_files if isinstance(path, str)],
                "",
                "## Tests",
                *[f"- {path}" for path in artifact_paths if path.endswith("tests.md")],
                "",
                "## Risk",
                *[f"- {path}" for path in artifact_paths if path.endswith("risk.md")],
                "",
                "## Repair Attempts",
                *(f"- {path}" for path in repair_attempts),
                *(["- none"] if not repair_attempts else []),
                "",
                "## Evidence",
                *[f"- {path}" for path in artifact_paths],
                "",
                "## Checklist",
                f"- [{'x' if task_run.branch_name else ' '}] Branch exists: {branch_label}",
                f"- [{'x' if has_diff else ' '}] Diff artifact exists",
                f"- [{'x' if has_tests else ' '}] Test artifact exists",
                f"- [{'x' if not reasons else ' '}] Local PR-ready gates pass",
                "",
            ]
        )
