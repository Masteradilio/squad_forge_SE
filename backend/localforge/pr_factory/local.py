import os
from dataclasses import dataclass

from localforge.contracts.verifier import ContractVerifier
from localforge.models import domain
from localforge.models.enums import AgentRole, AuditEventActorType, AuditEventType, HandoffKind, TaskStatus
from localforge.pr_factory.github import GitHubPRAdapter
from localforge.safety.pre_pr_gate import MechanicalPrePRGate
from localforge.storage import UnitOfWork
from localforge.storage.artifacts import ArtifactStore
from localforge.visual.gate import VisualFidelityGate, validate_visual_html_structure
from localforge.visual.screenshot import capture_html_screenshot


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
        changed_files = task.metadata.get("changed_files", [])
        if not isinstance(changed_files, list):
            changed_files = []
        reasons = self._readiness_reasons(task_run.branch_name, artifact_paths, changed_files)

        # 1. Run ContractVerifier if task contract exists
        contract = task.metadata.get("task_contract")
        worktree_path = task_run.worktree_path or project.root_path
        if isinstance(contract, dict) and worktree_path:
            verifier_res = ContractVerifier().verify(
                worktree_path=worktree_path,
                task_contract=contract,
                changed_files=[str(f) for f in changed_files if isinstance(f, str)],
            )
            if not verifier_res.passed:
                for finding in verifier_res.findings:
                    reasons.append(f"Contract violation: {finding.message}")

        # 2. Run VisualFidelityGate only when visual_required is declared by task contract or metadata
        visual_required = False
        visual_ref_rel = None
        visual_actual_rel = None
        visual_threshold = 0.90
        visual_viewport = "1280x720"

        if isinstance(contract, dict):
            visual_required = bool(contract.get("visual_required", False))
            visual_ref_rel = contract.get("visual_reference_image")
            visual_actual_rel = contract.get("visual_actual_output")
            visual_threshold = float(contract.get("visual_similarity_threshold", 0.90))
            visual_viewport = str(contract.get("visual_viewport", visual_viewport))

        if not visual_required:
            visual_required = bool(task.metadata.get("visual_required", False))
        if not visual_ref_rel:
            visual_ref_rel = task.metadata.get("visual_reference_image")
        if not visual_actual_rel:
            visual_actual_rel = task.metadata.get("visual_actual_output")
        if "visual_similarity_threshold" in task.metadata:
            visual_threshold = float(task.metadata["visual_similarity_threshold"])
        if "visual_viewport" in task.metadata:
            visual_viewport = str(task.metadata["visual_viewport"])

        if visual_required and worktree_path:
            ref_image_path = None
            if visual_ref_rel:
                # 1. Try relative to worktree
                p1 = os.path.normpath(os.path.join(worktree_path, visual_ref_rel))
                if os.path.isfile(p1):
                    ref_image_path = p1
                else:
                    # 2. Try relative to parent repo root
                    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    p2 = os.path.normpath(os.path.join(backend_dir, "..", visual_ref_rel))
                    if os.path.isfile(p2):
                        ref_image_path = p2
                    else:
                        # 3. Try direct absolute path
                        if os.path.isfile(visual_ref_rel):
                            ref_image_path = os.path.abspath(visual_ref_rel)

            html_abs_path = None
            if visual_actual_rel:
                p_html = os.path.normpath(os.path.join(worktree_path, visual_actual_rel))
                if os.path.isfile(p_html):
                    html_abs_path = p_html
            else:
                # Fallback to walk worktree for html files
                html_files = []
                for root, _, files in os.walk(worktree_path):
                    for file in files:
                        if file.endswith(".html"):
                            html_files.append(os.path.join(root, file))
                if html_files:
                    html_abs_path = html_files[0]

            if visual_ref_rel and not ref_image_path:
                reasons.append(
                    f"Visual mismatch: Reference image not found for path '{visual_ref_rel}'."
                )
            elif not html_abs_path:
                reasons.append(
                    f"Visual mismatch: Actual HTML output not found for path '{visual_actual_rel}'."
                )
            else:
                structure_rules: list[str] = []
                if isinstance(contract, dict):
                    raw_rules = contract.get("visual_structure_rules", [])
                    if isinstance(raw_rules, list):
                        structure_rules = [item for item in raw_rules if isinstance(item, str)]
                    raw_matrix = contract.get("visual_acceptance_matrix", [])
                    visual_matrix = [item for item in raw_matrix if isinstance(item, dict)] if isinstance(raw_matrix, list) else []
                else:
                    visual_matrix = []
                structure_findings = validate_visual_html_structure(
                    html_abs_path, structure_rules=structure_rules, visual_matrix=visual_matrix
                )
                reasons.extend(
                    f"Visual structure mismatch: {finding}" for finding in structure_findings
                )
                actual_image_path = os.path.join(worktree_path, "actual_layout.png")
                captured = capture_html_screenshot(
                    html_abs_path, actual_image_path, viewport=visual_viewport
                )
                if captured and ref_image_path:
                    visual_result = VisualFidelityGate().evaluate(
                        reference_image_path=ref_image_path,
                        actual_image_path=actual_image_path,
                        task_is_visual=True,
                        min_similarity=visual_threshold,
                    )
                    if not visual_result.passed:
                        reasons.append(f"Visual mismatch: {visual_result.summary}")
                elif not captured:
                    reasons.append("Visual mismatch: Headless screenshot capture failed.")

        # Generate cost benchmark report
        cost_report_md = ""
        try:
            assert self.uow.cost_benchmark is not None
            cost_report_md = await self.uow.cost_benchmark.generate_markdown_report(
                self.project_id, self.run_id
            )
            cost_artifact = await ArtifactStore(self.uow).write_artifact(
                project_root=project.root_path,
                task_run_id=task_run_id,
                task_key=task.key,
                run_id=self.run_id,
                filename="cost_benchmark.md",
                content=cost_report_md,
                summary=f"Cost benchmark artifact for {task.key}",
            )
            artifact_paths.add(cost_artifact.path)
        except Exception as exc:
            reasons.append(f"Cost benchmark unavailable: {exc}")
        if not any(path.endswith("cost_benchmark.md") for path in artifact_paths):
            reasons.append("cost_benchmark.md missing")

        remote_url: str | None = None
        task_metadata = dict(task.metadata or {})
        source_commit = str(
            task_metadata.get("current_source_commit")
            or task_metadata.get("source_commit")
            or ""
        ).strip()
        target_commit = str(
            task_metadata.get("current_target_commit")
            or task_metadata.get("target_commit")
            or ""
        ).strip()
        if not source_commit or not target_commit:
            reasons.append("observed source/target commit binding missing")

        gate_result = None
        if not reasons:
            diff_text = await ArtifactStore(self.uow).read_artifact(
                project.root_path, self.run_id, task.key, "diff.patch"
            )
            gate_result = await MechanicalPrePRGate().evaluate_gate(
                project_id=self.project_id,
                task_run_id=task_run_id,
                uow=self.uow,
                diff_text=diff_text,
                modified_files=[str(path) for path in changed_files if isinstance(path, str)],
            )
            if not gate_result.passed:
                reasons.extend(f"Pre-PR gate: {violation}" for violation in gate_result.violations)

        verification = None
        if not reasons:
            assert self.uow.maker_checker is not None
            verification = await self.uow.maker_checker.get_verification_for_task_run(task_run_id)
            if verification is None or verification.id is None:
                reasons.append("approved Maker/Checker verification missing")
            elif verification.status.value != "APPROVED" or not verification.deterministic_passed:
                reasons.append("Maker/Checker verification is not an approved deterministic result")
        ready = not reasons
        pr_body = self._render_pr_body(
            task, task_run, sorted(artifact_paths), reasons, cost_report_md=cost_report_md
        )
        pr_artifact = await ArtifactStore(self.uow).write_artifact(
            project_root=project.root_path,
            task_run_id=task_run_id,
            task_key=task.key,
            run_id=self.run_id,
            filename="pr.md",
            content=pr_body,
            summary=f"Local PR artifact for {task.key}",
        )

        if ready and task.status == TaskStatus.REVIEWING:
            assert self.uow.executions is not None
            assert verification is not None
            remote_url = self.github_adapter.create_pr(
                title=f"{task.key}: {task.title}",
                body=pr_body,
                branch=task_run.branch_name or "",
            )
        if ready and task.status == TaskStatus.REVIEWING:
            assert gate_result is not None
            assert verification is not None
            handoff = await self.uow.executions.create_handoff(
                domain.Handoff(
                    task_run_id=task_run_id,
                    from_role=AgentRole.REVIEWER,
                    to_role=AgentRole.PR_WRITER,
                    kind=HandoffKind.PR_READY,
                    payload_json={"source": "pr_factory", "artifact_path": pr_artifact.path},
                )
            )
            await self.uow.tasks.mark_pr_ready(
                task_id,
                gate_evidence={
                    "source": "pr_factory",
                    "task_run_id": task_run_id,
                    "handoff_id": handoff.id or 0,
                    "maker_id": verification.maker_agent_id,
                    "checker_id": verification.checker_agent_id,
                    "maker_attempt_id": f"maker-checker:{verification.id}",
                    "checker_attempt_id": f"mechanical-pre-pr-gate:{verification.id}",
                    "pre_pr_gate": {
                        "passed": gate_result.passed,
                        "remote_url": remote_url,
                        "source_commit": source_commit,
                        "target_commit": target_commit,
                        "diff_hash": pr_artifact.content_hash,
                        "checks": gate_result.checks,
                    },
                    "risk_verdict": {"passed": True, "source": "contract-verifier"},
                    "safety_verdict": {"passed": True, "source": "mechanical-pre-pr-gate"},
                    "checks_executed": ["local-pr-artifact-created", "contract-verifier"],
                    "artifact_paths": [pr_artifact.path],
                    "branch_name": task_run.branch_name,
                    "worktree_path": task_run.worktree_path,
                    "source_commit": source_commit,
                    "target_commit": target_commit,
                    "diff_hash": pr_artifact.content_hash,
                },
            )

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

    def _readiness_reasons(
        self,
        branch_name: str | None,
        artifact_paths: set[str],
        changed_files: list[object],
    ) -> list[str]:
        reasons: list[str] = []
        if not branch_name:
            reasons.append("branch missing")
        if not any(isinstance(path, str) and path.strip() for path in changed_files):
            reasons.append("changed files missing")
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
        cost_report_md: str = "",
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
                cost_report_md,
                "",
                "## Branch Protection",
                "- Target branch: main",
                "- Required before merge: one PR review, green CI, no direct pushes",
                "- LocalForge PR Factory status: ready for protected-branch review flow",
                "",
            ]
        )
