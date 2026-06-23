from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContractChangeRequest:
    task_key: str
    requested_files: list[str] = field(default_factory=list)
    requested_dependencies: list[str] = field(default_factory=list)
    requested_public_apis: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass(frozen=True)
class ContractChangeDecision:
    approved: bool
    requires_chief_engineer: bool
    reason: str
    updated_contract: dict[str, Any] | None = None


class ContractChangeService:
    def evaluate(
        self,
        contract: dict[str, Any],
        request: ContractChangeRequest,
    ) -> ContractChangeDecision:
        allowed_files = _strings(contract.get("allowed_files"))
        forbidden_dependencies = _strings(contract.get("forbidden_dependencies"))
        public_apis = _strings(contract.get("required_public_apis"))

        new_files = [path for path in request.requested_files if path not in allowed_files]
        forbidden = [
            dep for dep in request.requested_dependencies if dep in forbidden_dependencies
        ]
        new_apis = [
            api for api in request.requested_public_apis if api not in public_apis
        ]
        if forbidden:
            return ContractChangeDecision(
                approved=False,
                requires_chief_engineer=True,
                reason=f"Requested forbidden dependency requires Chief Engineer approval: {', '.join(forbidden)}",
            )
        if new_files or new_apis or request.requested_dependencies:
            return ContractChangeDecision(
                approved=False,
                requires_chief_engineer=True,
                reason="Contract expansion requires Chief Engineer approval.",
            )
        return ContractChangeDecision(
            approved=True,
            requires_chief_engineer=False,
            reason="Request is already within the frozen contract.",
            updated_contract=contract,
        )


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
