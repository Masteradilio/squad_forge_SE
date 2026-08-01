"""Reviewer Scope Validator — File Scope Locking (Max 3-5 files per task contract)."""

from typing import List, Tuple


class FileScopeValidator:
    """Enforces strict File Scope Locking (max 3-5 files modified per ticket)."""

    def __init__(self, max_allowed_files: int = 5):
        self.max_allowed_files = max_allowed_files

    def validate_diff_scope(
        self, modified_files: List[str], contract_allowed_files: List[str]
    ) -> Tuple[bool, str]:
        """Validate if modified files stay strictly within allowed task scope boundaries."""
        if len(modified_files) > self.max_allowed_files:
            return (
                False,
                f"File Scope Lock Violation: Modified {len(modified_files)} files, "
                f"exceeding maximum limit of {self.max_allowed_files} files.",
            )

        unauthorized = [
            f for f in modified_files if contract_allowed_files and f not in contract_allowed_files
        ]
        if unauthorized:
            return (
                False,
                f"File Scope Lock Violation: Attempted to modify unauthorized files outside task contract: {unauthorized}",
            )

        return (True, "File scope validation passed cleanly.")
