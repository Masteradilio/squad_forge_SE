"""Stable filesystem bindings for durable ForgeOS goals."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def goal_id_for_project(
    project_id: int, resource_limits: Mapping[str, Any] | None = None
) -> str:
    """Return the lifetime goal identity shared by scheduler and API.

    A run may opt into a separate durable goal with ``goal_id`` in its
    resource limits. The default is intentionally project-scoped so a process
    restart or a new worker run resumes the same objective instead of silently
    creating a new control plane.
    """

    configured = (resource_limits or {}).get("goal_id")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return f"project:{project_id}:lifetime"


def state_path_for_goal(
    project_root: str | Path,
    goal_id: str,
    database_identity: object = "default",
) -> Path:
    """Build a stable, collision-resistant state path without using run IDs."""

    identity = str(database_identity)
    digest = hashlib.sha256(
        f"{goal_id}:{Path(project_root).resolve()}:{identity}".encode("utf-8")
    ).hexdigest()[:16]
    return (
        Path(project_root)
        / ".localforge"
        / "control_plane"
        / f"goal-{digest}.json"
    )
