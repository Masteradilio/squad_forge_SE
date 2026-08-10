"""Mark every task in the active workspace as local_assisted / low risk.

Used by the V5.1 demo to remove the Chief Engineer escalation and let
tasks complete against the configured local Ollama lane. This is a
demo-only convenience: real workloads keep the inferred contract.

Usage:
    python scripts/apply_demo_local_first.py [PROJECT_ROOT]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def main(project_root: str) -> int:
    db_path = Path(project_root) / ".localforge" / "localforge.db"
    if not db_path.exists():
        sys.stderr.write(f"Database not found at {db_path}\n")
        return 2

    connection = sqlite3.connect(db_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id, metadata_json, risk_level FROM tasks ORDER BY id"
        )
        rows = cursor.fetchall()
        if not rows:
            sys.stderr.write("No tasks to update; import a PRD first.\n")
            return 3

        updates: list[tuple[str, str, int]] = []
        for task_id, raw_metadata, _risk in rows:
            try:
                metadata = (
                    json.loads(raw_metadata)
                    if isinstance(raw_metadata, str)
                    else (raw_metadata or {})
                )
            except Exception:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            contract = metadata.get("task_contract")
            if not isinstance(contract, dict):
                contract = {}
            contract["seniority_class"] = "local_assisted"
            contract["visual_required"] = False
            contract["risk_level"] = "low"
            contract["canonical_test_command"] = (
                contract.get("canonical_test_command")
                or "python -m pytest tests -q"
            )
            contract.pop("visual_reference_image", None)
            contract.pop("visual_actual_output", None)
            contract.pop("visual_similarity_threshold", None)
            contract.pop("visual_viewport", None)
            metadata["task_contract"] = contract
            metadata["demo_local_first"] = True
            updates.append(("low", json.dumps(metadata), task_id))

        cursor.executemany(
            "UPDATE tasks SET risk_level = ?, metadata_json = ? WHERE id = ?",
            updates,
        )
        connection.commit()
        sys.stdout.write(
            f"Annotated {len(updates)} task(s) as local_assisted / low risk.\n"
        )
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "project_root",
        nargs="?",
        default=os.getcwd(),
        help="Workspace root that contains .localforge/localforge.db",
    )
    args = parser.parse_args()
    raise SystemExit(main(args.project_root))
