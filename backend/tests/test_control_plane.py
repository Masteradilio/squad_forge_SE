from localforge.control_plane import (
    AgentIdentity,
    GateState,
)
from localforge.control_plane import (
    ControlPlaneKernel,
    ControlPlaneStore,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
    TurnRoute,
)


def _kernel(tmp_path):
    return ControlPlaneKernel(ControlPlaneStore(tmp_path / "control-plane.json"))


def _started(kernel: ControlPlaneKernel, *, max_turns: int = 10):
    return kernel.start(
        goal_id="run:test",
        vision="finish the bounded fixture",
        non_negotiables=["keep evidence"],
        tasks=[
            TaskSnapshot(todo_id="A", title="first", status="READY"),
            TaskSnapshot(todo_id="B", title="second", status="READY", dependencies=["A"]),
        ],
        max_turns=max_turns,
    )


def test_control_plane_survives_restart_and_claims_dependency_order(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)

    first = kernel.next_turn("worker-1")
    assert first.route == TurnRoute.READY
    assert first.todo_id == "A"

    restarted = _kernel(tmp_path)
    state = restarted.status()
    assert state is not None
    assert state.revision > 0
    assert state.todos[0].status.value == "CLAIMED"

    restarted.record_result(
        TurnResult(
            todo_id="A",
            turn_id=first.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_PROGRESS,
            summary="A passed its checks",
            evidence={"checks": ["unit"]},
            validated_by="checker",
            idempotency_key="result-a-1",
        )
    )
    second = restarted.next_turn("worker-1")
    assert second.route == TurnRoute.READY
    assert second.todo_id == "B"


def test_control_plane_writeback_is_idempotent_and_completes_goal(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker")
    result = TurnResult(
        todo_id="A",
        turn_id=decision.turn_id or "missing",
        result_kind=TurnResultKind.VALIDATED_COMPLETION,
        summary="done",
        validated_by="checker",
        idempotency_key="same-result",
    )
    first = kernel.record_result(result)
    second = kernel.record_result(result)
    assert len(first.receipts) == len(second.receipts) == 1
    assert second.quota.turns_committed == 1


def test_control_plane_routes_blockers_to_repair_without_claiming_next_task(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker")
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATION_FAILED,
            summary="test command failed",
            validated_by="checker",
            idempotency_key="blocked-a",
        )
    )
    repair = kernel.next_turn("worker")
    assert repair.route == TurnRoute.REPAIR
    assert repair.todo_id == "A"
    assert "test command failed" in repair.reason


def test_control_plane_records_repair_handoff_and_reopens_after_writeback(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker")
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATION_FAILED,
            summary="syntax error",
            validated_by="checker",
            idempotency_key="repair-a",
        )
    )
    kernel.record_repair_handoff(
        todo_id="A",
        diagnosis="syntax error",
        evidence={"stderr": "line 1"},
        handoff_id="handoff-a-1",
    )
    reopened = kernel.reopen_after_repair(
        todo_id="A",
        summary="Chief repair validated",
        evidence={"checks": ["compile"]},
        handoff_id="handoff-a-1",
    )
    assert reopened.todos[0].status.value == "PENDING"
    assert any(event["event"] == "repair_handoff" for event in reopened.events)
    assert any(event["event"] == "repair_writeback" for event in reopened.events)


def test_control_plane_rejects_stale_turn_writeback(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker")
    try:
        kernel.record_result(
            TurnResult(
                todo_id="A",
                turn_id="stale-turn",
                result_kind=TurnResultKind.VALIDATED_PROGRESS,
                summary="stale",
                validated_by="checker",
                idempotency_key="stale-a",
            )
        )
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale writeback was accepted")


def test_control_plane_stops_new_turns_at_quota(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel, max_turns=1)
    decision = kernel.next_turn("worker")
    assert decision.route == TurnRoute.READY
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_PROGRESS,
            summary="done",
            validated_by="checker",
            idempotency_key="quota-a",
        )
    )
    assert kernel.next_turn("worker").route == TurnRoute.WAIT


def test_control_plane_abort_closes_claimed_lease_and_blocks_goal(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker")

    aborted = kernel.abort("worker process terminated by bounded watchdog")

    assert aborted.goal.status.value == "BLOCKED"
    assert aborted.todos[0].status.value == "BLOCKED"
    assert aborted.todos[0].lease_token is None
    assert aborted.todos[0].current_turn_id is None
    assert aborted.todos[0].last_error == "worker process terminated by bounded watchdog"
    assert any(event["event"] == "run_aborted" for event in aborted.events)
    assert kernel.next_turn("worker").route == TurnRoute.WAIT


def test_control_plane_replays_append_only_journal_without_claiming_work(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)

    packet = kernel.review_packet()
    state = kernel.status()
    assert state is not None
    assert packet["next_action"]["route"] == TurnRoute.READY.value
    assert state.todos[0].status.value == "PENDING"

    store = ControlPlaneStore(tmp_path / "control-plane.json")
    records = store.event_records()
    assert records
    assert store.verify_replay()
    replayed = store.replay()
    assert replayed is not None
    assert replayed.revision == state.revision


def test_control_plane_review_packet_exposes_machine_interaction_contract(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)

    packet = kernel.review_packet()

    contract = packet["interaction_contract"]
    assert contract["schema_version"] == "forgeos.interaction_contract.v1"
    assert contract["should_run"] is True
    assert contract["mode"] == "bounded_delivery"
    assert contract["primary_action"] == "claim_bounded_turn"
    assert contract["spend_allowed"] is True


def test_control_plane_renews_live_lease_idempotently(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker", lease_seconds=60)

    renewed = kernel.renew_lease(
        todo_id="A",
        turn_id=decision.turn_id or "missing",
        lease_token=decision.lease_token or "missing",
        owner="worker",
        lease_seconds=120,
        renewal_id="heartbeat-a-1",
    )
    repeated = kernel.renew_lease(
        todo_id="A",
        turn_id=decision.turn_id or "missing",
        lease_token=decision.lease_token or "missing",
        owner="worker",
        lease_seconds=120,
        renewal_id="heartbeat-a-1",
    )

    assert renewed.todos[0].lease_expires_at == repeated.todos[0].lease_expires_at
    assert sum(event["event"] == "lease_renewed" for event in repeated.events) == 1


def test_control_plane_reconciles_expired_lease_with_recovery_event(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    decision = kernel.next_turn("worker")

    def expire(state):
        state.todos[0].lease_expires_at = "2000-01-01T00:00:00+00:00"
        return state

    kernel.store.update(expire, operation_id="test:expire-lease")
    recovered = kernel.next_turn("replacement-worker")

    assert recovered.route == TurnRoute.READY
    state = kernel.status()
    assert state is not None
    assert any(
        event["event"] == "lease_expired_recovered"
        and event["turn_id"] == decision.turn_id
        for event in state.events
    )


def test_control_plane_unchanged_projection_does_not_spin_the_journal(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    store = ControlPlaneStore(tmp_path / "control-plane.json")
    before = store.read()
    assert before is not None
    kernel.sync_tasks(
        [
            TaskSnapshot(todo_id="A", title="first", status="READY"),
            TaskSnapshot(todo_id="B", title="second", status="READY", dependencies=["A"]),
        ]
    )
    after = store.read()
    assert after is not None
    assert after.revision == before.revision
    assert len(store.event_records()) == 1


def test_control_plane_deduplicates_external_signals_and_tracks_handoff(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    kernel.record_signal(
        signal_id="ci-1",
        signal_type="ci.completed",
        source="github",
        fingerprint="commit:abc",
        payload={"conclusion": "failure"},
    )
    second = kernel.record_signal(
        signal_id="ci-duplicate",
        signal_type="ci.completed",
        source="github",
        fingerprint="commit:abc",
        payload={"conclusion": "failure"},
    )
    assert len(second.signals) == 1

    decision = kernel.next_turn("worker")
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=decision.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATION_FAILED,
            summary="CI failed",
            validated_by="checker",
            idempotency_key="ci-failure",
        )
    )
    handed = kernel.record_repair_handoff(
        todo_id="A",
        diagnosis="CI failed",
        evidence={"run": "42"},
        handoff_id="handoff-ci-1",
    )
    assert handed.handoffs[0].status == "OPEN"
    reopened = kernel.reopen_after_repair(
        todo_id="A",
        summary="Chief repaired CI failure",
        evidence={"checks": ["pytest"]},
        handoff_id="handoff-ci-1",
    )
    assert reopened.handoffs[0].status == "REOPENED"


def test_control_plane_rejects_stale_frontier_revision(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    state = kernel.status()
    assert state is not None
    first = kernel.next_turn("worker", expected_revision=state.revision)
    assert first.route == TurnRoute.READY
    try:
        kernel.next_turn("other-worker", expected_revision=state.revision)
    except RuntimeError as exc:
        assert "expected revision" in str(exc)
    else:
        raise AssertionError("stale frontier revision was accepted")


def test_control_plane_scopes_gate_to_affected_lane_and_records_answer(tmp_path):
    kernel = _kernel(tmp_path)
    kernel.start(
        goal_id="run:gate",
        vision="finish gated work",
        non_negotiables=["keep the independent lane moving"],
        tasks=[
            TaskSnapshot(todo_id="A", title="independent", status="READY"),
            TaskSnapshot(todo_id="B", title="gated", status="READY"),
        ],
        gates=[
            GateState(
                gate_id="human-b",
                name="Approve B",
                question="May B proceed?",
                affected_todo_ids=["B"],
            )
        ],
    )
    first = kernel.next_turn("worker")
    assert first.route == TurnRoute.READY
    assert first.todo_id == "A"
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=first.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATED_PROGRESS,
            summary="A passed",
            validated_by="checker",
            idempotency_key="gate-a",
        )
    )
    gated = kernel.next_turn("worker")
    assert gated.route == TurnRoute.ASK
    assert gated.todo_id == "B"
    answered = kernel.answer_gate("human-b", "approved", answered_by="product-owner")
    assert answered.gates[0].status.value == "PASSED"
    assert answered.gates[0].answer_receipt_id
    assert kernel.next_turn("worker").route == TurnRoute.READY


def test_control_plane_registers_agent_capabilities_durably(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    state = kernel.register_agent(
        AgentIdentity(
            agent_id="chief",
            role="chief_engineer",
            capabilities=["repair"],
            allowed_actions=["write_allowed_files"],
            authority="chief",
        )
    )
    assert state.agents[0].agent_id == "chief"
    restarted = _kernel(tmp_path).status()
    assert restarted is not None
    assert restarted.agents[0].capabilities == ["repair"]


def test_control_plane_hash_chain_detects_tampering(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    store = ControlPlaneStore(tmp_path / "control-plane.json")
    event_path = tmp_path / "control-plane.events.jsonl"
    event_path.write_text(
        event_path.read_text(encoding="utf-8").replace(
            "finish the bounded fixture", "tampered"
        ),
        encoding="utf-8",
    )
    try:
        store.replay()
    except RuntimeError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered journal was accepted")


def test_control_plane_retries_blocked_todo_with_bounded_backoff(tmp_path):
    kernel = _kernel(tmp_path)
    _started(kernel)
    first = kernel.next_turn("worker")
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=first.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATION_FAILED,
            summary="first failure",
            validated_by="checker",
            idempotency_key="backoff-1",
        )
    )
    repair = kernel.next_turn("worker")
    assert repair.route == TurnRoute.REPAIR
    kernel.record_repair_handoff(
        todo_id="A",
        diagnosis="first failure",
        evidence={"checks": ["first"]},
        handoff_id="backoff-handoff",
    )
    kernel.reopen_after_repair(
        todo_id="A",
        summary="retry allowed",
        evidence={"checks": ["repair"]},
        handoff_id="backoff-handoff",
    )
    second = kernel.next_turn("worker")
    kernel.record_result(
        TurnResult(
            todo_id="A",
            turn_id=second.turn_id or "missing",
            result_kind=TurnResultKind.VALIDATION_FAILED,
            summary="second failure",
            validated_by="checker",
            idempotency_key="backoff-2",
        )
    )
    state = kernel.status()
    assert state is not None
    assert state.todos[0].next_retry_at is not None
    assert kernel.next_turn("worker").route == TurnRoute.WAIT
