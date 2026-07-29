import pytest
from localforge.models import domain
from localforge.models.enums import (
    ActionKind,
    AutonomyEnforcementResult,
    AutonomyLevel,
    VerificationStatus,
)
from localforge.storage import UnitOfWork


def test_autonomy_level_action_permissions() -> None:
    """Test V6-300 & V6-301: Server enforcement of L0-L3 action boundaries."""
    from localforge.services.autonomy import AutonomyService

    service = AutonomyService()

    # L0_SIMULATE: file write, command execution, pr_ready, merge all DENIED
    ok, res, _ = service.evaluate_action(
        AutonomyLevel.L0_SIMULATE, ActionKind.WRITE_FILE, "test.py"
    )
    assert ok is False
    assert res == AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED

    ok, res, _ = service.evaluate_action(AutonomyLevel.L0_SIMULATE, ActionKind.RUN_COMMAND, "ls")
    assert ok is False

    # L1_INSPECT: file write DENIED, command execution ALLOWED (inspection)
    ok, res, _ = service.evaluate_action(AutonomyLevel.L1_INSPECT, ActionKind.WRITE_FILE, "test.py")
    assert ok is False

    ok, res, _ = service.evaluate_action(
        AutonomyLevel.L1_INSPECT, ActionKind.RUN_COMMAND, "git status"
    )
    assert ok is True
    assert res == AutonomyEnforcementResult.ALLOWED

    # L2_ISOLATED: file write ALLOWED, pr_ready DENIED
    ok, res, _ = service.evaluate_action(
        AutonomyLevel.L2_ISOLATED, ActionKind.WRITE_FILE, "test.py"
    )
    assert ok is True

    ok, res, _ = service.evaluate_action(AutonomyLevel.L2_ISOLATED, "pr_ready")
    assert ok is False

    # L3_UNATTENDED: pr_ready ALLOWED, git_merge ALWAYS DENIED
    ok, res, _ = service.evaluate_action(AutonomyLevel.L3_UNATTENDED, "pr_ready")
    assert ok is True

    ok, res, _ = service.evaluate_action(AutonomyLevel.L3_UNATTENDED, "git_merge")
    assert ok is False
    assert res == AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED


@pytest.mark.asyncio
async def test_maker_checker_self_verification_rejected(db_manager) -> None:
    """Test V6-302: Rejection of self-verification when maker and checker share identical ID."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.maker_checker is not None

        proj = domain.Project(
            name="Self Verification Test", root_path="E:/tmp/self_ver", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = domain.Task(
            project_id=project.id,
            key="TSK-01",
            title="Self ver task",
            description="Test self approval",
        )
        created_task = await uow.tasks.create_task(task)
        assert created_task.id is not None

        task_run = await uow.tasks.create_task_run(
            domain.TaskRun(task_id=created_task.id, run_id=1)
        )
        assert task_run.id is not None

        # Attempt to create verification with same agent ID for maker and checker -> ValueError
        with pytest.raises(ValueError, match="Self-verification rejected"):
            await uow.maker_checker.create_verification(
                project_id=project.id,
                task_run_id=task_run.id,
                maker_agent_id="agent_dev_001",
                checker_agent_id="agent_dev_001",
            )


@pytest.mark.asyncio
async def test_maker_checker_role_spoofing_and_pr_ready(db_manager) -> None:
    """Test V6-302 & V6-303: Independent verification approval and PR_READY eligibility."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.maker_checker is not None

        proj = domain.Project(
            name="Maker Checker Test", root_path="E:/tmp/mc_test", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = domain.Task(
            project_id=project.id, key="TSK-02", title="Feature task", description="Add new feature"
        )

        created_task = await uow.tasks.create_task(task)
        assert created_task.id is not None

        task_run = await uow.tasks.create_task_run(
            domain.TaskRun(task_id=created_task.id, run_id=1)
        )

        assert task_run.id is not None

        # Create valid verification assignment with distinct Maker and Checker
        ver = await uow.maker_checker.create_verification(
            project_id=project.id,
            task_run_id=task_run.id,
            maker_agent_id="developer_agent_01",
            checker_agent_id="qa_reviewer_agent_02",
        )
        assert ver.id is not None
        assert ver.status == VerificationStatus.PENDING

        # Check PR_READY eligibility before approval -> Ineligible
        eligible, reason = await uow.maker_checker.verify_pr_ready_eligibility(
            task_run_id=task_run.id
        )
        assert eligible is False
        assert "PENDING" in reason

        # Role spoofing test: maker attempts to submit checker decision -> DENIED_ROLE_SPOOFING
        _, code, reason_spoof = await uow.maker_checker.submit_verification_result(
            verification_id=ver.id,
            checker_agent_id="developer_agent_01",  # Not assigned checker!
            approved=True,
            deterministic_passed=True,
            tests_executed=["test_feature.py"],
            not_checked=[],
        )
        assert code == AutonomyEnforcementResult.DENIED_ROLE_SPOOFING
        assert "Role spoofing rejected" in reason_spoof

        # Failed deterministic test -> Approval rejected
        _, code_det, _ = await uow.maker_checker.submit_verification_result(
            verification_id=ver.id,
            checker_agent_id="qa_reviewer_agent_02",
            approved=True,
            deterministic_passed=False,  # Failed unit tests!
            tests_executed=["test_feature.py"],
            not_checked=[],
        )
        assert code_det == AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED

        # Valid independent approval by assigned checker
        updated_ver, code_ok, reason_ok = await uow.maker_checker.submit_verification_result(
            verification_id=ver.id,
            checker_agent_id="qa_reviewer_agent_02",
            approved=True,
            deterministic_passed=True,
            tests_executed=["test_feature.py::test_success"],
            not_checked=["ui_visual_inspection"],
            feedback="Code quality is clean and 100% tests pass.",
        )
        assert code_ok == AutonomyEnforcementResult.ALLOWED
        assert updated_ver.status == VerificationStatus.APPROVED

        # Re-check PR_READY eligibility -> Eligible!
        eligible_now, reason_now = await uow.maker_checker.verify_pr_ready_eligibility(
            task_run_id=task_run.id
        )
        assert eligible_now is True
        assert "valid independent verification" in reason_now
