"""Probe the configured Context7 MCP endpoint without printing credentials."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from localforge.connectors.context7_mcp import Context7MCPConnector  # noqa: E402


async def _run() -> int:
    os.chdir(PROJECT_ROOT)
    connector = Context7MCPConnector.from_config()
    try:
        probe = await connector.probe()
        payload: dict[str, object] = {
            "ok": probe.ok,
            "endpoint": probe.endpoint,
            "server_info": probe.server_info,
            "tools": list(probe.tools),
            "error": probe.error,
        }
        if probe.ok:
            docs = await connector.search_library_docs(
                "fastapi",
                "routing and request validation API signatures",
            )
            payload["docs_count"] = len(docs)
            payload["library_ids"] = [item.get("library_id") for item in docs]
            payload["content_lengths"] = [len(str(item.get("content", ""))) for item in docs]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if probe.ok else 1
    finally:
        await connector.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
