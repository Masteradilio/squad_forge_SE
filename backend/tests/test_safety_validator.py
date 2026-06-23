from localforge.core.policy import PolicyRules
from localforge.safety import split_shell_commands, validate_command


def test_split_shell_commands_basic():
    """Verify that split_shell_commands correctly splits on operators outside quotes."""
    cmd1 = "git status && rm -rf"
    assert split_shell_commands(cmd1) == ["git status", "rm -rf"]

    cmd2 = "echo 'hello && world' ; grep 'hello'"
    assert split_shell_commands(cmd2) == ["echo 'hello && world'", "grep 'hello'"]

    cmd3 = 'echo "hello || world" | grep hello'
    assert split_shell_commands(cmd3) == ['echo "hello || world"', "grep hello"]

    # No spaces around separator
    cmd4 = "git status&&rm -rf"
    assert split_shell_commands(cmd4) == ["git status", "rm -rf"]


def test_split_shell_commands_quotes():
    """Verify that separators inside quotes are ignored."""
    cmd = 'git commit -m "feat: initial commit; added files && docs"'
    expected = ['git commit -m "feat: initial commit; added files && docs"']
    assert split_shell_commands(cmd) == expected


def test_validate_command_blocked():
    """Verify that validate_command flags blocked commands even when chained."""
    policy = PolicyRules(
        blocked_commands=["rm -rf", "git push --force"],
        allowed_commands=[],
        protected_paths=[],
    )

    # Simple allowed command
    safe, reason = validate_command("git status", policy)
    assert safe is True

    # Simple blocked command
    safe, reason = validate_command("rm -rf /", policy)
    assert safe is False
    assert "Blocked command" in reason

    # Chained command containing a blocked subcommand
    safe, reason = validate_command("git status && rm -rf /tmp/test", policy)
    assert safe is False
    assert "Blocked command" in reason

    # Chained command with pipe containing blocked command
    safe, reason = validate_command("echo test | git push --force", policy)
    assert safe is False
    assert "Blocked command" in reason


def test_validate_command_protected_paths():
    """Verify that commands touching protected paths are blocked."""
    policy = PolicyRules(
        blocked_commands=[],
        allowed_commands=[],
        protected_paths=[".env", "config/secrets.yaml"],
    )

    # Touch clean path
    safe, reason = validate_command("cat README.md", policy)
    assert safe is True

    # Touch protected path
    safe, reason = validate_command("cat .env", policy)
    assert safe is False
    assert "protected path" in reason

    # Chained command touching protected path
    safe, reason = validate_command("git status && cat config/secrets.yaml", policy)
    assert safe is False
    assert "protected path" in reason


def test_validate_command_allowed_list():
    """Verify that when allowed_commands is set, only matching commands pass."""
    policy = PolicyRules(
        blocked_commands=[],
        allowed_commands=["git status", "pytest", "ruff check"],
        protected_paths=[],
    )

    # Allowed command
    safe, reason = validate_command("git status", policy)
    assert safe is True

    # Allowed command with arguments
    safe, reason = validate_command("pytest backend/tests -v", policy)
    assert safe is True

    # Not allowed command
    safe, reason = validate_command("git commit -m 'done'", policy)
    assert safe is False
    assert "not in the allowed commands" in reason

    # Chained command where one part is not allowed
    safe, reason = validate_command("git status && git commit -m 'done'", policy)
    assert safe is False
    assert "not in the allowed commands" in reason


def test_validate_command_absolute_python_executable_matches_policy_prefix():
    """Verify venv-managed Python executables match the logical python allowlist."""
    policy = PolicyRules(
        blocked_commands=[],
        allowed_commands=["python -m pytest"],
        protected_paths=[],
    )

    command = r'"E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe" -m pytest -q'
    safe, reason = validate_command(command, policy)

    assert safe is True
    assert reason == ""
