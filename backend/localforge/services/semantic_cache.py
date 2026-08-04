"""Semantic Caching Module — Accelerates LLM completions & AST Graphify queries in ForgeOS Cloud."""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from localforge.services.redis_manager import redis_manager

logger = logging.getLogger(__name__)


class SemanticCacheManager:
    """Manages semantic and exact-match caching for LLM responses and AST graphs using Redis or disk fallback."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        similarity_threshold: float = 0.92,
        ttl_seconds: int = 86400,
    ):
        self.cache_dir = cache_dir or Path(".localforge") / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.similarity_threshold = float(
            os.getenv("FORGEOS_CACHE_SIMILARITY_THRESHOLD", str(similarity_threshold))
        )
        self.ttl_seconds = int(
            os.getenv("FORGEOS_CACHE_TTL_SECONDS", str(ttl_seconds))
        )
        self.enabled = os.getenv("FORGEOS_SEMANTIC_CACHE_ENABLED", "true").lower() == "true"
        self.redis = redis_manager

    def _compute_key(self, model: str, messages: list[dict[str, Any]]) -> str:
        """Compute deterministic SHA-256 key from model and chat message structure."""
        serialized = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_llm_completion(
        self, model: str, messages: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Retrieve cached LLM completion if available and unexpired."""
        if not self.enabled:
            return None

        cache_key = self._compute_key(model, messages)
        cache_file = self.cache_dir / f"llm_{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            content = json.loads(cache_file.read_text(encoding="utf-8"))
            timestamp = content.get("timestamp", 0)
            if time.time() - timestamp > self.ttl_seconds:
                cache_file.unlink(missing_ok=True)
                return None
            cached_data = content.get("data", {})
            if not isinstance(cached_data, dict):
                return None
            cached_data["cached"] = True
            cached_data["cache_key"] = cache_key
            return cached_data
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(f"Error reading cache file {cache_file}: {exc}")
            return None

    async def aget_llm_completion(
        self, model: str, messages: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Async cache lookup that actually uses Redis when it is reachable."""
        if not self.enabled:
            return None
        cache_key = self._compute_key(model, messages)
        redis_key = f"forgeos:llm:{cache_key}"
        cached = await self.redis.get(redis_key)
        if cached:
            try:
                data = json.loads(cached)
                if isinstance(data, dict):
                    data["cached"] = True
                    data["cache_key"] = cache_key
                    return data
            except json.JSONDecodeError:
                await self.redis.delete(redis_key)
        return self.get_llm_completion(model, messages)

    def set_llm_completion(
        self, model: str, messages: list[dict[str, Any]], data: dict[str, Any]
    ) -> None:
        """Store LLM completion into semantic cache."""
        if not self.enabled:
            return

        cache_key = self._compute_key(model, messages)
        cache_file = self.cache_dir / f"llm_{cache_key}.json"

        payload = {
            "timestamp": time.time(),
            "model": model,
            "data": data,
        }
        try:
            cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.debug(f"Saved completion to semantic cache ({cache_key[:8]})")
        except Exception as exc:
            logger.warning(f"Failed to write cache file {cache_file}: {exc}")

    async def aset_llm_completion(
        self, model: str, messages: list[dict[str, Any]], data: dict[str, Any]
    ) -> None:
        """Persist an LLM response to Redis and the deterministic disk fallback."""
        if not self.enabled:
            return
        cache_key = self._compute_key(model, messages)
        await self.redis.set(
            f"forgeos:llm:{cache_key}",
            json.dumps(data, separators=(",", ":")),
            ttl_seconds=self.ttl_seconds,
        )
        self.set_llm_completion(model, messages, data)

    def compute_workspace_hash(self, workspace_path: Path) -> str:
        """Compute combined SHA-256 hash of all indexed source code files in workspace."""
        hasher = hashlib.sha256()
        for ext in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.html", "*.css"]:
            for filepath in sorted(workspace_path.glob(f"**/{ext}")):
                if any(
                    ignored in str(filepath)
                    for ignored in [".git", "node_modules", ".venv", "dist", ".localforge"]
                ):
                    continue
                try:
                    stat = filepath.stat()
                    hasher.update(f"{filepath.name}:{stat.st_mtime}:{stat.st_size}".encode())
                except OSError:
                    continue
        return hasher.hexdigest()

    def get_ast_graph(self, workspace_path: Path) -> dict[str, Any] | None:
        """Retrieve cached AST graph if workspace files have not changed."""
        if not self.enabled:
            return None

        ws_hash = self.compute_workspace_hash(workspace_path)
        ast_cache_file = self.cache_dir / f"ast_{ws_hash[:16]}.json"

        if not ast_cache_file.exists():
            return None

        try:
            content = json.loads(ast_cache_file.read_text(encoding="utf-8"))
            logger.info("AST Graphify Cache HIT — returning pre-computed AST graph (0 LLM tokens)")
            return content.get("graph_data")
        except Exception:
            return None

    def set_ast_graph(self, workspace_path: Path, graph_data: dict[str, Any]) -> None:
        """Store AST graph for workspace hash."""
        if not self.enabled:
            return

        ws_hash = self.compute_workspace_hash(workspace_path)
        ast_cache_file = self.cache_dir / f"ast_{ws_hash[:16]}.json"

        payload = {
            "timestamp": time.time(),
            "workspace_hash": ws_hash,
            "graph_data": graph_data,
        }
        try:
            ast_cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to write AST graph cache: {exc}")
