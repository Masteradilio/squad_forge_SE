"""Human-in-the-Loop (HITL Gates) Engine — Pauses execution for PO approval or dynamic input."""

import time
from typing import Any, Dict, Optional
import pydantic


class HITLInterruptionGate(pydantic.BaseModel):
    gate_id: str
    gate_type: str  # "ARCHITECTURE_APPROVAL", "RELEASE_APPROVAL", "DYNAMIC_INPUT"
    role_name: str
    prompt_message: str
    question_options: Optional[Dict[str, Any]] = None
    status: str = "PAUSED"  # "PAUSED", "APPROVED", "REJECTED"
    created_at: float = pydantic.Field(default_factory=time.time)
    user_response: Optional[str] = None


class HITLEngine:
    """Engine managing Human-in-the-Loop interruption gates and PO approvals."""

    def __init__(self):
        self.active_gates: Dict[str, HITLInterruptionGate] = {}

    def create_interruption_gate(
        self,
        gate_type: str,
        role_name: str,
        prompt_message: str,
        question_options: Optional[Dict[str, Any]] = None,
    ) -> HITLInterruptionGate:
        """Pause pipeline execution and register a HITL gate requiring PO input/approval."""
        gate_id = f"hitl_{gate_type.lower()}_{int(time.time() * 1000)}"
        gate = HITLInterruptionGate(
            gate_id=gate_id,
            gate_type=gate_type,
            role_name=role_name,
            prompt_message=prompt_message,
            question_options=question_options,
            status="PAUSED",
        )
        self.active_gates[gate_id] = gate
        return gate

    def resolve_gate(self, gate_id: str, user_response: str, approve: bool = True) -> Optional[HITLInterruptionGate]:
        """Resolve a HITL gate with PO approval or input response."""
        if gate_id in self.active_gates:
            gate = self.active_gates[gate_id]
            gate.status = "APPROVED" if approve else "REJECTED"
            gate.user_response = user_response
            return gate
        return None
