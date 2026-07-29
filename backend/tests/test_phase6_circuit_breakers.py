import pytest
from localforge.models import domain
from localforge.models.enums import (
    CircuitScope,
    CircuitState,
    LeaseReleaseReason,
    LoopRunStatus,
    ProgressSignal,
    RunnerLane,
    RunStatus,
    TaskRunStatus,
    TriggerKind,
    WorktreeAttemptStatus,
)
from localforge.services.fingerprint import (
    evaluate_attempt_progress,
    generate_error_fingerprint,
)
from localforge.storage import UnitOfWork


def test_error_normalization_and_fingerprinting() -> None:
    """Test V6-200: Normalization strips memory addresses, timestamps, and local paths."""
    raw_err_1 = "ValueError: Failed at 0x7f9a8c001230 in E:\\Projetos\\local_forge_os\\test.py at 2026-07-28T01:23:45Z"
    raw_err_2 = "ValueError: Failed at 0x10b34d998000 in C:\\Users\\Adilio\\AppData\\test.py at 2026-07-28T02:00:00Z"

    fp_1 = generate_error_fingerprint(
        "ValueError", raw_err_1, "E:\\Projetos\\local_forge_os\\test.py:42"
    )
    fp_2 = generate_error_fingerprint(
        "ValueError", raw_err_2, "C:\\Users\\Adilio\\AppData\\test.py:42"
    )

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

        proj = domain.Project(
            name="CB Error Test", root_path="E:/tmp/cb_err_test", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        proj_id = project.id
        assert proj_id is not None

        fp = generate_error_fingerprint("ConnectionError", "Failed to reach model endpoint 0x123")

        # Record 2 failures (threshold = 3)
        b1 = await uow.circuit_breakers.record_failure(
            proj_id, CircuitScope.LOOP, "loop_101", fp, max_identical=3
        )
        assert b1.state == CircuitState.CLOSED
        assert b1.consecutive_failures == 1

        b2 = await uow.circuit_breakers.record_failure(
            proj_id, CircuitScope.LOOP, "loop_101", fp, max_identical=3
        )
        assert b2.state == CircuitState.CLOSED
        assert b2.consecutive_failures == 2

        # 3rd identical failure trips the breaker to OPEN
        b3 = await uow.circuit_breakers.record_failure(
            proj_id, CircuitScope.LOOP, "loop_101", fp, max_identical=3
        )
        assert b3.state == CircuitState.OPEN
        assert "identical failure" in (b3.reason or "")

        # Check breaker prevents execution
        can_proceed, state, reason = await uow.circuit_breakers.check_breaker(
            proj_id, CircuitScope.LOOP, "loop_101"
        )
        assert can_proceed is False
        assert state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_stagnation_trip(db_manager) -> None:
    """Test V6-201 & V6-202: Breaker trips after consecutive stagnation attempts."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.circuit_breakers is not None

        proj = domain.Project(
            name="CB Stagnation Test", root_path="E:/tmp/cb_stag_test", default_branch="main"
        )
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

        await uow.circuit_breakers.record_progress_signal(
            proj_id, CircuitScope.RUN, "run_202", stag_record, max_stagnation=3
        )
        await uow.circuit_breakers.record_progress_signal(
            proj_id, CircuitScope.RUN, "run_202", stag_record, max_stagnation=3
        )
        b3 = await uow.circuit_breakers.record_progress_signal(
            proj_id, CircuitScope.RUN, "run_202", stag_record, max_stagnation=3
        )

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

        proj = domain.Project(
            name="CB Block Test", root_path="E:/tmp/cb_block_test", default_branch="main"
        )
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
        await uow.circuit_breakers.record_failure(
            proj_id, CircuitScope.LOOP, str(loop_id), fp, max_identical=1
        )

        # Attempt to trigger loop -> ValueError raised due to open breaker
        with pytest.raises(ValueError, match="blocked by Circuit Breaker"):
            await uow.loop_coordinator.trigger_loop(
                loop_id=loop_id,
                trigger_kind=TriggerKind.MANUAL,
                idempotency_key="cb_blocked_key_001",
            )

        # Reset breaker
        reset_b = await uow.circuit_breakers.reset_breaker(
            proj_id, CircuitScope.LOOP, str(loop_id), actor_id="admin"
        )
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
        assert uow.tasks is not None
        assert uow.executions is not None
        assert uow.path_leases is not None
        assert uow.runner_pool is not None
        assert uow.worktrees is not None

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
            payload={
                "force_actionable": True,
                "items": [{"external_id": "kill-item", "title": "Kill test item"}],
            },
        )

        assert run.id is not None
        assert run.scheduler_run_id is not None
        assert run.triage_task_ids

        task_run = await uow.tasks.create_task_run(
            domain.TaskRun(
                run_id=run.scheduler_run_id,
                task_id=run.triage_task_ids[0],
                status=TaskRunStatus.RUNNING,
            )
        )
        assert task_run.id is not None
        lease, _, _ = await uow.path_leases.acquire_lease(
            project_id=proj_id,
            task_run_id=task_run.id,
            owner_id="loop-worker",
            target_path="src/killable.py",
        )
        assert lease is not None
        worktree_manifest = await uow.worktrees.create_attempt_manifest(
            project_id=proj_id,
            task_id=run.triage_task_ids[0],
            task_run_id=task_run.id,
            worktree_path="E:/tmp/kill_test/.localforge/worktrees/kill-item",
            branch_name="lf/kill-item",
            source_commit="abc123",
            owner_agent_id="loop-worker",
        )
        assert worktree_manifest.status == WorktreeAttemptStatus.ACTIVE

        await uow.runner_pool.register_runner(
            runner_id="runner-kill",
            name="Kill Runner",
            lane=RunnerLane.INLINE,
            max_concurrency=1,
        )
        _, dispatch_status, dispatch_log = await uow.runner_pool.dispatch_task(
            project_id=proj_id,
            task_run_id=task_run.id,
            required_lane=RunnerLane.INLINE,
        )
        assert dispatch_status == "SUCCESS"
        assert dispatch_log.selected_runner_id == "runner-kill"

        # Kill run
        killed_run = await uow.loop_coordinator.kill_loop_run(
            run.id, actor_id="user_admin", reason="Emergency stop"
        )
        assert killed_run.status == LoopRunStatus.CANCELLED

        assert "Killed by user_admin" in (killed_run.error_message or "")

        scheduler_run = await uow.executions.get_run(run.scheduler_run_id)
        assert scheduler_run is not None
        assert scheduler_run.status == RunStatus.CANCELLED

        cancelled_task_run = await uow.tasks.get_task_run(task_run.id)
        assert cancelled_task_run is not None
        assert cancelled_task_run.status == TaskRunStatus.CANCELLED

        active_leases = await uow.path_leases.list_active_leases(proj_id)
        assert active_leases == []
        released_lease = await uow.path_leases.release_lease(
            lease.id or 0, LeaseReleaseReason.CANCELLED
        )
        assert released_lease is not None
        assert released_lease.release_reason == LeaseReleaseReason.CANCELLED

        runner_state = (await uow.runner_pool.list_runners())[0]
        assert runner_state.active_tasks_count == 0
        dispatch_logs = await uow.runner_pool.list_dispatch_logs_for_task_run(task_run.id)
        assert dispatch_logs[0].dispatch_status == "CANCELLED"
        cancelled_manifest = await uow.worktrees.get_manifest_by_task_run(task_run.id)
        assert cancelled_manifest is not None
        assert cancelled_manifest.status == WorktreeAttemptStatus.CANCELLED

        killed_again = await uow.loop_coordinator.kill_loop_run(
            run.id, actor_id="user_admin", reason="Emergency stop"
        )
        assert killed_again.status == LoopRunStatus.CANCELLED
        runner_state_after_repeat = (await uow.runner_pool.list_runners())[0]
        assert runner_state_after_repeat.active_tasks_count == 0
