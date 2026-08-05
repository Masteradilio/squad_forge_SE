from localforge.control_plane import (
    BoundedWorkerBridge,
    ControlPlaneKernel,
    ControlPlaneStore,
    GoalRegistry,
    PersistentRunnerPolicy,
    PersistentWorkerRunner,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
    TurnRoute,
    goal_id_for_project,
    state_path_for_goal,
)


def _kernel(tmp_path):
    kernel = ControlPlaneKernel(ControlPlaneStore(tmp_path / "control-plane.json"))
    kernel.start(
        goal_id="project:test:goal",
        vision="finish a tiny product",
        non_negotiables=["preserve evidence"],
        tasks=[TaskSnapshot(todo_id="A", title="first", status="READY")],
        source_revision="commit-1",
        acceptance_target="all_tasks_pr_ready",
    )
    return kernel


def test_goal_registry_reconnects_without_rebuilding_control_state(tmp_path):
    registry = GoalRegistry(tmp_path / "registry.json")
    first = registry.connect(
        goal_id="project:test:goal",
        workspace=tmp_path,
        state_path=tmp_path / "control-plane.json",
        source_revision="commit-1",
    )
    second = GoalRegistry(tmp_path / "registry.json").get("project:test:goal")
    assert second is not None
    assert second.state_path == first.state_path
    assert second.source_revision == "commit-1"
    assert len(registry.list()) == 1


def test_goal_binding_is_stable_across_runs_and_supports_explicit_goal_ids(tmp_path):
    default = goal_id_for_project(7, {})
    same_default = goal_id_for_project(7, {"source_revision": "next-run"})
    explicit = goal_id_for_project(7, {"goal_id": "prd:health-check"})

    assert default == same_default == "project:7:lifetime"
    assert explicit == "prd:health-check"
    assert state_path_for_goal(tmp_path, default, "db.sqlite") == state_path_for_goal(
        tmp_path, default, "db.sqlite"
    )
    assert state_path_for_goal(tmp_path, default, "db.sqlite") != state_path_for_goal(
        tmp_path, explicit, "db.sqlite"
    )


def test_bounded_worker_bridge_claims_and_writes_one_turn(tmp_path):
    kernel = _kernel(tmp_path)
    bridge = BoundedWorkerBridge(kernel)
    tick = bridge.execute_once(
        "worker-1",
        lambda decision: TurnResult(
            todo_id=decision.todo_id or "missing",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_COMPLETION,
            summary="validated",
            evidence={"check": "unit"},
            validated_by="checker",
            idempotency_key="worker-v9-a",
        ),
    )
    assert tick.decision.route == TurnRoute.READY
    assert tick.state is not None
    assert tick.state.goal.status.value == "COMPLETED"
    assert tick.state.goal.last_receipt_id is not None


def test_persistent_runner_completes_goal_with_bounded_backoff_contract(tmp_path):
    kernel = _kernel(tmp_path)
    runner = PersistentWorkerRunner(
        kernel,
        lambda decision: TurnResult(
            todo_id=decision.todo_id or "missing",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_COMPLETION,
            summary="validated by persistent runner",
            validated_by="test-runner",
            idempotency_key="persistent-v9-a",
        ),
        sleeper=lambda _: None,
    )

    outcome = runner.run(
        PersistentRunnerPolicy(owner="runner", lease_seconds=60, max_ticks=2)
    )

    assert outcome.status == "COMPLETED"
    assert outcome.ticks == 1
    assert outcome.progress_events == 1
    assert kernel.status() is not None
    assert kernel.status().goal.status.value == "COMPLETED"


def test_persistent_runner_recovers_expired_lease_after_restart(tmp_path):
    kernel = _kernel(tmp_path)
    claimed = kernel.next_turn("old-worker", lease_seconds=60)

    def expire(state):
        state.todos[0].lease_expires_at = "2000-01-01T00:00:00+00:00"
        return state

    kernel.store.update(expire, operation_id="test:persistent-expiry")
    restarted = ControlPlaneKernel(ControlPlaneStore(tmp_path / "control-plane.json"))
    runner = PersistentWorkerRunner(
        restarted,
        lambda decision: TurnResult(
            todo_id=decision.todo_id or "missing",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_COMPLETION,
            summary="resumed",
            validated_by="replacement-worker",
            idempotency_key="persistent-v9-recovered",
        ),
        sleeper=lambda _: None,
    )

    outcome = runner.run(
        PersistentRunnerPolicy(owner="replacement-worker", lease_seconds=60, max_ticks=2)
    )

    assert outcome.status == "COMPLETED"
    state = restarted.status()
    assert state is not None
    assert any(
        event["event"] == "lease_expired_recovered"
        and event["turn_id"] == claimed.turn_id
        for event in state.events
    )


def test_persistent_runner_wakes_for_external_signal_before_spending(tmp_path):
    kernel = _kernel(tmp_path)
    kernel.record_signal(
        signal_id="provider-1",
        signal_type="provider.recovered",
        source="omniroute",
        payload={"status": 200},
        fingerprint="provider-recovered-1",
    )
    observed: list[str] = []

    def on_signal(signal: dict[str, object]) -> None:
        observed.append(str(signal["signal_id"]))
        kernel.acknowledge_signal(str(signal["signal_id"]))

    runner = PersistentWorkerRunner(
        kernel,
        lambda decision: TurnResult(
            todo_id=decision.todo_id or "missing",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_COMPLETION,
            summary="signal wakeup continued work",
            validated_by="signal-runner",
            idempotency_key="persistent-v9-signal",
        ),
        on_signal=on_signal,
        sleeper=lambda _: None,
    )

    outcome = runner.run(
        PersistentRunnerPolicy(owner="signal-worker", lease_seconds=60, max_ticks=3)
    )

    assert outcome.status == "COMPLETED"
    assert outcome.signal_wakeups == 1
    assert observed == ["provider-1"]


def test_persistent_runner_bounds_quiet_wait_cycles(tmp_path):
    kernel = _kernel(tmp_path)
    kernel.next_turn("busy-worker", lease_seconds=60)
    sleeps: list[float] = []
    runner = PersistentWorkerRunner(
        kernel,
        lambda decision: (_ for _ in ()).throw(AssertionError("no claim expected")),
        sleeper=sleeps.append,
    )

    outcome = runner.run(
        PersistentRunnerPolicy(
            owner="waiting-worker",
            lease_seconds=60,
            base_backoff_seconds=1,
            max_backoff_seconds=2,
            max_ticks=2,
        )
    )

    assert outcome.status == "EXHAUSTED"
    assert outcome.ticks == 2
    assert sleeps == [1, 2]


def test_worker_bridge_does_not_claim_when_goal_is_complete(tmp_path):
    kernel = _kernel(tmp_path)
    bridge = BoundedWorkerBridge(kernel)
    first = bridge.claim("worker")
    bridge.writeback(
        TurnResult(
            todo_id="A",
            turn_id=first.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_COMPLETION,
            summary="done",
            validated_by="checker",
            idempotency_key="complete-v9-a",
        )
    )
    decision = bridge.claim("worker")
    assert decision.route == TurnRoute.COMPLETE


def test_attention_queue_and_capability_promotion_are_durable(tmp_path):
    kernel = _kernel(tmp_path)
    kernel.record_signal(
        signal_id="ci-1",
        signal_type="ci.failed",
        source="github",
        payload={"todo_id": "A", "conclusion": "failure"},
        fingerprint="commit-1:ci",
    )
    kernel.propose_capability(
        proposal_id="cap-1",
        capability="bounded-heartbeat",
        description="Wake one worker turn at a time",
        isolated_scope=["backend/localforge/control_plane"],
        proposed_by="chief",
    )
    packet = kernel.review_packet()
    assert packet["attention_queue"][0]["kind"] == "external_signal"
    kernel.validate_capability("cap-1", evidence={"tests": ["unit"]}, validated_by="reviewer")
    promoted = kernel.promote_capability("cap-1", promoted_by="human")
    assert promoted.capability_proposals[0].status.value == "PROMOTED"
    acknowledged = kernel.acknowledge_signal("ci-1")
    assert acknowledged.signals[0].acknowledged_at is not None
