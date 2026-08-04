"""MemPalace Service — Verbatim 'Method of Loci' Session & ADR Persistence Vault."""

import json
import logging
import re
import secrets
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemPalaceService:
    """Verbatim session state, decision, and file context persistence service."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_loci_memory(self, project_id: str, chamber_name: str, memory_data: dict[str, Any]) -> str:
        """Store verbatim decision/session memory in a spatial project chamber."""
        safe_project = self._safe_component(project_id)
        safe_chamber = self._safe_component(chamber_name)
        chamber_dir = self.storage_dir / safe_project / safe_chamber
        chamber_dir.mkdir(parents=True, exist_ok=True)

        memory_id = f"mem_{secrets.token_hex(10)}"
        file_path = chamber_dir / f"{memory_id}.json"
        file_path.write_text(json.dumps(memory_data, indent=2), encoding="utf-8")

        logger.info(f"MemPalace stored verbatim memory '{memory_id}' in chamber '{chamber_name}' for project '{project_id}'.")
        return str(file_path)

    @staticmethod
    def _safe_component(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(value)).strip("._")
        if not safe or safe in {".", ".."}:
            raise ValueError("memory path component must contain a safe name")
        return safe[:120]

    def recall_project_memories(self, project_id: str, chamber_name: str | None = None) -> list[dict[str, Any]]:
        """Recall verbatim memories for a project without lossy LLM summarization."""
        project_dir = self.storage_dir / self._safe_component(project_id)
        if not project_dir.exists():
            return []

        results = []
        chambers = (
            [project_dir / self._safe_component(chamber_name)]
            if chamber_name
            else project_dir.iterdir()
        )

        for ch in chambers:
            if ch.is_dir():
                for json_file in ch.glob("*.json"):
                    try:
                        data = json.loads(json_file.read_text(encoding="utf-8"))
                        results.append(data)
                    except Exception:
                        continue

        return results
