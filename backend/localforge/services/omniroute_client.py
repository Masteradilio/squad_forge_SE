"""OmniRoute AI Gateway Client — Async connection & fallback interface for 290+ Free Tier LLMs."""

import json
import logging
import os
from typing import Any

import httpx

from localforge.llm.openai_compatible import decode_chat_completion_response
from localforge.services.semantic_cache import SemanticCacheManager

logger = logging.getLogger(__name__)


class OmniRouteClient:
    """Client for communicating with the OmniRoute AI Gateway proxy."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (
            base_url
            or os.getenv("OMNIROUTE_URL")
            or "http://localhost:20128/v1"
        ).rstrip("/")
        from localforge.core.config import _validate_omniroute_endpoint

        _validate_omniroute_endpoint(self.base_url, "omniroute")
        self.client = httpx.AsyncClient(timeout=60.0)
        self.cache = SemanticCacheManager()
        # The catalog exposed by OmniRoute's OpenAI endpoint does not publish
        # JSON-output metadata for its built-in ``auto/*`` routes. The Compose
        # deployment opts into this only after the gateway contract has been
        # verified by the local pre-flight configuration.
        self.gateway_json_contract_verified = (
            os.getenv("LOCALFORGE_OMNIROUTE_JSON_VERIFIED", "false").lower() == "true"
        )
        self.combo_mutation_enabled = (
            os.getenv("LOCALFORGE_OMNIROUTE_COMBO_MUTATION_ENABLED", "false").lower()
            == "true"
        )
        self._json_contract_verified: dict[str, bool] = {}
        self._agentic_contract_verified: dict[str, bool] = {}

    async def get_models(self) -> list[dict[str, Any]]:
        """Fetch catalog of available LLMs from OmniRoute."""
        url = f"{self.base_url}/models"
        try:
            response = await self.client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as exc:
            logger.warning(f"Failed to fetch models from OmniRoute at {url}: {exc}")
            return []

    async def register_combo(self, combo_name: str, models: list[str]) -> bool:
        """Register or update a dynamic model combo route in OmniRoute."""
        # /v1/combos is a read-only OpenAI catalog endpoint in OmniRoute. The
        # management API owns combo mutations under /api/combos.
        management_base = self.base_url.removesuffix("/v1")
        url = f"{management_base}/api/combos"
        payload = {"name": combo_name, "models": models, "strategy": "priority"}
        headers: dict[str, str] = {}
        api_key = os.getenv("OMNIROUTE_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = await self.client.post(url, json=payload, headers=headers or None)
            if response.status_code not in (200, 201):
                logger.warning(
                    "OmniRoute combo mutation failed for %s with HTTP %s",
                    combo_name,
                    response.status_code,
                )
            return response.status_code in (200, 201)
        except Exception as exc:
            logger.warning(f"Failed to register combo '{combo_name}': {exc}")
            return False

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Send a chat completion request to OmniRoute with standard OpenAI protocol & semantic caching."""
        if use_cache:
            cached_result = await self.cache.aget_llm_completion(model, messages)
            if cached_result:
                return cached_result

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if response_format is not None:
            payload["response_format"] = response_format

        response = await self.client.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        content = decode_chat_completion_response(response)
        data = {"choices": [{"message": {"content": content}}]}
        if use_cache:
            await self.cache.aset_llm_completion(model, messages, data)
        return data

    async def verify_json_contract(self, model: str = "auto/best-free") -> bool:
        """Prove that a gateway route returns parseable JSON before routing work."""
        if model in self._json_contract_verified:
            return self._json_contract_verified[model]

        try:
            response = await self.chat_completion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return only a JSON object with the boolean field ok.",
                    },
                    {"role": "user", "content": 'Return exactly {"ok":true}.'},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                use_cache=False,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content.strip()) if isinstance(content, str) else None
            self._json_contract_verified[model] = (
                isinstance(parsed, dict) and parsed.get("ok") is True
            )
        except Exception as exc:
            logger.warning("OmniRoute JSON contract verification failed for %s: %s", model, exc)
            self._json_contract_verified[model] = False
        return self._json_contract_verified[model]

    async def verify_agentic_contract(self, model: str) -> bool:
        """Live-probe both structured output and required function calling."""
        if model in self._agentic_contract_verified:
            return self._agentic_contract_verified[model]
        if not await self.verify_json_contract(model):
            self._agentic_contract_verified[model] = False
            return False

        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": "Call report_ok with ok=true. Do not answer in text.",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "report_ok",
                        "description": "Report route readiness.",
                        "parameters": {
                            "type": "object",
                            "properties": {"ok": {"type": "boolean"}},
                            "required": ["ok"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "report_ok"}},
            "max_tokens": 128,
            "temperature": 0.0,
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=20.0,
            )
            response.raise_for_status()
            data = response.json()
            tool_calls = (
                data.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
            )
            arguments = next(
                (
                    call.get("function", {}).get("arguments")
                    for call in tool_calls
                    if call.get("function", {}).get("name") == "report_ok"
                ),
                None,
            )
            parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
            verified = isinstance(parsed, dict) and parsed.get("ok") is True
        except Exception as exc:
            logger.warning("OmniRoute agentic contract verification failed for %s: %s", model, exc)
            verified = False
        self._agentic_contract_verified[model] = verified
        return verified

    async def close(self):
        await self.client.aclose()

    @staticmethod
    def _headers() -> dict[str, str]:
        api_key = os.getenv("OMNIROUTE_API_KEY")
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}
