import shlex

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


def validate_command(cmd_str: str, policy: PolicyRules) -> tuple[bool, str]:
    """Validate a shell command string against a policy ruleset.

    Decomposes chained commands and evaluates each subcommand separately.
    Returns (is_safe, error_reason).
    """
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

        # 2. Check protected paths
        for path in policy.protected_paths:
            for token in tokens:
                if path in token:
                    return (
                        False,
                        f"Access to protected path '{path}' is denied in command '{sub_cmd}'",
                    )

        # 3. Check allowed commands list (if configured and not empty)
        if policy.allowed_commands:
            is_allowed = False
            for allowed in policy.allowed_commands:
                try:
                    allowed_tokens = shlex.split(allowed)
                except Exception:
                    allowed_tokens = allowed.split()

                if not allowed_tokens:
                    continue

                if (
                    len(tokens) >= len(allowed_tokens)
                    and tokens[: len(allowed_tokens)] == allowed_tokens
                ):
                    is_allowed = True
                    break

            if not is_allowed:
                return False, f"Command '{sub_cmd}' is not in the allowed commands list"

    return True, ""
