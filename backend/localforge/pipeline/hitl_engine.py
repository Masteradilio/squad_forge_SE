"""Durable Human-in-the-Loop gates for PO approvals and dynamic input."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pydantic


class HITLInterruptionGate(pydantic.BaseModel):
    gate_id: str
    project_id: int | None = None
    run_id: int | None = None
    gate_type: str
    role_name: str
    prompt_message: str
    question_options: dict[str, Any] | None = None
    status: str = "PAUSED"
    created_at: float = pydantic.Field(default_factory=time.time)
    user_response: str | None = None


class HITLEngine:
    """Persist HITL gates so a restart cannot lose a pending PO decision."""

    def __init__(self, storage_path: str | Path | None = None):
        self.active_gates: dict[str, HITLInterruptionGate] = {}
        self.storage_path = Path(storage_path or ".localforge/hitl_gates.json")
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, list):
            return
        with self._lock:
            for item in payload:
                if not isinstance(item, dict) or not item.get("gate_id"):
                    continue
                try:
                    gate = HITLInterruptionGate.model_validate(item)
                except pydantic.ValidationError:
                    continue
                self.active_gates[gate.gate_id] = gate

    def _persist(self) -> None:
        with self._lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [gate.model_dump(mode="json") for gate in self.active_gates.values()]
            temporary = self.storage_path.with_name(
                f".{self.storage_path.name}.{uuid4().hex}.tmp"
            )
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(temporary, self.storage_path)

    def create_interruption_gate(
        self,
        gate_type: str,
        role_name: str,
        prompt_message: str,
        question_options: dict[str, Any] | None = None,
        project_id: int | None = None,
        run_id: int | None = None,
    ) -> HITLInterruptionGate:
        """Create and durably register a gate requiring PO input."""
        gate = HITLInterruptionGate(
            gate_id=f"hitl_{gate_type.lower()}_{uuid4().hex}",
            project_id=project_id,
            run_id=run_id,
            gate_type=gate_type,
            role_name=role_name,
            prompt_message=prompt_message,
            question_options=question_options,
        )
        with self._lock:
            self.active_gates[gate.gate_id] = gate
        self._persist()
        return gate

    def resolve_gate(
        self, gate_id: str, user_response: str, approve: bool = True
    ) -> HITLInterruptionGate | None:
        """Resolve a pending gate and persist the PO response."""
        with self._lock:
            gate = self.active_gates.get(gate_id)
            if gate is None:
                return None
            gate.status = "APPROVED" if approve else "REJECTED"
            gate.user_response = user_response
        self._persist()
        return gate

    def get_gate(self, gate_id: str) -> HITLInterruptionGate | None:
        with self._lock:
            return self.active_gates.get(gate_id)

    def list_gates(self) -> list[HITLInterruptionGate]:
        with self._lock:
            return list(self.active_gates.values())
