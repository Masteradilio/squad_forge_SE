from dataclasses import dataclass

from localforge.models.enums import (
    ActionKind,
    AutonomyEnforcementResult,
    AutonomyLevel,
)
from localforge.safety.kernel import ActionRequest, SafetyDecision, SafetyKernel
from localforge.services.autonomy import AutonomyService
from localforge.storage import UnitOfWork


@dataclass(frozen=True)
class ActionGatewayDecision:
    decision: SafetyDecision
    reason: str
    autonomy_result: AutonomyEnforcementResult


class ActionGateway:
    """Single policy checkpoint before runtime side effects are executed."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.autonomy = AutonomyService()

    async def evaluate(
        self,
        request: ActionRequest,
        *,
        project_root: str,
        autonomy_level: AutonomyLevel,
    ) -> ActionGatewayDecision:
        target = self._target_for(request)
        allowed, autonomy_result, autonomy_reason = self.autonomy.evaluate_action(
            autonomy_level,
            request.kind,
            target,
        )
        if not allowed:
            return ActionGatewayDecision(
                decision=SafetyDecision.DENY,
                reason=autonomy_reason,
                autonomy_result=autonomy_result,
            )
        decision, safety_reason = await SafetyKernel.evaluate(request, self.uow, project_root)
        return ActionGatewayDecision(
            decision=decision,
            reason=safety_reason,
            autonomy_result=autonomy_result,
        )

    @staticmethod
    def _target_for(request: ActionRequest) -> str | None:
        if request.kind in (ActionKind.READ_FILE, ActionKind.WRITE_FILE):
            return str(request.payload.get("path") or "")
        if request.kind in (ActionKind.RUN_COMMAND, ActionKind.GIT_COMMAND):
            return str(request.payload.get("command") or "")
        return None
