"""Context7 MCP Connector — Fetch live version-specific library documentation."""

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class Context7MCPConnector:
    """Connector for Upstash Context7 MCP Server providing up-to-date library docs."""

    def __init__(self, mcp_endpoint: str = "https://mcp.context7.ai/v1"):
        self.endpoint = mcp_endpoint.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self._request_id = 0
        self._initialized = False

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params is not None:
            payload["params"] = params
        response = await self.client.post(
            self.endpoint,
            json=payload,
            headers={"Accept": "application/json, text/event-stream"},
        )
        response.raise_for_status()
        if "text/event-stream" in response.headers.get("content-type", ""):
            data_lines = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
            if not data_lines:
                raise RuntimeError("Context7 MCP returned an empty event stream")
            result = json.loads(data_lines[-1])
        else:
            result = response.json()
        if not isinstance(result, dict):
            raise RuntimeError("Context7 MCP returned a non-object response")
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        return result

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "localforge-os", "version": "6.2.0"},
            },
        )
        await self.client.post(
            self.endpoint,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        self._initialized = True

    async def search_library_docs(self, library_name: str, query: str) -> list[dict[str, Any]]:
        """Search and retrieve official version-specific documentation snippets for a library."""
        try:
            await self._ensure_initialized()
            resolved = await self._rpc(
                "tools/call",
                {
                    "name": "resolve-library-id",
                    "arguments": {"libraryName": library_name, "query": query},
                },
            )
            resolved_text = self._text_content(resolved)
            resolved_data: Any = None
            try:
                resolved_data = json.loads(resolved_text)
            except json.JSONDecodeError:
                resolved_data = resolved_text
            library_id = self._extract_library_id(resolved_data)
            if not library_id:
                return []
            docs = await self._rpc(
                "tools/call",
                {
                    "name": "query-docs",
                    "arguments": {"libraryId": library_id, "query": query},
                },
            )
            return [{"library_id": library_id, "content": self._text_content(docs)}]
        except Exception as exc:
            logger.warning(f"Context7 MCP search failed for {library_name}: {exc}")
            return []

    @staticmethod
    def _text_content(result: dict[str, Any]) -> str:
        payload = result.get("result", result)
        content = payload.get("content", []) if isinstance(payload, dict) else []
        return "\n".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text"
        ).strip()

    @staticmethod
    def _extract_library_id(value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("libraryId", "library_id", "id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.startswith("/"):
                    return candidate
            for item in value.values():
                found = Context7MCPConnector._extract_library_id(item)
                if found:
                    return found
        if isinstance(value, list):
            for item in value:
                found = Context7MCPConnector._extract_library_id(item)
                if found:
                    return found
        if isinstance(value, str):
            for token in value.split():
                if token.startswith("/"):
                    return token.rstrip(".,)")
        return None

    async def prefetch_prd_technologies(self, tech_stack: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Pre-fetch documentation for all technology frameworks listed in the PRD."""
        results = {}
        for tech in tech_stack:
            snippets = await self.search_library_docs(tech, f"{tech} latest best practices and API signatures")
            results[tech] = snippets
        return results

    async def close(self):
        await self.client.aclose()
