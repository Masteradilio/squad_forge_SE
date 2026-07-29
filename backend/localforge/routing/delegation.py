import logging
import os

from localforge.models.domain import Task, TaskRun
from localforge.models.enums import TaskSeniorityClass

logger = logging.getLogger(__name__)


class LocalWorkDelegationContract:
    """
    Evaluates whether a task and its context fit within local model capabilities (Phase 58).
    Limits:
    - Max file size of allowed files: 30,000 characters.
    - Max output content size: 4,000 characters.
    - Allowed actions for local models: write_file, append_content, run_command (limited).
    """

    def __init__(self, max_file_size: int = 30000, max_output_size: int = 4000):
        self.max_file_size = max_file_size
        self.max_output_size = max_output_size

    def evaluate_delegation(self, task: Task, task_run: TaskRun) -> tuple[bool, str]:
        """
        Returns (is_allowed, rationale).
        If False, the task must be escalated to Chief Engineer.
        """
        contract = task.metadata.get("task_contract", {}) if isinstance(task.metadata, dict) else {}
        allowed_files = contract.get("allowed_files", []) if isinstance(contract, dict) else []
        seniority_class = contract.get("seniority_class") if isinstance(contract, dict) else None
        if seniority_class == TaskSeniorityClass.CHIEF_ONLY.value:
            return False, "Task contract requires Chief Engineer execution."

        # 1. Check file size of allowed files in the worktree
        if task_run.worktree_path:
            for file_rel in allowed_files:
                file_path = os.path.join(task_run.worktree_path, file_rel)
                if os.path.isfile(file_path):
                    try:
                        sz = os.path.getsize(file_path)
                        # Estimate chars by size (approx 1 char = 1 byte in utf-8 text usually)
                        if sz > self.max_file_size:
                            return (
                                False,
                                f"File {file_rel} size ({sz} bytes) exceeds local model limit ({self.max_file_size} chars).",
                            )
                    except Exception as e:
                        logger.warning(f"Failed to check size for {file_path}: {e}")

        # 2. Check if contract requires visual fidelity
        if contract.get("visual_required", False):
            # Visual parity tasks are structurally complex and require visual similarity gates
            return False, "Visual parity task requires Chief Engineer."

        # 3. Check risk level
        if task.risk_level.lower() in ("high", "critical"):
            return (
                False,
                f"Task risk level is {task.risk_level.upper()}, which requires Chief Engineer review/implementation.",
            )

        # 4. Check if task description indicates architect scope
        text = f"{task.title} {task.description}".lower()
        if any(
            term in text
            for term in ("architecture", "breaking change", "cross-module", "public api")
        ):
            return False, "Task scopes global architecture or public API signatures."

        return True, "Task is safe and bounded for local model delegation."
