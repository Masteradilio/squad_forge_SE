"""Safe Context7 MCP connector for version-specific library documentation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from localforge.core.config import Context7Config, load_config

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT7_ENDPOINT = "https://mcp.context7.com/mcp"


class Context7MCPError(RuntimeError):
    """Base error for safe Context7 transport and protocol failures."""


class Context7ConfigurationError(Context7MCPError):
    """Raised when Context7 cannot be used with the current configuration."""


@dataclass(frozen=True)
class Context7ProbeResult:
    """Non-sensitive result of a Context7 connectivity probe."""

    ok: bool
    endpoint: str
    server_info: dict[str, Any] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    error: str | None = None


class Context7MCPConnector:
    """Connector for Context7's hosted Streamable HTTP MCP server.

    Construction is explicit so unit tests and isolated runtimes do not
    accidentally inherit credentials from another working directory. Use
    :meth:`from_config` at ForgeOS integration boundaries.
    """

    def __init__(
        self,
        mcp_endpoint: str = DEFAULT_CONTEXT7_ENDPOINT,
        api_key: str | None = None,
        *,
        enabled: bool = True,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.endpoint = mcp_endpoint.rstrip("/")
        self.api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        self.enabled = enabled
        self.timeout = timeout
        self.client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._request_id = 0
        self._initialized = False
        self._session_id: str | None = None
        self._server_info: dict[str, Any] = {}
        self._tools: tuple[str, ...] = ()

    @classmethod
    def from_config(
        cls,
        config: Context7Config | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> "Context7MCPConnector":
        """Build a connector from the workspace-local ForgeOS configuration."""

        resolved = config or load_config().context7
        return cls(
            mcp_endpoint=resolved.endpoint,
            api_key=resolved.api_key,
            enabled=resolved.enabled,
            timeout=resolved.timeout,
            client=client,
        )

    def _require_configured(self) -> None:
        if not self.enabled:
            raise Context7ConfigurationError("Context7 MCP is disabled")
        if not self.api_key:
            raise Context7ConfigurationError("Context7 MCP API key is not configured")

    def _headers(self) -> dict[str, str]:
        self._require_configured()
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        self._request_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        response = await self.client.post(self.endpoint, json=payload, headers=self._headers())
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        response.raise_for_status()
        result = self._decode_response(response)
        if result.get("error"):
            error = result["error"]
            message = error.get("message", "MCP request failed") if isinstance(error, dict) else str(error)
            raise Context7MCPError(self._redact(str(message)))
        return result

    async def _notification(self, method: str) -> None:
        self._require_configured()
        response = await self.client.post(
            self.endpoint,
            json={"jsonrpc": "2.0", "method": method},
            headers=self._headers(),
        )
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        response.raise_for_status()

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" in content_type:
            data_lines = [
                line[5:].strip()
                for line in response.text.splitlines()
                if line.startswith("data:") and line[5:].strip()
            ]
            if not data_lines:
                raise Context7MCPError("Context7 MCP returned an empty event stream")
            try:
                result = json.loads(data_lines[-1])
            except json.JSONDecodeError as exc:
                raise Context7MCPError("Context7 MCP returned invalid event data") from exc
        else:
            try:
                result = response.json()
            except ValueError as exc:
                raise Context7MCPError("Context7 MCP returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise Context7MCPError("Context7 MCP returned a non-object response")
        return result

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        response = await self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "localforge-os", "version": "6.2.0"},
            },
        )
        result = response.get("result")
        if isinstance(result, dict):
            server_info = result.get("serverInfo")
            if isinstance(server_info, dict):
                self._server_info = dict(server_info)
        await self._notification("notifications/initialized")
        self._initialized = True

    async def list_tools(self) -> list[str]:
        """Return the names exposed by the current Context7 MCP session."""

        await self._ensure_initialized()
        response = await self._rpc("tools/list", {})
        result = response.get("result")
        tools = result.get("tools", []) if isinstance(result, dict) else []
        names = tuple(
            str(tool["name"])
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        )
        self._tools = names
        return list(names)

    async def probe(self) -> Context7ProbeResult:
        """Check authentication and MCP tool discovery without fetching docs."""

        try:
            self._require_configured()
            tools = await self.list_tools()
            return Context7ProbeResult(
                ok=True,
                endpoint=self.endpoint,
                server_info=dict(self._server_info),
                tools=tuple(tools),
            )
        except Exception as exc:  # Probes report status; operational calls raise.
            error = self._safe_error(exc)
            logger.warning("Context7 MCP probe failed: %s", error)
            return Context7ProbeResult(ok=False, endpoint=self.endpoint, error=error)

    async def search_library_docs(self, library_name: str, query: str) -> list[dict[str, Any]]:
        """Resolve a library and retrieve current version-specific documentation."""

        await self._ensure_initialized()
        tools = set(await self.list_tools())
        if "resolve-library-id" not in tools:
            raise Context7MCPError("Context7 MCP does not expose resolve-library-id")
        docs_tool = "get-library-docs" if "get-library-docs" in tools else "query-docs"
        if docs_tool not in tools:
            raise Context7MCPError("Context7 MCP does not expose a documentation tool")

        resolved = await self._rpc(
            "tools/call",
            {
                "name": "resolve-library-id",
                "arguments": {"libraryName": library_name, "query": query},
            },
        )
        resolved_text = self._text_content(resolved)
        try:
            resolved_data: Any = json.loads(resolved_text)
        except json.JSONDecodeError:
            resolved_data = resolved_text
        library_id = self._extract_library_id(resolved_data)
        if not library_id:
            return []

        docs = await self._rpc(
            "tools/call",
            {
                "name": docs_tool,
                "arguments": {"libraryId": library_id, "query": query},
            },
        )
        return [{"library_id": library_id, "content": self._text_content(docs)}]

    @staticmethod
    def _text_content(result: dict[str, Any]) -> str:
        payload = result.get("result", result)
        content = payload.get("content", []) if isinstance(payload, dict) else []
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
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
        """Pre-fetch documentation for all technology frameworks listed in a PRD."""

        results: dict[str, list[dict[str, Any]]] = {}
        for tech in tech_stack:
            results[tech] = await self.search_library_docs(
                tech,
                f"{tech} latest best practices and API signatures",
            )
        return results

    def _redact(self, message: str) -> str:
        return message.replace(self.api_key, "[redacted]") if self.api_key else message

    def _safe_error(self, exc: Exception) -> str:
        if isinstance(exc, Context7ConfigurationError):
            return str(exc)
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Context7 MCP returned HTTP {exc.response.status_code}"
        if isinstance(exc, httpx.RequestError):
            return f"Context7 MCP transport error: {type(exc).__name__}"
        if isinstance(exc, Context7MCPError):
            return self._redact(str(exc))
        return self._redact(f"Context7 MCP error: {type(exc).__name__}")

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
