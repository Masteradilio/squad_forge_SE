"""Context7 MCP Connector — Fetch live version-specific library documentation."""

import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class Context7MCPConnector:
    """Connector for Upstash Context7 MCP Server providing up-to-date library docs."""

    def __init__(self, mcp_endpoint: str = "https://context7.upstash.io/api"):
        self.endpoint = mcp_endpoint.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def search_library_docs(self, library_name: str, query: str) -> List[Dict[str, Any]]:
        """Search and retrieve official version-specific documentation snippets for a library."""
        url = f"{self.endpoint}/docs"
        params = {"library": library_name, "query": query}
        try:
            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                return response.json().get("snippets", [])
            logger.info(f"Context7 returned status {response.status_code} for {library_name}")
            return []
        except Exception as exc:
            logger.warning(f"Context7 MCP search failed for {library_name}: {exc}")
            return [
                {
                    "title": f"{library_name} Context7 Fallback",
                    "content": f"Use latest official API syntax for {library_name}.",
                }
            ]

    async def prefetch_prd_technologies(self, tech_stack: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Pre-fetch documentation for all technology frameworks listed in the PRD."""
        results = {}
        for tech in tech_stack:
            snippets = await self.search_library_docs(tech, f"{tech} latest best practices and API signatures")
            results[tech] = snippets
        return results

    async def close(self):
        await self.client.aclose()
