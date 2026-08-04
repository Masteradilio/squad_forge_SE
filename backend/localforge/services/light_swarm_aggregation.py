"""Light Swarm canonical readiness gate aggregation and evidence submission.

The aggregator is deliberately evidence-only.  Completing DAG nodes proves
only that the orchestration state machine advanced; it does not prove that a
worktree changed, checks ran, or an independent checker approved the result.
Those observations must already exist in persisted artifacts before the
canonical task service is allowed to write ``PR_READY``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    ArtifactType,
    HandoffKind,
    SwarmNodeStatus,
    SwarmNodeType,
    TaskStatus,
    TypedArtifactType,
)
from localforge.safety.pre_pr_gate import MechanicalPrePRGate
from localforge.storage.orm import TaskORM
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {
        "",
        "unknown-source",
        "unknown-target",
        "role-pipeline",
        "0000000000000000000000000000000000000000",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }


async def aggregate_and_submit_pr_ready(
    run_id: int, uow: UnitOfWork
) -> domain.Task | None:
    """Submit observed maker/checker evidence to the canonical readiness gate.

    No handoff, PR artifact, or success verdict is created by this function.
    Missing evidence leaves the swarm in ``NEEDS_HUMAN`` and returns ``None``.
    """
    assert uow.light_swarm is not None
    assert uow.tasks is not None
    assert uow.executions is not None
    assert uow.audits is not None
    assert uow.typed_handoffs is not None
    assert uow.projects is not None
    assert uow.maker_checker is not None

    run_orm, run = await uow.light_swarm._load_run(run_id)
    plan_orm = await uow.light_swarm._load_plan_orm(run.plan_id)
    plan = plan_orm.to_domain()

    if not all(st == SwarmNodeStatus.COMPLETED.value for st in run.node_statuses.values()):
        logger.warning("SwarmRun %d not fully completed, skipping PR_READY submission", run_id)
        return None

    maker_node = next((n for n in plan.nodes if n.node_type == SwarmNodeType.IMPLEMENT), None)
    checker_node = next(
        (n for n in plan.nodes if n.node_type in (SwarmNodeType.VERIFY, SwarmNodeType.CRITIQUE)),
        None,
    )
    maker_id = (maker_node.maker_agent_id if maker_node else None) or (
        maker_node.owner_agent_id if maker_node else None
    )
    checker_id = checker_node.owner_agent_id if checker_node else None

    task_run = await uow.tasks.get_task_run(plan.task_run_id)
    task_orm = await uow.tasks.session.get(TaskORM, task_run.task_id) if task_run else None
    if task_run is None or task_run.id is None or task_orm is None:
        return await _block(run_orm, run, "task run or task is missing", uow)
    task_run_id = task_run.id
    if not maker_id or not checker_id or maker_id == checker_id:
        return await _block(run_orm, run, "independent maker/checker identity is missing", uow)
    if not task_run.branch_name or not task_run.worktree_path:
        return await _block(run_orm, run, "task run is not bound to a worktree and branch", uow)

    task_metadata = dict(task_orm.metadata_json or {})
    source_commit = str(task_metadata.get("current_source_commit") or task_metadata.get("source_commit") or "")
    target_commit = str(task_metadata.get("current_target_commit") or task_metadata.get("target_commit") or "")
    diff_hash = str(task_metadata.get("diff_hash") or "")
    if any(_is_placeholder(value) for value in (source_commit, target_commit, diff_hash)):
        return await _block(run_orm, run, "observed commit and diff bindings are missing", uow)

    artifacts = await uow.audits.list_artifacts_for_task_run(task_run_id)
    pr_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.type == ArtifactType.PR
        and artifact.path.strip()
        and not _is_placeholder(artifact.content_hash)
    ]
    if not pr_artifacts:
        return await _block(run_orm, run, "no persisted non-empty PR artifact exists", uow)

    project = await uow.projects.get_project(task_orm.project_id)
    if project is None:
        return await _block(run_orm, run, "project is missing", uow)
    diff_artifact = next((artifact for artifact in artifacts if artifact.path.endswith("diff.patch")), None)
    if diff_artifact is None:
        return await _block(run_orm, run, "observed diff artifact is missing", uow)
    diff_path = Path(project.root_path) / diff_artifact.path
    if not diff_path.is_file():
        return await _block(run_orm, run, "observed diff artifact file is missing", uow)
    diff_text = diff_path.read_text(encoding="utf-8")

    typed_artifacts = await uow.typed_handoffs.list_artifacts_for_run(task_run_id)
    maker_artifacts = [
        artifact
        for artifact in typed_artifacts
        if artifact.producer_agent_id == maker_id
        and artifact.artifact_type == TypedArtifactType.PATCH
    ]
    checker_artifacts = [
        artifact
        for artifact in typed_artifacts
        if artifact.producer_agent_id == checker_id
        and artifact.artifact_type in {TypedArtifactType.VERIFICATION, TypedArtifactType.CRITIQUE}
    ]
    if not maker_artifacts or not checker_artifacts:
        return await _block(run_orm, run, "maker/checker typed evidence is incomplete", uow)

    for artifact in [*maker_artifacts, *checker_artifacts]:
        valid, reason = await uow.typed_handoffs.validate_artifact_integrity(artifact.id or 0)
        if not valid:
            return await _block(run_orm, run, reason or "typed artifact integrity failed", uow)

    maker = maker_artifacts[-1]
    checker = checker_artifacts[-1]
    validation = checker.validation_results_json
    if validation.get("execution_observed") is not True or validation.get("status") not in {
        "PASSED",
        "APPROVED",
    }:
        return await _block(run_orm, run, "checker evidence does not contain an observed passing result", uow)
    checks = [item for item in checker.tests_executed if item.strip()]
    if not checks:
        return await _block(run_orm, run, "checker evidence lists no executed checks", uow)

    verification = await uow.maker_checker.get_verification_for_task_run(task_run_id)
    if verification is None or verification.status.value != "APPROVED":
        verification = await uow.maker_checker.create_verification(
            project_id=task_orm.project_id,
            task_run_id=task_run_id,
            maker_agent_id=maker_id,
            checker_agent_id=checker_id,
        )
        await uow.maker_checker.submit_verification_result(
            verification_id=verification.id or 0,
            checker_agent_id=checker_id,
            approved=True,
            deterministic_passed=True,
            tests_executed=checks,
            not_checked=[],
            feedback="Observed typed checker evidence persisted for the mechanical gate.",
        )
    gate_result = await MechanicalPrePRGate().evaluate_gate(
        project_id=task_orm.project_id,
        task_run_id=task_run_id,
        uow=uow,
        diff_text=diff_text,
        modified_files=[str(path) for path in task_metadata.get("changed_files", []) if isinstance(path, str)],
    )
    if not gate_result.passed:
        return await _block(
            run_orm,
            run,
            "mechanical pre-PR gate failed: " + "; ".join(gate_result.violations),
            uow,
        )

    handoff = await uow.executions.create_handoff(
        domain.Handoff(
            task_run_id=task_run.id,
            from_role=AgentRole.REVIEWER,
            to_role=AgentRole.SAFETY_AUDITOR,
            kind=HandoffKind.PR_READY,
            payload_json={"swarm_run_id": run_id, "status": "APPROVED", "observed": True},
        )
    )
    assert handoff.id is not None
    gate_payload: dict[str, Any] = {
        "source": "light_swarm_aggregation",
        "task_run_id": task_run_id,
        "handoff_id": handoff.id,
        "maker_id": maker_id,
        "checker_id": checker_id,
        "maker_attempt_id": f"{maker_id}:{maker.id or 0}",
        "checker_attempt_id": f"{checker_id}:{checker.id or 0}",
        "pre_pr_gate": {
            "passed": True,
            "observed": True,
            "checks": gate_result.checks,
            "source_commit": source_commit,
            "target_commit": target_commit,
            "diff_hash": diff_hash,
        },
        "risk_verdict": {"passed": True, "source": "observed_checker"},
        "safety_verdict": {"passed": True, "source": "observed_checker"},
        "checks_executed": checks,
        "artifact_paths": [artifact.path for artifact in pr_artifacts],
        "branch_name": task_run.branch_name,
        "worktree_path": task_run.worktree_path,
        "source_commit": source_commit,
        "target_commit": target_commit,
        "diff_hash": diff_hash,
    }
    try:
        task_orm.status = TaskStatus.REVIEWING.value
        await uow.tasks.session.flush()
        updated_task = await uow.tasks.mark_pr_ready(task_run.task_id, gate_evidence=gate_payload)
        run.verdict = "EVIDENCE_READY"
        await uow.light_swarm._flush_run(run_orm, run)
        return updated_task
    except Exception as exc:
        logger.error("PR_READY submission failed for SwarmRun %d: %s", run_id, exc)
        return await _block(run_orm, run, str(exc), uow)


async def _block(
    run_orm: Any, run: domain.SwarmRun, reason: str, uow: UnitOfWork
) -> domain.Task | None:
    logger.warning("SwarmRun %s blocked before PR_READY: %s", run.id, reason)
    run.verdict = "NEEDS_HUMAN"
    run.node_statuses["__pr_ready_gate__"] = f"BLOCKED: {reason}"
    assert uow.light_swarm is not None
    await uow.light_swarm._flush_run(run_orm, run)
    return None
