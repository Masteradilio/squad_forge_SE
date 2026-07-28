import pytest

from localforge.models import domain
from localforge.models.enums import CircuitScope, CircuitState, LoopRunStatus, ProgressSignal, TriggerKind

from localforge.services.fingerprint import (
    compute_diff_signature,
    compute_test_signature,
    evaluate_attempt_progress,
    generate_error_fingerprint,
    normalize_error_message,
)
from localforge.storage import UnitOfWork


def test_error_normalization_and_fingerprinting() -> None:
    """Test V6-200: Normalization strips memory addresses, timestamps, and local paths."""
    raw_err_1 = "ValueError: Failed at 0x7f9a8c001230 in E:\\Projetos\\local_forge_os\\test.py at 2026-07-28T01:23:45Z"
    raw_err_2 = "ValueError: Failed at 0x10b34d998000 in C:\\Users\\Adilio\\AppData\\test.py at 2026-07-28T02:00:00Z"

    fp_1 = generate_error_fingerprint("ValueError", raw_err_1, "E:\\Projetos\\local_forge_os\\test.py:42")
    fp_2 = generate_error_fingerprint("ValueError", raw_err_2, "C:\\Users\\Adilio\\AppData\\test.py:42")

    # Hashes must match despite different memory addresses, paths, and timestamps
    assert fp_1.fingerprint_hash == fp_2.fingerprint_hash
    assert fp_1.normalized_message == fp_2.normalized_message


def test_progress_signal_evaluation() -> None:
    """Test V6-200: Classify progress, stagnation, regression, and repeated failure."""
    attempt_1 = evaluate_attempt_progress(
        previous_attempt=None,
        current_attempt_num=1,
        current_test_sig="sig_tests_v1",
        current_diff_sig="sig_diff_v1",
        current_artifact_sig="sig_art_v1",
        current_fingerprint_hash="fp_123",
        failed_test_count=2,
    )
    assert attempt_1.signal == ProgressSignal.STAGNATION

    # Identical fingerprint repeated -> REPEATED_FAILURE
    attempt_2 = evaluate_attempt_progress(
        previous_attempt=attempt_1,
        current_attempt_num=2,
        current_test_sig="sig_tests_v1",
        current_diff_sig="sig_diff_v1",
        current_artifact_sig="sig_art_v1",
        current_fingerprint_hash="fp_123",
        failed_test_count=2,
    )
    assert attempt_2.signal == ProgressSignal.REPEATED_FAILURE

    # Failed tests increased -> REGRESSION
    attempt_3 = evaluate_attempt_progress(
        previous_attempt=attempt_1,
        current_attempt_num=3,
        current_test_sig="sig_tests_v2",
        current_diff_sig="sig_diff_v2",
        current_artifact_sig="sig_art_v1",
        current_fingerprint_hash="fp_456",
        failed_test_count=4,
        previous_failed_test_count=2,
    )
    assert attempt_3.signal == ProgressSignal.REGRESSION

    # Failed tests decreased -> PROGRESS
    attempt_4 = evaluate_attempt_progress(
        previous_attempt=attempt_3,
        current_attempt_num=4,
        current_test_sig="sig_tests_v3",
        current_diff_sig="sig_diff_v3",
        current_artifact_sig="sig_art_v1",
        current_fingerprint_hash="fp_789",
        failed_test_count=1,
        previous_failed_test_count=4,
    )
    assert attempt_4.signal == ProgressSignal.PROGRESS


@pytest.mark.asyncio
async def test_circuit_breaker_identical_error_trip(db_manager) -> None:
    """Test V6-201 & V6-202: Breaker trips after identical error threshold exceeded."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.circuit_breakers is not None

        proj = domain.Project(name="CB Error Test", root_path="E:/tmp/cb_err_test", default_branch="main")
        project = await uow.projects.create_project(proj)
        proj_id = project.id
        assert proj_id is not None

        fp = generate_error_fingerprint("ConnectionError", "Failed to reach model endpoint 0x123")

        # Record 2 failures (threshold = 3)
        b1 = await uow.circuit_breakers.record_failure(proj_id, CircuitScope.LOOP, "loop_101", fp, max_identical=3)
        assert b1.state == CircuitState.CLOSED
        assert b1.consecutive_failures == 1

        b2 = await uow.circuit_breakers.record_failure(proj_id, CircuitScope.LOOP, "loop_101", fp, max_identical=3)
        assert b2.state == CircuitState.CLOSED
        assert b2.consecutive_failures == 2

        # 3rd identical failure trips the breaker to OPEN
        b3 = await uow.circuit_breakers.record_failure(proj_id, CircuitScope.LOOP, "loop_101", fp, max_identical=3)
        assert b3.state == CircuitState.OPEN
        assert "identical failure" in (b3.reason or "")

        # Check breaker prevents execution
        can_proceed, state, reason = await uow.circuit_breakers.check_breaker(proj_id, CircuitScope.LOOP, "loop_101")
        assert can_proceed is False
        assert state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_stagnation_trip(db_manager) -> None:
    """Test V6-201 & V6-202: Breaker trips after consecutive stagnation attempts."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.circuit_breakers is not None

        proj = domain.Project(name="CB Stagnation Test", root_path="E:/tmp/cb_stag_test", default_branch="main")
        project = await uow.projects.create_project(proj)
        proj_id = project.id
        assert proj_id is not None

        stag_record = domain.AttemptProgressRecord(
            attempt_number=1,
            test_signature="same_tests",
            diff_signature="same_diff",
            artifact_signature="same_art",
            signal=ProgressSignal.STAGNATION,
        )

        await uow.circuit_breakers.record_progress_signal(proj_id, CircuitScope.RUN, "run_202", stag_record, max_stagnation=3)
        await uow.circuit_breakers.record_progress_signal(proj_id, CircuitScope.RUN, "run_202", stag_record, max_stagnation=3)
        b3 = await uow.circuit_breakers.record_progress_signal(proj_id, CircuitScope.RUN, "run_202", stag_record, max_stagnation=3)

        assert b3.state == CircuitState.OPEN
        assert b3.stagnation_count == 3
        assert "no progress detected" in (b3.reason or "")


@pytest.mark.asyncio
async def test_circuit_breaker_reset_and_loop_coordination_block(db_manager) -> None:
    """Test V6-202 & V6-203: Open circuit breaker blocks loop trigger, manual reset unblocks it."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None
        assert uow.circuit_breakers is not None

        proj = domain.Project(name="CB Block Test", root_path="E:/tmp/cb_block_test", default_branch="main")
        project = await uow.projects.create_project(proj)
        proj_id = project.id
        assert proj_id is not None

        loop_def = domain.LoopDefinition(
            project_id=proj_id,
            name="CB Protected Loop",
            repository_path="E:/tmp/cb_block_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)
        loop_id = created_loop.id
        assert loop_id is not None

        # Trip breaker for this loop
        fp = generate_error_fingerprint("FatalError", "Database corrupt")
        await uow.circuit_breakers.record_failure(proj_id, CircuitScope.LOOP, str(loop_id), fp, max_identical=1)

        # Attempt to trigger loop -> ValueError raised due to open breaker
        with pytest.raises(ValueError, match="blocked by Circuit Breaker"):
            await uow.loop_coordinator.trigger_loop(
                loop_id=loop_id,
                trigger_kind=TriggerKind.MANUAL,
                idempotency_key="cb_blocked_key_001",
            )

        # Reset breaker
        reset_b = await uow.circuit_breakers.reset_breaker(proj_id, CircuitScope.LOOP, str(loop_id), actor_id="admin")
        assert reset_b.state == CircuitState.CLOSED

        # Now trigger succeeds
        run = await uow.loop_coordinator.trigger_loop(
            loop_id=loop_id,
            trigger_kind=TriggerKind.MANUAL,
            idempotency_key="cb_unblocked_key_002",
            payload={"force_noop": True},
        )
        assert run.id is not None


@pytest.mark.asyncio
async def test_kill_loop_run(db_manager) -> None:
    """Test V6-203: Kill operation cancels run, updates status, and logs audit event."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.loops is not None
        assert uow.loop_coordinator is not None

        proj = domain.Project(name="Kill Test", root_path="E:/tmp/kill_test", default_branch="main")
        project = await uow.projects.create_project(proj)
        proj_id = project.id
        assert proj_id is not None

        loop_def = domain.LoopDefinition(
            project_id=proj_id,
            name="Killable Loop",
            repository_path="E:/tmp/kill_test",
        )
        created_loop = await uow.loops.create_loop(loop_def)

        # Create active run
        run = await uow.loop_coordinator.trigger_loop(
            loop_id=created_loop.id,  # type: ignore[arg-type]
            trigger_kind=TriggerKind.MANUAL,
            idempotency_key="kill_key_001",
            payload={"force_actionable": True},
        )

        assert run.id is not None

        # Kill run
        killed_run = await uow.loop_coordinator.kill_loop_run(run.id, actor_id="user_admin", reason="Emergency stop")
        assert killed_run.status == LoopRunStatus.CANCELLED

        assert "Killed by user_admin" in (killed_run.error_message or "")
