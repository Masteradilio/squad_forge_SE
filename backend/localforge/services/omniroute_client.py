"""OmniRoute AI Gateway Client — Async connection & fallback interface for 290+ Free Tier LLMs."""

import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class OmniRouteClient:
    """Client for communicating with the OmniRoute AI Gateway proxy."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (
            base_url
            or os.getenv("OMNIROUTE_URL")
            or "http://localhost:20128/v1"
        ).rstrip("/")
        self.client = httpx.AsyncClient(timeout=60.0)

    async def get_models(self) -> List[Dict[str, Any]]:
        """Fetch catalog of available LLMs from OmniRoute."""
        url = f"{self.base_url}/models"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            logger.warning(f"Failed to fetch models from OmniRoute at {url}: {exc}")
            return []

    async def register_combo(self, combo_name: str, models: List[str]) -> bool:
        """Register or update a dynamic model combo route in OmniRoute."""
        url = f"{self.base_url}/combos"
        payload = {"name": combo_name, "models": models, "strategy": "fallback"}
        try:
            response = await self.client.post(url, json=payload)
            return response.status_code in (200, 201)
        except Exception as exc:
            logger.warning(f"Failed to register combo '{combo_name}': {exc}")
            return False

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Send a chat completion request to OmniRoute with standard OpenAI protocol."""
        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
