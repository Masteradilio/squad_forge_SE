import json
from pathlib import Path
from typing import Any

import typer
from localforge.control_plane import (
    BoundedWorkerBridge,
    AgentIdentity,
    ControlPlaneKernel,
    ControlPlaneStore,
    GoalRegistry,
    GateState,
    TaskSnapshot,
    TurnResult,
    TurnResultKind,
)
from rich.console import Console

console = Console()
control_plane_app = typer.Typer(help="Inspect and drive the durable bounded-turn run state.")


def _kernel(path: str) -> ControlPlaneKernel:
    return ControlPlaneKernel(ControlPlaneStore(Path(path)))


@control_plane_app.command("status")
def status(
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Print the redacted control-plane projection for one run."""
    state = _kernel(path).status()
    if state is None:
        raise typer.Exit(code=1)
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("events")
def events(
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
    limit: int = typer.Option(20, "--limit", min=1, max=200),
) -> None:
    """Print append-only control-plane event metadata."""
    records = ControlPlaneStore(Path(path)).event_records()
    console.print_json(json.dumps(records[-limit:]))


@control_plane_app.command("review-packet")
def review_packet(
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Print the compact operator handoff without raw model transcripts."""
    console.print_json(json.dumps(_kernel(path).review_packet()))


@control_plane_app.command("should-run")
def should_run(
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Print the pure scheduler heartbeat without claiming a turn."""
    console.print_json(json.dumps(_kernel(path).should_run()))


@control_plane_app.command("heartbeat")
def heartbeat(
    owner: str = typer.Option("worker", "--owner"),
    claim: bool = typer.Option(False, "--claim", help="Claim one bounded turn after the read-only check."),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=30, max=86400),
    expected_revision: int | None = typer.Option(None, "--expected-revision"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Run one quiet heartbeat; optionally claim exactly one bounded turn."""
    bridge = BoundedWorkerBridge(_kernel(path))
    if not claim:
        console.print_json(json.dumps(bridge.should_run()))
        return
    decision = bridge.claim(
        owner,
        lease_seconds=lease_seconds,
        expected_revision=expected_revision,
    )
    console.print_json(json.dumps(decision.model_dump(mode="json")))


@control_plane_app.command("renew")
def renew(
    todo_id: str = typer.Option(..., "--todo-id"),
    turn_id: str = typer.Option(..., "--turn-id"),
    lease_token: str = typer.Option(..., "--lease-token"),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=30, max=86400),
    owner: str | None = typer.Option(None, "--owner"),
    renewal_id: str | None = typer.Option(None, "--renewal-id"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Renew one live bounded-turn lease; never claims or executes work."""
    state = _kernel(path).renew_lease(
        todo_id=todo_id,
        turn_id=turn_id,
        lease_token=lease_token,
        lease_seconds=lease_seconds,
        owner=owner,
        renewal_id=renewal_id,
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("connect")
def connect(
    goal_id: str = typer.Option(..., "--goal-id"),
    state_path: str = typer.Option(".localforge/control_plane.json", "--state-path"),
    workspace: str = typer.Option(".", "--workspace"),
    source_revision: str | None = typer.Option(None, "--source-revision"),
    registry_path: str = typer.Option(".localforge/registry.json", "--registry-path"),
) -> None:
    """Connect a project to an existing durable goal without rebuilding it."""
    entry = GoalRegistry(registry_path).connect(
        goal_id=goal_id,
        workspace=workspace,
        state_path=state_path,
        source_revision=source_revision,
    )
    console.print_json(json.dumps(entry.model_dump(mode="json")))


@control_plane_app.command("signal")
def signal(
    signal_id: str = typer.Option(..., "--signal-id"),
    signal_type: str = typer.Option(..., "--type"),
    source: str = typer.Option(..., "--source"),
    payload: str = typer.Option("{}", "--payload"),
    fingerprint: str | None = typer.Option(None, "--fingerprint"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Record one deduplicated provider, CI, review, or host signal."""
    try:
        payload_value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"payload must be JSON: {exc}") from exc
    if not isinstance(payload_value, dict):
        raise typer.BadParameter("payload must be a JSON object")
    state = _kernel(path).record_signal(
        signal_id=signal_id,
        signal_type=signal_type,
        source=source,
        payload=payload_value,
        fingerprint=fingerprint,
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("ack-signal")
def acknowledge_signal(
    signal_id: str = typer.Option(..., "--signal-id"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Acknowledge an external observation while preserving its journal record."""
    state = _kernel(path).acknowledge_signal(signal_id)
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("propose-capability")
def propose_capability(
    proposal_id: str = typer.Option(..., "--proposal-id"),
    capability: str = typer.Option(..., "--capability"),
    description: str = typer.Option(..., "--description"),
    isolated_scope: str = typer.Option("", "--isolated-scope"),
    proposed_by: str = typer.Option("chief-engineer", "--proposed-by"),
    source_revision: str | None = typer.Option(None, "--source-revision"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Record a self-evolution proposal without changing the active runtime."""
    state = _kernel(path).propose_capability(
        proposal_id=proposal_id,
        capability=capability,
        description=description,
        isolated_scope=[item.strip() for item in isolated_scope.split(",") if item.strip()],
        proposed_by=proposed_by,
        source_revision=source_revision,
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("validate-capability")
def validate_capability(
    proposal_id: str = typer.Option(..., "--proposal-id"),
    evidence: str = typer.Option("{}", "--evidence"),
    validated_by: str = typer.Option("reviewer", "--validated-by"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Attach independent evidence before a capability can be promoted."""
    try:
        evidence_payload: dict[str, Any] = json.loads(evidence)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"evidence must be JSON: {exc}") from exc
    state = _kernel(path).validate_capability(proposal_id, evidence=evidence_payload, validated_by=validated_by)
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("promote-capability")
def promote_capability(
    proposal_id: str = typer.Option(..., "--proposal-id"),
    promoted_by: str = typer.Option("human", "--promoted-by"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Promote a separately validated capability after its review gate."""
    state = _kernel(path).promote_capability(proposal_id, promoted_by=promoted_by)
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("next")
def next_turn(
    owner: str = typer.Option("operator", "--owner"),
    lease_seconds: int = typer.Option(900, "--lease-seconds", min=30, max=86400),
    expected_revision: int | None = typer.Option(None, "--expected-revision"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Claim one bounded turn or print an explicit wait/repair decision."""
    decision = _kernel(path).next_turn(
        owner, lease_seconds=lease_seconds, expected_revision=expected_revision
    )
    console.print_json(json.dumps(decision.model_dump(mode="json")))


@control_plane_app.command("agent")
def register_agent(
    agent_id: str = typer.Option(..., "--agent-id"),
    role: str = typer.Option(..., "--role"),
    capabilities: str = typer.Option("", "--capabilities"),
    allowed_actions: str = typer.Option("", "--allowed-actions"),
    authority: str = typer.Option("worker", "--authority"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Register a bounded worker identity and its explicit authority."""
    state = _kernel(path).register_agent(
        AgentIdentity(
            agent_id=agent_id,
            role=role,
            capabilities=[item.strip() for item in capabilities.split(",") if item.strip()],
            allowed_actions=[item.strip() for item in allowed_actions.split(",") if item.strip()],
            authority=authority,
        )
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("gate")
def set_gate(
    gate_id: str = typer.Option(..., "--gate-id"),
    name: str = typer.Option(..., "--name"),
    question: str = typer.Option("", "--question"),
    authority: str = typer.Option("human", "--authority"),
    safe_default: str | None = typer.Option(None, "--safe-default"),
    affected_todo_ids: str = typer.Option("", "--affected-todo-ids"),
    required: bool = typer.Option(True, "--required/--optional"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Create or update an explicit human decision gate."""
    state = _kernel(path).set_gate(
        GateState(
            gate_id=gate_id,
            name=name,
            question=question,
            authority=authority,
            safe_default=safe_default,
            affected_todo_ids=[
                item.strip() for item in affected_todo_ids.split(",") if item.strip()
            ],
            required=required,
        )
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("answer-gate")
def answer_gate(
    gate_id: str = typer.Option(..., "--gate-id"),
    answer: str = typer.Option(..., "--answer"),
    answered_by: str = typer.Option("human", "--answered-by"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Record an authorized gate answer as a durable receipt."""
    state = _kernel(path).answer_gate(gate_id, answer, answered_by=answered_by)
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("writeback")
def writeback(
    todo_id: str = typer.Option(..., "--todo-id"),
    turn_id: str = typer.Option(..., "--turn-id"),
    result_kind: TurnResultKind = typer.Option(..., "--result"),
    summary: str = typer.Option(..., "--summary"),
    evidence: str = typer.Option("{}", "--evidence"),
    validated_by: str = typer.Option("operator", "--validated-by"),
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    cost_usd: float = typer.Option(0.0, "--cost-usd"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Commit one typed receipt; observations without this command do not advance state."""
    try:
        evidence_payload: dict[str, Any] = json.loads(evidence)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"evidence must be JSON: {exc}") from exc
    state = _kernel(path).record_result(
        TurnResult(
            todo_id=todo_id,
            turn_id=turn_id,
            result_kind=result_kind,
            summary=summary,
            evidence=evidence_payload,
            validated_by=validated_by,
            idempotency_key=idempotency_key,
            cost_usd=cost_usd,
        )
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("repair-handoff")
def repair_handoff(
    todo_id: str = typer.Option(..., "--todo-id"),
    diagnosis: str = typer.Option(..., "--diagnosis"),
    evidence: str = typer.Option("{}", "--evidence"),
    handoff_id: str = typer.Option(..., "--handoff-id"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Persist Scrum Master diagnosis before Chief Engineer repair."""
    try:
        evidence_payload: dict[str, Any] = json.loads(evidence)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"evidence must be JSON: {exc}") from exc
    state = _kernel(path).record_repair_handoff(
        todo_id=todo_id,
        diagnosis=diagnosis,
        evidence=evidence_payload,
        handoff_id=handoff_id,
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("reopen")
def reopen_after_repair(
    todo_id: str = typer.Option(..., "--todo-id"),
    summary: str = typer.Option(..., "--summary"),
    evidence: str = typer.Option("{}", "--evidence"),
    handoff_id: str = typer.Option(..., "--handoff-id"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Return a blocked todo to the frontier after validated repair writeback."""
    try:
        evidence_payload: dict[str, Any] = json.loads(evidence)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"evidence must be JSON: {exc}") from exc
    state = _kernel(path).reopen_after_repair(
        todo_id=todo_id,
        summary=summary,
        evidence=evidence_payload,
        handoff_id=handoff_id,
    )
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("pause")
def pause(
    reason: str = typer.Option("operator_pause", "--reason"),
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Pause new bounded turns while preserving the durable goal."""
    state = _kernel(path).pause(reason)
    console.print_json(json.dumps(state.model_dump(mode="json")))


@control_plane_app.command("resume")
def resume(
    path: str = typer.Option(".localforge/control_plane.json", "--path"),
) -> None:
    """Resume a paused goal."""
    state = _kernel(path).resume()
    console.print_json(json.dumps(state.model_dump(mode="json")))
