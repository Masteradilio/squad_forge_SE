import os
import shlex
from pathlib import PureWindowsPath

from localforge.core.policy import PolicyRules


def split_shell_commands(cmd_str: str) -> list[str]:
    """Split a shell command line into individual subcommands by operators:

    &&, ||, ;, | (pipes).
    Respects single quotes, double quotes, and backslash escapes.
    """
    commands: list[str] = []
    current: list[str] = []
    in_double_quote = False
    in_single_quote = False
    escape = False
    i = 0
    n = len(cmd_str)

    while i < n:
        char = cmd_str[i]

        if escape:
            current.append(char)
            escape = False
            i += 1
            continue

        if char == "\\":
            current.append(char)
            escape = True
            i += 1
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
            i += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
            i += 1
            continue

        if not in_double_quote and not in_single_quote:
            # Check for &&
            if i + 1 < n and cmd_str[i : i + 2] == "&&":
                commands.append("".join(current).strip())
                current = []
                i += 2
                continue
            # Check for ||
            if i + 1 < n and cmd_str[i : i + 2] == "||":
                commands.append("".join(current).strip())
                current = []
                i += 2
                continue
            # Check for ;
            if char == ";":
                commands.append("".join(current).strip())
                current = []
                i += 1
                continue
            # Check for | (pipe, not part of ||)
            if char == "|":
                commands.append("".join(current).strip())
                current = []
                i += 1
                continue

        current.append(char)
        i += 1

    if current:
        commands.append("".join(current).strip())

    return [cmd for cmd in commands if cmd]


def command_to_argv(cmd_str: str) -> list[str]:
    """Parse one non-shell command for direct process execution.

    Commands that need shell semantics must be broken into individual approved
    actions by the caller.  This keeps direct executors from reinterpreting
    command substitutions, pipes, redirections, or chained commands.
    """
    unsafe_syntax = _unsafe_shell_syntax_reason(cmd_str)
    if unsafe_syntax:
        raise ValueError(unsafe_syntax)

    commands = split_shell_commands(cmd_str)
    if len(commands) != 1 or commands[0] != cmd_str.strip():
        raise ValueError("Shell operators are not supported for direct execution")

    try:
        tokens = _split_direct_command(cmd_str, windows=os.name == "nt")
    except ValueError as exc:
        raise ValueError(f"Failed to tokenize command: {exc}") from exc

    if not tokens:
        raise ValueError("Empty command")

    return tokens


def _split_direct_command(command: str, *, windows: bool) -> list[str]:
    """Tokenize a direct command without corrupting quoted Windows paths."""
    tokens = shlex.split(command, posix=not windows)
    if not windows:
        return tokens
    return [
        token[1:-1]
        if len(token) >= 2 and token.startswith('"') and token.endswith('"')
        else token
        for token in tokens
    ]


def _unsafe_shell_syntax_reason(command: str) -> str | None:
    """Return a reason when shell-only syntax appears outside a literal string."""
    in_double_quote = False
    in_single_quote = False
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\" and not in_single_quote:
            escaped = True
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue
        if in_single_quote:
            continue
        if char in {">", "<"} and not in_double_quote:
            return "Shell redirection is not supported"
        if char == "`" or (char == "$" and index + 1 < len(command) and command[index + 1] == "("):
            return "Command substitution is not supported"
    return None


def validate_command(cmd_str: str, policy: PolicyRules) -> tuple[bool, str]:
    """Validate a shell command string against a policy ruleset.

    Decomposes chained commands and evaluates each subcommand separately.
    Returns (is_safe, error_reason).
    """
    unsafe_syntax = _unsafe_shell_syntax_reason(cmd_str)
    if unsafe_syntax:
        return False, unsafe_syntax

    try:
        subcommands = split_shell_commands(cmd_str)
    except Exception as e:
        return False, f"Failed to parse shell operators: {e}"

    if not subcommands:
        return False, "Empty command"

    for sub_cmd in subcommands:
        try:
            tokens = shlex.split(sub_cmd)
        except Exception as e:
            return False, f"Failed to tokenize command '{sub_cmd}': {e}"

        if not tokens:
            continue

        # 1. Check blocked commands list
        for blocked in policy.blocked_commands:
            try:
                blocked_tokens = shlex.split(blocked)
            except Exception:
                blocked_tokens = blocked.split()

            if not blocked_tokens:
                continue

            # Exact prefix match of command and arguments
            if (
                len(tokens) >= len(blocked_tokens)
                and tokens[: len(blocked_tokens)] == blocked_tokens
            ):
                return False, f"Blocked command match: '{blocked}' in '{sub_cmd}'"

            # Check if any blocked pattern matches as a substring of the subcommand (e.g. rm -rf)
            if blocked in sub_cmd:
                return False, f"Blocked command pattern: '{blocked}' in '{sub_cmd}'"

        # 2. Check protected paths (standardized separators and case-insensitive check)
        for path in policy.protected_paths:
            normalized_path = path.replace("\\", "/").lower()
            for token in tokens:
                normalized_token = token.replace("\\", "/").lower()
                if normalized_path in normalized_token:
                    return (
                        False,
                        f"Access to protected path '{path}' is denied in command '{sub_cmd}'",
                    )

        # 3. Check allowed commands list (if configured and not empty)
        if policy.allowed_commands:
            is_allowed = False
            comparable_tokens = _normalize_command_tokens(tokens)
            for allowed in policy.allowed_commands:
                try:
                    allowed_tokens = shlex.split(allowed)
                except Exception:
                    allowed_tokens = allowed.split()

                if not allowed_tokens:
                    continue

                if (
                    len(comparable_tokens) >= len(allowed_tokens)
                    and comparable_tokens[: len(allowed_tokens)] == allowed_tokens
                ):
                    is_allowed = True
                    break

            if not is_allowed:
                return False, f"Command '{sub_cmd}' is not in the allowed commands list"

    return True, ""


def _normalize_command_tokens(tokens: list[str]) -> list[str]:
    if not tokens:
        return tokens
    executable = tokens[0].replace("\\", "/").lower()
    name = PureWindowsPath(executable).name
    if name in {"python", "python.exe"}:
        return ["python", *tokens[1:]]
    return tokens
