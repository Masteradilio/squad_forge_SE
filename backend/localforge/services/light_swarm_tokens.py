"""Light Swarm security tokens and maker/checker separation helpers (V61C-601)."""

import hashlib
import hmac
import os

from localforge.models.enums import SwarmNodeType

DEFAULT_TOKEN_SECRET = os.getenv("LIGHT_SWARM_SECRET", "localforge-light-swarm-token-secret-v1")


def generate_node_ownership_token(
    run_id: int, node_id: str, attempt_count: int = 1, secret: str = DEFAULT_TOKEN_SECRET
) -> str:
    """Generate a deterministic HMAC ownership token for worker callbacks."""
    msg = f"run:{run_id}:node:{node_id}:attempt:{attempt_count}".encode()
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_node_ownership_token(
    token: str | None,
    expected_token: str | None,
    run_id: int,
    node_id: str,
    attempt_count: int = 1,
    secret: str = DEFAULT_TOKEN_SECRET,
) -> bool:
    """Verify ownership token matches either expected_token or generated HMAC token."""
    if not token:
        return False
    if expected_token and hmac.compare_digest(token, expected_token):
        return True
    computed = generate_node_ownership_token(run_id, node_id, attempt_count, secret)
    return hmac.compare_digest(token, computed)


def validate_maker_checker_identity(
    node_type: SwarmNodeType,
    checker_agent_id: str | None,
    maker_agent_id: str | None,
) -> tuple[bool, str | None]:
    """Ensure CRITIQUE or VERIFY nodes do not share identity with IMPLEMENT nodes (V61C-601)."""
    if node_type in (SwarmNodeType.CRITIQUE, SwarmNodeType.VERIFY):
        if checker_agent_id and maker_agent_id and checker_agent_id == maker_agent_id:
            return (
                False,
                f"Maker/Checker violation: Node {node_type.value} agent '{checker_agent_id}' matches maker agent '{maker_agent_id}'.",
            )
    return True, None
