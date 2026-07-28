import logging
from typing import Any

from localforge.models import domain
from localforge.models.enums import ActionKind, AutonomyEnforcementResult, AutonomyLevel

logger = logging.getLogger(__name__)

AUTONOMY_RULES: dict[AutonomyLevel, domain.AutonomyPolicyRule] = {
    AutonomyLevel.L0_SIMULATE: domain.AutonomyPolicyRule(
        autonomy_level=AutonomyLevel.L0_SIMULATE,
        allow_file_write=False,
        allow_command_execution=False,
        allow_git_commit=False,
        allow_pr_ready=False,
        allow_auto_merge=False,
    ),
    AutonomyLevel.L1_INSPECT: domain.AutonomyPolicyRule(
        autonomy_level=AutonomyLevel.L1_INSPECT,
        allow_file_write=False,
        allow_command_execution=True,  # Read-only inspection commands allowed
        allow_git_commit=False,
        allow_pr_ready=False,
        allow_auto_merge=False,
    ),
    AutonomyLevel.L2_ISOLATED: domain.AutonomyPolicyRule(
        autonomy_level=AutonomyLevel.L2_ISOLATED,
        allow_file_write=True,
        allow_command_execution=True,
        allow_git_commit=True,
        allow_pr_ready=False,  # Human review required before PR_READY
        allow_auto_merge=False,
    ),
    AutonomyLevel.L3_UNATTENDED: domain.AutonomyPolicyRule(
        autonomy_level=AutonomyLevel.L3_UNATTENDED,
        allow_file_write=True,
        allow_command_execution=True,
        allow_git_commit=True,
        allow_pr_ready=True,  # PR_READY allowed automatically
        allow_auto_merge=False,  # Merge ALWAYS requires human approval
    ),
}


class AutonomyService:
    """Service layer enforcing L0-L3 server autonomy policies before actions are executed."""

    @staticmethod
    def get_rule_for_level(level: AutonomyLevel) -> domain.AutonomyPolicyRule:
        return AUTONOMY_RULES.get(level, AUTONOMY_RULES[AutonomyLevel.L0_SIMULATE])

    def evaluate_action(
        self,
        level: AutonomyLevel,
        action_kind: ActionKind | str,
        target: str | None = None,
    ) -> tuple[bool, AutonomyEnforcementResult, str]:
        """Evaluate if an action is permitted under the given AutonomyLevel.

        Returns:
            (allowed: bool, result_code: AutonomyEnforcementResult, reason: str)
        """
        rule = self.get_rule_for_level(level)
        action_str = action_kind.value if isinstance(action_kind, ActionKind) else str(action_kind)

        if action_str == ActionKind.WRITE_FILE.value:
            if not rule.allow_file_write:
                reason = f"File write to '{target}' rejected under autonomy level {level.value}."
                logger.warning(reason)
                return False, AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED, reason

        elif action_str == ActionKind.RUN_COMMAND.value:
            if not rule.allow_command_execution:
                reason = f"Command execution '{target}' rejected under autonomy level {level.value}."
                logger.warning(reason)
                return False, AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED, reason

        elif action_str == "git_commit":
            if not rule.allow_git_commit:
                reason = f"Git commit rejected under autonomy level {level.value}."
                logger.warning(reason)
                return False, AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED, reason

        elif action_str == "pr_ready":
            if not rule.allow_pr_ready:
                reason = f"Transition to PR_READY rejected under autonomy level {level.value} (requires L3_UNATTENDED or human review)."
                logger.warning(reason)
                return False, AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED, reason

        elif action_str == "git_merge":
            if not rule.allow_auto_merge:
                reason = "Git merge is ALWAYS denied for automated agents under all autonomy levels (requires human approval)."
                logger.warning(reason)
                return False, AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED, reason

        return True, AutonomyEnforcementResult.ALLOWED, f"Action '{action_str}' permitted under {level.value}."
