import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from localforge.core.policy import PolicyRules
from localforge.core.templates import DEFAULT_POLICY_TEMPLATE
from localforge.models.enums import ActionKind
from localforge.safety.command_validator import validate_command
from localforge.storage import UnitOfWork


class SafetyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ActionRequest(BaseModel):
    """Normalized payload request for Safety Kernel validation."""

    project_id: int
    run_id: int | None = None
    task_id: int | None = None
    kind: ActionKind
    payload: dict[str, Any] = Field(default_factory=dict)
    purpose: str
    risk_level: str = "low"  # low, medium, high

    @model_validator(mode="after")
    def validate_payload_requirements(self) -> "ActionRequest":
        """Strict verification of payload keys depending on action kind."""
        if self.kind in (ActionKind.READ_FILE, ActionKind.WRITE_FILE):
            if "path" not in self.payload or not self.payload["path"]:
                raise ValueError(f"Path string is required in payload for kind '{self.kind}'")
        elif self.kind in (ActionKind.RUN_COMMAND, ActionKind.GIT_COMMAND):
            if "command" not in self.payload or not self.payload["command"]:
                raise ValueError(f"Command string is required in payload for kind '{self.kind}'")
        return self


def is_path_safe(target_path: str, root_path: str) -> bool:
    """Check if the target path resides securely inside the root directory.

    Canonicalizes absolute paths and resolves symlinks to prevent path traversal
    attacks (../).
    """
    try:
        # Standardize path separators and drive letters
        real_target = os.path.realpath(os.path.abspath(target_path))
        real_root = os.path.realpath(os.path.abspath(root_path))

        # On Windows, drive letters and paths are case-insensitive
        if os.name == "nt":
            real_target_norm = os.path.normcase(real_target)
            real_root_norm = os.path.normcase(real_root)
            common = os.path.commonpath([real_target_norm, real_root_norm])
            return os.path.normcase(common) == real_root_norm
        else:
            common = os.path.commonpath([real_target, real_root])
            return common == real_root
    except Exception:
        return False


class SafetyKernel:
    """Mediator evaluating action requests against project policy rules."""

    @staticmethod
    async def evaluate(
        request: ActionRequest, uow: UnitOfWork, project_root: str
    ) -> tuple[SafetyDecision, str]:
        """Evaluate an ActionRequest against active policy rules.

        Returns (SafetyDecision, reasoning).
        """
        # 1. Fetch project rules from policy
        assert uow.audits is not None
        policy_obj = await uow.audits.get_project_policy(request.project_id, "default")
        if policy_obj:
            policy_rules = PolicyRules.model_validate(policy_obj.rules)
        else:
            # Fallback to default conservative template rules
            policy_rules = PolicyRules.model_validate(DEFAULT_POLICY_TEMPLATE["policy"])

        # 2. Evaluate File Actions (read/write)
        if request.kind in (ActionKind.READ_FILE, ActionKind.WRITE_FILE):
            target = request.payload["path"]

            # Enforce path canonicalization boundaries for writes
            if request.kind == ActionKind.WRITE_FILE:
                if not is_path_safe(target, project_root):
                    return (
                        SafetyDecision.DENY,
                        f"Write action outside workspace root is blocked: {target}",
                    )

            # Resolve real target path to check protected path segments
            try:
                real_target = os.path.realpath(os.path.abspath(target))
            except Exception:
                real_target = target

            for protected in policy_rules.protected_paths:
                norm_protected = protected.replace("\\", "/").lower()
                norm_real_target = real_target.replace("\\", "/").lower()
                norm_target = target.replace("\\", "/").lower()

                # Check if protected path segment exists in absolute target path (case-insensitive)
                if norm_protected in norm_real_target or norm_protected in norm_target:
                    return (
                        SafetyDecision.DENY,
                        f"Access to protected path '{protected}' is denied: {target}",
                    )

        # 3. Evaluate Command Actions
        elif request.kind in (ActionKind.RUN_COMMAND, ActionKind.GIT_COMMAND):
            command = request.payload["command"]
            is_safe, error_reason = validate_command(command, policy_rules)
            if not is_safe:
                return SafetyDecision.DENY, f"Command safety check failed: {error_reason}"

            # Escalate high/medium risk command inputs to requiring approval unless they are automated pipeline actions (staging/test validation)
            is_git_or_test = (
                command.strip().startswith("git add")
                or command.strip().startswith("git commit")
                or (command.strip().startswith("git checkout") and "localforge" in command)
                or ("pytest" in command and ("tests/" in command or "test_" in command))
            )

            if request.risk_level in ("high", "medium") and not is_git_or_test:
                return (
                    SafetyDecision.REQUIRE_APPROVAL,
                    f"Command request has escalated risk level: {request.risk_level}",
                )

        # 4. Handle other action requests escalation
        elif request.risk_level in ("high", "medium"):
            return (
                SafetyDecision.REQUIRE_APPROVAL,
                f"Action kind '{request.kind}' requires approval due to "
                f"risk level '{request.risk_level}'",
            )

        return SafetyDecision.ALLOW, "Action complies with policy rules."
