import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Iterable

from localforge.control_plane.contracts import (
    AgentIdentity,
    CapabilityProposal,
    CapabilityProposalStatus,
    ControlPlaneState,
    ExternalSignal,
    GateStatus,
    GateState,
    GoalState,
    GoalStatus,
    QuotaState,
    RepairHandoff,
    Receipt,
    TaskSnapshot,
    TodoState,
    TodoStatus,
    TurnDecision,
    TurnResult,
    TurnResultKind,
    TurnRoute,
    utc_iso,
)
from localforge.control_plane.store import ControlPlaneStore


class ControlPlaneKernel:
    """Deterministic goal/todo/turn kernel; it never executes model actions."""

    def __init__(self, store: ControlPlaneStore) -> None:
        self.store = store

    def sync_tasks(self, tasks: Iterable[TaskSnapshot]) -> ControlPlaneState:
        snapshots = list(tasks)

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane must be started before task sync")
            existing = {todo.todo_id: todo for todo in current.todos}
            for snapshot in snapshots:
                todo = existing.get(snapshot.todo_id)
                if todo is None:
                    existing[snapshot.todo_id] = TodoState(
                        todo_id=snapshot.todo_id,
                        title=snapshot.title,
                        dependencies=snapshot.dependencies,
                    )
                    continue
                todo.title = snapshot.title
                todo.dependencies = snapshot.dependencies
                if snapshot.status in {"PR_READY", "DONE"}:
                    todo.status = TodoStatus.PASSED
                    todo.owner = None
                    todo.lease_token = None
                elif snapshot.status in {
                    "BLOCKED",
                    "FAILED_SAFE",
                    "BLOCKED_NEEDS_HUMAN_REVIEW",
                }:
                    todo.status = TodoStatus.BLOCKED
                elif snapshot.status in {"READY", "BACKLOG"} and todo.status != TodoStatus.PASSED:
                    todo.status = TodoStatus.PENDING
                    todo.last_error = None
                todo.updated_at = utc_iso()
            current.todos = list(existing.values())
            return current

        return self.store.update(mutate)

    def start(
        self,
        *,
        goal_id: str,
        vision: str,
        non_negotiables: list[str],
        tasks: Iterable[TaskSnapshot],
        scope: list[str] | None = None,
        authority: dict[str, str] | None = None,
        gates: Iterable[GateState] | None = None,
        max_turns: int = 100,
        max_attempts_per_todo: int = 3,
        max_cost_usd: float = 5.0,
        max_wall_seconds: float | None = None,
        agents: Iterable[AgentIdentity] | None = None,
        source_revision: str | None = None,
        acceptance_target: str | None = None,
    ) -> ControlPlaneState:
        snapshots = list(tasks)

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is not None:
                return current
            return ControlPlaneState(
                goal=GoalState(
                    goal_id=goal_id,
                    vision=vision,
                    non_negotiables=non_negotiables,
                    scope=scope or [],
                    authority=authority or {},
                    source_revision=source_revision,
                    acceptance_target=acceptance_target,
                ),
                todos=[
                    TodoState(
                        todo_id=item.todo_id,
                        title=item.title,
                        dependencies=item.dependencies,
                        status=(
                            TodoStatus.PASSED
                            if item.status in {"PR_READY", "DONE"}
                            else TodoStatus.BLOCKED
                            if item.status in {"BLOCKED", "FAILED_SAFE", "BLOCKED_NEEDS_HUMAN_REVIEW"}
                            else TodoStatus.PENDING
                        ),
                    )
                    for item in snapshots
                ],
                quota=QuotaState(
                    max_turns=max(1, max_turns),
                    max_attempts_per_todo=max(1, max_attempts_per_todo),
                    max_cost_usd=max(0.0, max_cost_usd),
                    max_wall_seconds=max_wall_seconds,
                ),
                gates=list(gates or []),
                agents=list(agents or []),
            )

        return self.store.update(mutate, operation_id=f"start:{goal_id}")

    def next_turn(
        self,
        owner: str,
        *,
        lease_seconds: int = 900,
        expected_revision: int | None = None,
    ) -> TurnDecision:
        decision: TurnDecision | None = None

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            nonlocal decision
            if current is None:
                raise ValueError("Control plane is not initialized")
            if not any(agent.agent_id == owner for agent in current.agents):
                current.agents.append(
                    AgentIdentity(
                        agent_id=owner,
                        role="worker",
                        capabilities=["bounded_turn", "receipt_writeback"],
                        allowed_actions=["read_contract", "write_allowed_files", "run_checks"],
                    )
                )
            self._reconcile_expired(current)
            if current.goal.status == GoalStatus.COMPLETED:
                decision = TurnDecision(
                    route=TurnRoute.COMPLETE,
                    reason="goal_completed",
                    revision=current.revision,
                )
                return current
            if current.goal.status != GoalStatus.ACTIVE:
                decision = TurnDecision(
                    route=TurnRoute.WAIT,
                    reason=f"goal_{current.goal.status.value.lower()}",
                    revision=current.revision,
                    wait_until=(
                        datetime.now(UTC) + timedelta(seconds=60)
                    ).isoformat(),
                )
                return current
            if (
                current.quota.max_wall_seconds is not None
                and current.quota.started_at
            ):
                try:
                    elapsed = (
                        datetime.now(UTC)
                        - datetime.fromisoformat(current.quota.started_at)
                    ).total_seconds()
                except ValueError:
                    elapsed = current.quota.max_wall_seconds + 1
                if elapsed >= current.quota.max_wall_seconds:
                    decision = TurnDecision(
                        route=TurnRoute.WAIT,
                        reason="wall_time_quota_exhausted",
                        revision=current.revision,
                        wait_until=None,
                    )
                    return current
            if current.quota.turns_started >= current.quota.max_turns:
                decision = TurnDecision(
                    route=TurnRoute.WAIT,
                    reason="turn_quota_exhausted",
                    revision=current.revision,
                    wait_until=None,
                )
                return current
            if current.quota.cost_committed_usd >= current.quota.max_cost_usd:
                decision = TurnDecision(
                    route=TurnRoute.WAIT,
                    reason="cost_quota_exhausted",
                    revision=current.revision,
                    wait_until=None,
                )
                return current
            gate = self._gate_for_frontier(current, None)
            if gate is not None:
                decision = TurnDecision(
                    route=TurnRoute.ASK,
                    reason=f"human_gate:{gate.gate_id}:{gate.question or gate.name}",
                    revision=current.revision,
                    todo_id=(gate.affected_todo_ids[0] if gate.affected_todo_ids else None),
                    allowed_actions=["answer_gate"],
                )
                return current
            blocked = next((item for item in current.todos if item.status == TodoStatus.BLOCKED), None)
            if blocked is not None:
                gate = self._gate_for_frontier(current, blocked.todo_id)
                if gate is not None:
                    decision = TurnDecision(
                        route=TurnRoute.ASK,
                        reason=f"human_gate:{gate.gate_id}:{gate.question or gate.name}",
                        revision=current.revision,
                        todo_id=blocked.todo_id,
                        allowed_actions=["answer_gate"],
                    )
                    return current
                if self._retry_is_deferred(blocked):
                    decision = TurnDecision(
                        route=TurnRoute.WAIT,
                        reason=f"repair_backoff:{blocked.todo_id}",
                        revision=current.revision,
                        todo_id=blocked.todo_id,
                        wait_until=blocked.next_retry_at,
                    )
                    return current
                current.goal.current_todo_id = blocked.todo_id
                decision = TurnDecision(
                    route=TurnRoute.REPAIR,
                    reason=f"blocked_todo:{blocked.todo_id}:{blocked.last_error or 'evidence_required'}",
                    revision=current.revision,
                    todo_id=blocked.todo_id,
                    allowed_actions=["inspect_evidence", "repair_under_contract", "rerun_checks"],
                )
                return current
            for item in current.todos:
                if item.status != TodoStatus.PENDING:
                    continue
                if item.attempts >= current.quota.max_attempts_per_todo:
                    item.status = TodoStatus.BLOCKED
                    item.last_error = "attempt_quota_exhausted"
                    item.updated_at = utc_iso()
                    continue
                dependencies = {todo.todo_id: todo.status for todo in current.todos}
                if any(dependencies.get(dep) not in {TodoStatus.PASSED, TodoStatus.SKIPPED} for dep in item.dependencies):
                    continue
                gate = self._gate_for_frontier(current, item.todo_id)
                if gate is not None:
                    decision = TurnDecision(
                        route=TurnRoute.ASK,
                        reason=f"human_gate:{gate.gate_id}:{gate.question or gate.name}",
                        revision=current.revision,
                        todo_id=item.todo_id,
                        allowed_actions=["answer_gate"],
                    )
                    return current
                turn_id = f"turn-{uuid.uuid4().hex}"
                lease_token = uuid.uuid4().hex
                item.status = TodoStatus.CLAIMED
                item.owner = owner
                item.current_turn_id = turn_id
                item.lease_token = lease_token
                item.lease_expires_at = (
                    datetime.now(UTC) + timedelta(seconds=max(30, lease_seconds))
                ).isoformat()
                item.attempts += 1
                item.updated_at = utc_iso()
                current.goal.current_todo_id = item.todo_id
                current.quota.turns_started += 1
                decision = TurnDecision(
                    route=TurnRoute.READY,
                    reason="bounded_turn_claimed",
                    revision=current.revision,
                    todo_id=item.todo_id,
                    turn_id=turn_id,
                    lease_token=lease_token,
                    allowed_actions=["read_contract", "write_allowed_files", "run_checks", "emit_receipt"],
                )
                return current
            all_todos_complete = all(
                item.status in {TodoStatus.PASSED, TodoStatus.SKIPPED}
                for item in current.todos
            )
            open_required_gate = any(
                gate.required
                and gate.status in {GateStatus.OPEN, GateStatus.HUMAN_REVIEW}
                for gate in current.gates
            )
            if all_todos_complete and not open_required_gate:
                current.goal.status = GoalStatus.COMPLETED
                decision = TurnDecision(
                    route=TurnRoute.COMPLETE,
                    reason="all_todos_validated",
                    revision=current.revision,
                )
            else:
                decision = TurnDecision(
                    route=TurnRoute.WAIT,
                    reason="waiting_for_dependencies_or_writeback",
                    revision=current.revision,
                    wait_until=(
                        datetime.now(UTC) + timedelta(seconds=15)
                    ).isoformat(),
                )
            return current

        updated = self.store.update(
            mutate,
            expected_revision=expected_revision,
            operation_id=f"next:{owner}:{datetime.now(UTC).timestamp()}",
        )
        assert decision is not None
        decision.revision = updated.revision
        return decision

    def record_result(self, result: TurnResult) -> ControlPlaneState:
        operation_id = f"result:{result.idempotency_key}"

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            item = next((todo for todo in current.todos if todo.todo_id == result.todo_id), None)
            if item is None:
                raise ValueError(f"Unknown todo {result.todo_id}")
            if item.status != TodoStatus.CLAIMED:
                raise ValueError(f"Todo {result.todo_id} is not owned by a bounded turn")
            if item.current_turn_id != result.turn_id:
                raise ValueError(f"Turn {result.turn_id} is stale for todo {result.todo_id}")
            if current.quota.cost_committed_usd + max(0.0, result.cost_usd) > current.quota.max_cost_usd:
                raise ValueError("Result would exceed the configured cost quota")
            receipt_payload = {
                "todo_id": result.todo_id,
                "turn_id": result.turn_id,
                "result_kind": result.result_kind.value,
                "summary": result.summary,
                "evidence": result.evidence,
                "validated_by": result.validated_by,
                "idempotency_key": result.idempotency_key,
                "changed_files": result.changed_files,
                "checks": result.checks,
                "source_revision": result.source_revision,
            }
            content_hash = hashlib.sha256(
                json.dumps(receipt_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            receipt = Receipt(
                receipt_id=f"receipt-{uuid.uuid4().hex}",
                todo_id=result.todo_id,
                turn_id=result.turn_id,
                result_kind=result.result_kind,
                summary=result.summary,
                evidence=result.evidence,
                content_hash=content_hash,
                validated_by=result.validated_by,
                idempotency_key=result.idempotency_key,
                changed_files=result.changed_files,
                checks=result.checks,
                source_revision=result.source_revision,
            )
            current.receipts.append(receipt)
            current.goal.last_receipt_id = receipt.receipt_id
            current.quota.turns_committed += 1
            current.quota.cost_committed_usd += max(0.0, result.cost_usd)
            item.lease_token = None
            item.lease_expires_at = None
            item.owner = None
            item.current_turn_id = None
            item.last_error = None if result.result_kind in {
                TurnResultKind.VALIDATED_PROGRESS,
                TurnResultKind.VALIDATED_COMPLETION,
            } else result.summary[:1200]
            item.next_retry_at = None
            if (
                result.result_kind
                not in {
                    TurnResultKind.VALIDATED_PROGRESS,
                    TurnResultKind.VALIDATED_COMPLETION,
                }
                and item.attempts > 1
            ):
                item.next_retry_at = (
                    datetime.now(UTC) + timedelta(seconds=min(120, 15 * item.attempts))
                ).isoformat()
            item.status = (
                TodoStatus.PASSED
                if result.result_kind in {
                    TurnResultKind.VALIDATED_PROGRESS,
                    TurnResultKind.VALIDATED_COMPLETION,
                }
                else TodoStatus.BLOCKED
            )
            item.updated_at = utc_iso()
            current.events.append({
                "event": "turn_writeback",
                "todo_id": result.todo_id,
                "turn_id": result.turn_id,
                "route": result.result_kind.value,
                "receipt_id": receipt.receipt_id,
                "at": utc_iso(),
            })
            all_todos_complete = all(
                todo.status in {TodoStatus.PASSED, TodoStatus.SKIPPED}
                for todo in current.todos
            )
            open_required_gate = any(
                gate.required
                and gate.status in {GateStatus.OPEN, GateStatus.HUMAN_REVIEW}
                for gate in current.gates
            )
            if all_todos_complete and not open_required_gate:
                current.goal.status = GoalStatus.COMPLETED
            return current

        return self.store.update(mutate, operation_id=operation_id)

    def renew_lease(
        self,
        *,
        todo_id: str,
        turn_id: str,
        lease_token: str,
        lease_seconds: int = 900,
        owner: str | None = None,
        renewal_id: str | None = None,
    ) -> ControlPlaneState:
        """Extend a live bounded turn without changing its attempt count.

        Renewal is valid only before expiry and with the original turn token.
        A caller-provided ``renewal_id`` makes retries idempotent; this keeps a
        flaky worker heartbeat from creating duplicate journal entries.
        """

        normalized_renewal_id = renewal_id or f"{todo_id}:{turn_id}:{uuid.uuid4().hex}"
        operation_id = f"lease-renew:{normalized_renewal_id}"

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            item = next((todo for todo in current.todos if todo.todo_id == todo_id), None)
            if item is None:
                raise ValueError(f"Unknown todo {todo_id}")
            if item.status != TodoStatus.CLAIMED:
                raise ValueError(f"Todo {todo_id} is not owned by a bounded turn")
            if item.current_turn_id != turn_id or item.lease_token != lease_token:
                raise ValueError(f"Lease token is stale for todo {todo_id}")
            if owner is not None and item.owner != owner:
                raise ValueError(f"Lease owner is stale for todo {todo_id}")
            try:
                expired = bool(
                    item.lease_expires_at
                    and datetime.fromisoformat(item.lease_expires_at) <= datetime.now(UTC)
                )
            except ValueError:
                expired = True
            if expired:
                raise ValueError(f"Lease for todo {todo_id} has expired")
            item.lease_expires_at = (
                datetime.now(UTC) + timedelta(seconds=max(30, lease_seconds))
            ).isoformat()
            item.updated_at = utc_iso()
            current.events.append(
                {
                    "event": "lease_renewed",
                    "todo_id": todo_id,
                    "turn_id": turn_id,
                    "owner": item.owner,
                    "renewal_id": normalized_renewal_id,
                    "lease_expires_at": item.lease_expires_at,
                    "at": utc_iso(),
                }
            )
            return current

        return self.store.update(mutate, operation_id=operation_id)

    def record_repair_handoff(
        self,
        *,
        todo_id: str,
        diagnosis: str,
        evidence: dict[str, object],
        authority: str = "scrum_master",
        handoff_id: str | None = None,
    ) -> ControlPlaneState:
        """Persist a blocker diagnosis before a repair worker is dispatched."""

        operation_id = f"repair-handoff:{todo_id}:{handoff_id or diagnosis[:64]}"
        normalized_handoff_id = handoff_id or f"handoff-{uuid.uuid4().hex}"

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            item = next((todo for todo in current.todos if todo.todo_id == todo_id), None)
            if item is None:
                raise ValueError(f"Unknown todo {todo_id}")
            item.last_error = diagnosis[:1200]
            existing = next(
                (handoff for handoff in current.handoffs if handoff.handoff_id == normalized_handoff_id),
                None,
            )
            if existing is None:
                current.handoffs.append(
                    RepairHandoff(
                        handoff_id=normalized_handoff_id,
                        todo_id=todo_id,
                        diagnosis=diagnosis[:1200],
                        evidence=evidence,
                        authority=authority,
                    )
                )
            current.goal.current_todo_id = todo_id
            current.events.append(
                {
                    "event": "repair_handoff",
                    "todo_id": todo_id,
                    "handoff_id": normalized_handoff_id,
                    "authority": authority,
                    "diagnosis": diagnosis[:1200],
                    "evidence": evidence,
                    "at": utc_iso(),
                }
            )
            return current

        return self.store.update(mutate, operation_id=operation_id)

    def reopen_after_repair(
        self,
        *,
        todo_id: str,
        summary: str,
        evidence: dict[str, object],
        handoff_id: str,
    ) -> ControlPlaneState:
        """Return a blocked todo to the frontier only after repair writeback."""

        operation_id = f"repair-reopen:{todo_id}:{handoff_id}"

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            item = next((todo for todo in current.todos if todo.todo_id == todo_id), None)
            if item is None:
                raise ValueError(f"Unknown todo {todo_id}")
            if item.status not in {TodoStatus.BLOCKED, TodoStatus.PENDING}:
                raise ValueError(f"Todo {todo_id} is not repairable from {item.status.value}")
            handoff = next(
                (item for item in current.handoffs if item.handoff_id == handoff_id),
                None,
            )
            if handoff is None:
                raise ValueError(f"Unknown repair handoff {handoff_id}")
            handoff.status = "REOPENED"
            item.status = TodoStatus.PENDING
            item.last_error = None
            item.updated_at = utc_iso()
            current.goal.status = GoalStatus.ACTIVE
            current.goal.current_todo_id = todo_id
            current.events.append(
                {
                    "event": "repair_writeback",
                    "todo_id": todo_id,
                    "handoff_id": handoff_id,
                    "summary": summary[:1200],
                    "evidence": evidence,
                    "at": utc_iso(),
                }
            )
            return current

        return self.store.update(mutate, operation_id=operation_id)

    def record_signal(
        self,
        *,
        signal_id: str,
        signal_type: str,
        source: str,
        payload: dict[str, object],
        fingerprint: str | None = None,
        affected_todo_id: str | None = None,
    ) -> ControlPlaneState:
        """Persist one external observation exactly once by fingerprint."""

        normalized_fingerprint = fingerprint or json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        )
        operation_id = f"signal:{signal_id}"

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            if any(item.fingerprint == normalized_fingerprint for item in current.signals):
                return current
            current.signals.append(
                ExternalSignal(
                    signal_id=signal_id,
                    signal_type=signal_type,
                    source=source,
                    fingerprint=normalized_fingerprint,
                    payload=payload,
                    affected_todo_id=affected_todo_id or (
                        str(payload.get("todo_id")) if payload.get("todo_id") is not None else None
                    ),
                )
            )
            current.events.append(
                {
                    "event": "external_signal",
                    "signal_id": signal_id,
                    "signal_type": signal_type,
                    "source": source,
                    "fingerprint": normalized_fingerprint,
                    "at": utc_iso(),
                }
            )
            return current

        return self.store.update(mutate, operation_id=operation_id)

    def acknowledge_signal(self, signal_id: str) -> ControlPlaneState:
        """Mark an external observation consumed without deleting its evidence."""

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            signal = next((item for item in current.signals if item.signal_id == signal_id), None)
            if signal is None:
                raise ValueError(f"Unknown signal {signal_id}")
            if signal.acknowledged_at is None:
                signal.acknowledged_at = utc_iso()
                current.events.append(
                    {"event": "signal_acknowledged", "signal_id": signal_id, "at": signal.acknowledged_at}
                )
            return current

        return self.store.update(mutate, operation_id=f"signal-ack:{signal_id}")

    def propose_capability(
        self,
        *,
        proposal_id: str,
        capability: str,
        description: str,
        isolated_scope: list[str],
        proposed_by: str,
        source_revision: str | None = None,
    ) -> ControlPlaneState:
        """Register an isolated capability proposal; active runtime is unchanged."""

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            if any(item.proposal_id == proposal_id for item in current.capability_proposals):
                return current
            current.capability_proposals.append(
                CapabilityProposal(
                    proposal_id=proposal_id,
                    capability=capability,
                    description=description,
                    isolated_scope=isolated_scope,
                    source_revision=source_revision,
                    proposed_by=proposed_by,
                )
            )
            current.events.append(
                {"event": "capability_proposed", "proposal_id": proposal_id, "at": utc_iso()}
            )
            return current

        return self.store.update(mutate, operation_id=f"capability-propose:{proposal_id}")

    def validate_capability(
        self, proposal_id: str, *, evidence: dict[str, object], validated_by: str
    ) -> ControlPlaneState:
        """Accept validation evidence while keeping promotion a separate action."""

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            proposal = next((item for item in current.capability_proposals if item.proposal_id == proposal_id), None)
            if proposal is None:
                raise ValueError(f"Unknown capability proposal {proposal_id}")
            if not evidence:
                raise ValueError("Capability validation requires evidence")
            proposal.status = CapabilityProposalStatus.VALIDATED
            proposal.evidence = {**evidence, "validated_by": validated_by}
            proposal.updated_at = utc_iso()
            current.events.append(
                {"event": "capability_validated", "proposal_id": proposal_id, "at": proposal.updated_at}
            )
            return current

        return self.store.update(mutate, operation_id=f"capability-validate:{proposal_id}")

    def promote_capability(self, proposal_id: str, *, promoted_by: str) -> ControlPlaneState:
        """Promote only an independently validated proposal with recorded evidence."""

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            proposal = next((item for item in current.capability_proposals if item.proposal_id == proposal_id), None)
            if proposal is None:
                raise ValueError(f"Unknown capability proposal {proposal_id}")
            if proposal.status != CapabilityProposalStatus.VALIDATED:
                raise ValueError("Capability proposal must be independently validated before promotion")
            proposal.status = CapabilityProposalStatus.PROMOTED
            proposal.evidence = {**proposal.evidence, "promoted_by": promoted_by}
            proposal.updated_at = utc_iso()
            current.events.append(
                {"event": "capability_promoted", "proposal_id": proposal_id, "at": proposal.updated_at}
            )
            return current

        return self.store.update(mutate, operation_id=f"capability-promote:{proposal_id}")

    def register_agent(self, agent: AgentIdentity) -> ControlPlaneState:
        """Register or refresh a worker without granting human authority."""

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            existing = next(
                (item for item in current.agents if item.agent_id == agent.agent_id), None
            )
            if existing is None:
                current.agents.append(agent)
            else:
                existing.role = agent.role
                existing.capabilities = list(agent.capabilities)
                existing.allowed_actions = list(agent.allowed_actions)
                existing.authority = agent.authority
                existing.active = agent.active
            current.events.append(
                {"event": "agent_registered", "agent_id": agent.agent_id, "role": agent.role, "at": utc_iso()}
            )
            return current

        fingerprint = hashlib.sha256(
            json.dumps(agent.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return self.store.update(
            mutate, operation_id=f"agent:{agent.agent_id}:{fingerprint}"
        )

    def set_gate(self, gate: GateState) -> ControlPlaneState:
        """Create or update a human gate that only affects its declared lane."""

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            existing = next((item for item in current.gates if item.gate_id == gate.gate_id), None)
            if existing is None:
                current.gates.append(gate)
            else:
                existing.name = gate.name
                existing.required = gate.required
                existing.status = gate.status
                existing.question = gate.question
                existing.authority = gate.authority
                existing.safe_default = gate.safe_default
                existing.affected_todo_ids = list(gate.affected_todo_ids)
                existing.expires_at = gate.expires_at
            current.events.append({"event": "gate_changed", "gate_id": gate.gate_id, "status": gate.status.value, "at": utc_iso()})
            return current

        fingerprint = hashlib.sha256(
            json.dumps(gate.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return self.store.update(
            mutate, operation_id=f"gate:{gate.gate_id}:{fingerprint}"
        )

    def answer_gate(self, gate_id: str, answer: str, *, answered_by: str = "human") -> ControlPlaneState:
        """Record a human answer as a receipt before reopening its lane."""

        normalized = answer.strip()
        if not normalized:
            raise ValueError("Gate answer must not be empty")

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            gate = next((item for item in current.gates if item.gate_id == gate_id), None)
            if gate is None:
                raise ValueError(f"Unknown gate {gate_id}")
            receipt_id = f"gate-receipt-{uuid.uuid4().hex}"
            gate.status = GateStatus.PASSED
            gate.answer = normalized[:2000]
            gate.answer_receipt_id = receipt_id
            gate.receipt_ids.append(receipt_id)
            current.events.append({"event": "gate_answered", "gate_id": gate_id, "authority": answered_by, "receipt_id": receipt_id, "at": utc_iso()})
            return current

        return self.store.update(mutate, operation_id=f"gate-answer:{gate_id}:{normalized}")

    def review_packet(self) -> dict[str, object]:
        """Build a compact operator packet from the durable state."""
        state = self.status()
        if state is None:
            return {
                "status": "MISSING",
                "next_action": "INITIALIZE",
                "interaction_contract": {
                    "schema_version": "forgeos.interaction_contract.v1",
                    "should_run": False,
                    "mode": "initialize",
                    "primary_action": "initialize_goal",
                },
            }
        blocked = next(
            (todo for todo in state.todos if todo.status == TodoStatus.BLOCKED), None
        )
        passed_ids = {
            todo.todo_id
            for todo in state.todos
            if todo.status in {TodoStatus.PASSED, TodoStatus.SKIPPED}
        }
        pending = next(
            (
                todo
                for todo in state.todos
                if todo.status == TodoStatus.PENDING
                and all(dependency_id in passed_ids for dependency_id in todo.dependencies)
            ),
            None,
        )
        global_gate = self._gate_for_frontier(state, None)
        if state.goal.status == GoalStatus.COMPLETED:
            next_action: dict[str, object] = {"route": TurnRoute.COMPLETE.value}
        elif state.goal.status != GoalStatus.ACTIVE:
            next_action = {"route": TurnRoute.WAIT.value, "reason": state.goal.status.value}
        elif global_gate is not None:
            next_action = {
                "route": TurnRoute.ASK.value,
                "reason": f"human_gate:{global_gate.gate_id}",
                "question": global_gate.question or global_gate.name,
            }
        elif blocked is not None:
            blocked_gate = self._gate_for_frontier(state, blocked.todo_id)
            if blocked_gate is not None:
                next_action = {
                    "route": TurnRoute.ASK.value,
                    "todo_id": blocked.todo_id,
                    "reason": f"human_gate:{blocked_gate.gate_id}",
                    "question": blocked_gate.question or blocked_gate.name,
                }
            elif self._retry_is_deferred(blocked):
                next_action = {
                    "route": TurnRoute.WAIT.value,
                    "todo_id": blocked.todo_id,
                    "reason": "repair_backoff",
                    "wait_until": blocked.next_retry_at,
                }
            else:
                next_action = {
                    "route": TurnRoute.REPAIR.value,
                    "todo_id": blocked.todo_id,
                    "reason": blocked.last_error or "evidence_required",
                }
        elif pending is not None:
            pending_gate = self._gate_for_frontier(state, pending.todo_id)
            if pending_gate is not None:
                next_action = {
                    "route": TurnRoute.ASK.value,
                    "todo_id": pending.todo_id,
                    "reason": f"human_gate:{pending_gate.gate_id}",
                    "question": pending_gate.question or pending_gate.name,
                }
            else:
                next_action = {"route": TurnRoute.READY.value, "todo_id": pending.todo_id}
        else:
            next_action = {
                "route": TurnRoute.WAIT.value,
                "reason": "waiting_for_dependencies_or_writeback",
            }
        interaction_contract = self._interaction_contract(state, next_action)
        return {
            "goal": state.goal.model_dump(mode="json"),
            "frontier": [todo.model_dump(mode="json") for todo in state.todos],
            "gates": [gate.model_dump(mode="json") for gate in state.gates],
            "handoffs": [handoff.model_dump(mode="json") for handoff in state.handoffs],
            "signals": [signal.model_dump(mode="json") for signal in state.signals[-20:]],
            "attention_queue": self._attention_queue(state),
            "capability_proposals": [item.model_dump(mode="json") for item in state.capability_proposals],
            "receipts": len(state.receipts),
            "quota": state.quota.model_dump(mode="json"),
            "next_action": next_action,
            "interaction_contract": interaction_contract,
            "journal_verified": self.store.verify_replay(),
        }

    @staticmethod
    def _interaction_contract(
        state: ControlPlaneState, next_action: dict[str, object]
    ) -> dict[str, object]:
        """Return machine-readable wake/quiet semantics without an LLM call."""

        route = str(next_action.get("route") or TurnRoute.WAIT.value)
        active_routes = {
            TurnRoute.READY.value,
            TurnRoute.REPAIR.value,
            TurnRoute.REPLAN.value,
        }
        modes = {
            TurnRoute.READY.value: "bounded_delivery",
            TurnRoute.REPAIR.value: "bounded_repair",
            TurnRoute.REPLAN.value: "bounded_replan",
            TurnRoute.ASK.value: "user_gate",
            TurnRoute.WAIT.value: "wait",
            TurnRoute.BLOCKED.value: "blocked",
            TurnRoute.COMPLETE.value: "completed",
        }
        unacknowledged_signals = [
            signal for signal in state.signals if signal.acknowledged_at is None
        ]
        current_todo_id = next_action.get("todo_id")
        signal_wakeup = state.goal.status == GoalStatus.ACTIVE and any(
            signal.affected_todo_id is None
            or signal.affected_todo_id == current_todo_id
            or route not in active_routes
            for signal in unacknowledged_signals
        )
        should_run = (
            route in active_routes and state.goal.status == GoalStatus.ACTIVE
        ) or signal_wakeup
        signal = unacknowledged_signals[0] if unacknowledged_signals else None
        if signal_wakeup:
            mode = "signal_attention"
            primary_action = "inspect_external_signal"
        else:
            mode = modes.get(route, "wait")
            primary_action = (
                "claim_bounded_turn"
                if route == TurnRoute.READY.value
                else "repair_under_contract"
                if route == TurnRoute.REPAIR.value
                else "replan_under_contract"
                if route == TurnRoute.REPLAN.value
                else "wait_for_operator_or_signal"
            )
        return {
            "schema_version": "forgeos.interaction_contract.v1",
            "should_run": should_run,
            "mode": mode,
            "primary_action": primary_action,
            "route": route,
            "reason": next_action.get("reason"),
            "todo_id": next_action.get("todo_id"),
            "wait_until": next_action.get("wait_until"),
            "requires_human": route == TurnRoute.ASK.value,
            "spend_allowed": bool(
                should_run and primary_action != "inspect_external_signal"
            ),
            "signal_id": signal.signal_id if signal is not None else None,
        }

    @staticmethod
    def _attention_queue(state: ControlPlaneState) -> list[dict[str, object]]:
        queue: list[dict[str, object]] = []
        for gate in state.gates:
            if gate.required and gate.status in {GateStatus.OPEN, GateStatus.HUMAN_REVIEW}:
                queue.append({"kind": "human_gate", "id": gate.gate_id, "question": gate.question or gate.name})
        for todo in state.todos:
            if todo.status == TodoStatus.BLOCKED:
                queue.append({"kind": "blocked_todo", "id": todo.todo_id, "reason": todo.last_error or "evidence_required"})
        for signal in state.signals:
            if signal.acknowledged_at is None:
                queue.append(
                    {
                        "kind": "external_signal",
                        "id": signal.signal_id,
                        "signal_type": signal.signal_type,
                        "todo_id": signal.affected_todo_id,
                    }
                )
        return queue

    def should_run(self) -> dict[str, object]:
        """Return the scheduler-safe projection without claiming work."""

        return self.review_packet()

    def recover_expired_leases(self) -> ControlPlaneState | None:
        """Reconcile abandoned turns before a worker asks for new work.

        The projection remains read-only while a persistent runner can
        explicitly perform this deterministic recovery write at startup and
        on each heartbeat.
        """

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            self._reconcile_expired(current)
            return current

        return self.store.update(mutate)

    def pause(self, reason: str) -> ControlPlaneState:
        return self._set_goal_status(GoalStatus.PAUSED, reason)

    def resume(self, reason: str = "operator_resume") -> ControlPlaneState:
        return self._set_goal_status(GoalStatus.ACTIVE, reason)

    def abort(self, reason: str) -> ControlPlaneState:
        """Close an interrupted run without leaving an active lease behind."""

        normalized_reason = reason[:1200] or "bounded_run_interrupted"

        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            if current.goal.status in {
                GoalStatus.COMPLETED,
                GoalStatus.FAILED,
                GoalStatus.BLOCKED,
            }:
                return current
            interrupted: list[str] = []
            for item in current.todos:
                if item.status != TodoStatus.CLAIMED:
                    continue
                interrupted.append(item.todo_id)
                item.status = TodoStatus.BLOCKED
                item.owner = None
                item.current_turn_id = None
                item.lease_token = None
                item.lease_expires_at = None
                item.last_error = normalized_reason
                item.updated_at = utc_iso()
            current.goal.status = GoalStatus.BLOCKED
            if interrupted:
                current.goal.current_todo_id = interrupted[0]
            current.events.append(
                {
                    "event": "run_aborted",
                    "reason": normalized_reason,
                    "interrupted_todos": interrupted,
                    "at": utc_iso(),
                }
            )
            return current

        return self.store.update(mutate, operation_id=f"abort:{normalized_reason}")

    def status(self) -> ControlPlaneState | None:
        return self.store.read()

    @staticmethod
    def _reconcile_expired(current: ControlPlaneState) -> None:
        now = datetime.now(UTC)
        for item in current.todos:
            if item.status != TodoStatus.CLAIMED or not item.lease_expires_at:
                continue
            try:
                expired = datetime.fromisoformat(item.lease_expires_at) <= now
            except ValueError:
                expired = True
            if expired:
                previous_owner = item.owner
                previous_turn_id = item.current_turn_id
                next_status = (
                    TodoStatus.BLOCKED
                    if item.attempts >= current.quota.max_attempts_per_todo
                    else TodoStatus.PENDING
                )
                item.status = next_status
                item.owner = None
                item.current_turn_id = None
                item.lease_token = None
                item.lease_expires_at = None
                item.last_error = "bounded_turn_lease_expired"
                item.next_retry_at = None
                item.updated_at = utc_iso()
                current.events.append(
                    {
                        "event": "lease_expired_recovered",
                        "todo_id": item.todo_id,
                        "turn_id": previous_turn_id,
                        "owner": previous_owner,
                        "next_status": next_status.value,
                        "attempts": item.attempts,
                        "at": utc_iso(),
                    }
                )

    @staticmethod
    def _retry_is_deferred(item: TodoState) -> bool:
        if not item.next_retry_at:
            return False
        try:
            return datetime.fromisoformat(item.next_retry_at) > datetime.now(UTC)
        except ValueError:
            return False

    @staticmethod
    def _gate_for_frontier(
        current: ControlPlaneState, todo_id: str | None
    ) -> GateState | None:
        for gate in current.gates:
            if not gate.required or gate.status not in {GateStatus.OPEN, GateStatus.HUMAN_REVIEW}:
                continue
            if not gate.affected_todo_ids:
                return gate
            if todo_id is not None and todo_id in gate.affected_todo_ids:
                return gate
        return None

    def _set_goal_status(self, status: GoalStatus, reason: str) -> ControlPlaneState:
        def mutate(current: ControlPlaneState | None) -> ControlPlaneState:
            if current is None:
                raise ValueError("Control plane is not initialized")
            current.goal.status = status
            current.events.append({"event": "goal_status", "status": status.value, "reason": reason, "at": utc_iso()})
            return current

        return self.store.update(mutate, operation_id=f"goal:{status.value}:{reason}")
