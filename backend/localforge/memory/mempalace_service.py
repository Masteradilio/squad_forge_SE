"""MemPalace Service — Verbatim 'Method of Loci' Session & ADR Persistence Vault."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


class MemPalaceService:
    """Verbatim session state, decision, and file context persistence service."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_loci_memory(self, project_id: str, chamber_name: str, memory_data: Dict[str, Any]) -> str:
        """Store verbatim decision/session memory in a spatial project chamber."""
        chamber_dir = self.storage_dir / project_id / chamber_name
        chamber_dir.mkdir(parents=True, exist_ok=True)

        memory_id = f"mem_{int(memory_data.get('timestamp', 0)) or 1}"
        file_path = chamber_dir / f"{memory_id}.json"
        file_path.write_text(json.dumps(memory_data, indent=2), encoding="utf-8")

        logger.info(f"MemPalace stored verbatim memory '{memory_id}' in chamber '{chamber_name}' for project '{project_id}'.")
        return str(file_path)

    def recall_project_memories(self, project_id: str, chamber_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recall verbatim memories for a project without lossy LLM summarization."""
        project_dir = self.storage_dir / project_id
        if not project_dir.exists():
            return []

        results = []
        chambers = [project_dir / chamber_name] if chamber_name else project_dir.iterdir()

        for ch in chambers:
            if ch.is_dir():
                for json_file in ch.glob("*.json"):
                    try:
                        data = json.loads(json_file.read_text(encoding="utf-8"))
                        results.append(data)
                    except Exception:
                        continue

        return results
