import pytest

from localforge.core.policy import PolicyRules
from localforge.models.enums import ActionKind
from localforge.safety.command_validator import validate_command
from localforge.safety.kernel import ActionRequest, SafetyDecision, SafetyKernel, is_path_safe
from localforge.safety.pre_pr_gate import MechanicalPrePRGate
from localforge.storage import UnitOfWork


def test_path_traversal_escape_blocked() -> None:
    """Test V6-403: Path traversal escapes (../../.env) must be blocked deterministically."""
    workspace_root = "E:/workspace/project"

    # Traversal relative paths
    assert is_path_safe("../../.env", workspace_root) is False
    assert is_path_safe("E:/workspace/project/../../.env", workspace_root) is False

    # Normal child path inside workspace root
    assert is_path_safe("E:/workspace/project/src/main.py", workspace_root) is True


@pytest.mark.asyncio
async def test_protected_paths_denial(db_manager) -> None:
    """Test V6-400 & V6-401: Access to protected paths (.env, credentials) must return DENY."""
    async with UnitOfWork(db_manager) as uow:
        req = ActionRequest(
            project_id=1,
            kind=ActionKind.WRITE_FILE,
            payload={"path": "E:/workspace/project/.env"},
            purpose="Writing secret key",
            risk_level="high",
        )
        decision, reason = await SafetyKernel.evaluate(req, uow, "E:/workspace/project")
        assert decision == SafetyDecision.DENY
        assert "protected path" in reason or "workspace root" in reason


def test_command_validation_dangerous_syntax() -> None:
    """Test V6-403: Block dangerous command syntax, redirection, and prohibited executables."""
    policy = PolicyRules(
        allowed_commands=["pytest", "git", "npm"],
        blocked_commands=["rm -rf", "format", "del /f"],
        protected_paths=[".env"],
    )

    # Shell redirection blocked
    safe_redir, reason_redir = validate_command("echo hello > output.txt", policy)
    assert safe_redir is False
    assert "redirection" in reason_redir

    # Command substitution blocked
    safe_sub, reason_sub = validate_command("echo $(cat .env)", policy)
    assert safe_sub is False
    assert "substitution" in reason_sub

    # Blocked command phrase
    safe_del, reason_del = validate_command("rm -rf /", policy)
    assert safe_del is False
    assert "blocked" in reason_del.lower() or "unauthorized" in reason_del.lower()


@pytest.mark.asyncio
async def test_mechanical_pre_pr_gate(db_manager) -> None:
    """Test V6-402: Pre-PR gate performs secret scanning, file count limit, and verifier check."""
    gate = MechanicalPrePRGate()

    # Secret scanning check
    diff_with_secret = '+ API_KEY = "sk-live-1234567890123456"'
    secrets_found = gate.scan_diff_for_secrets(diff_with_secret)
    assert len(secrets_found) > 0
    assert "Secret pattern matched" in secrets_found[0]

    # Evaluate full gate on empty task_run (no verifier approval) -> Fails gate
    async with UnitOfWork(db_manager) as uow:
        res = await gate.evaluate_gate(
            project_id=1,
            task_run_id=9999,
            uow=uow,
            diff_text=diff_with_secret,
            modified_files=["src/app.py", ".env"],
            max_file_limit=1,
        )
        assert res.passed is False
        assert res.checks["secret_scanning"] is False
        assert res.checks["file_count_limit"] is False
        assert res.checks["protected_paths"] is False
        assert res.checks["verifier_evidence"] is False
