"""Chief Engineer Interface Contracts Service — Freezes interface contracts before code implementation."""

from pathlib import Path

import pydantic


class InterfaceContract(pydantic.BaseModel):
    contract_id: str
    target_filepath: str
    content: str
    is_frozen: bool = True


class InterfaceContractsService:
    """Service to freeze and validate interface contracts (.types.ts / Pydantic schemas)."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.frozen_contracts: dict[str, InterfaceContract] = {}

    def freeze_contract(self, relative_path: str, content: str) -> InterfaceContract:
        """Freeze an interface contract file in the workspace."""
        full_path = self.workspace_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

        contract = InterfaceContract(
            contract_id=relative_path,
            target_filepath=str(full_path),
            content=content,
            is_frozen=True,
        )
        self.frozen_contracts[relative_path] = contract
        return contract

    def get_frozen_contracts(self) -> list[InterfaceContract]:
        return list(self.frozen_contracts.values())
