from __future__ import annotations

import json

from scripts.run_benchmark_reference_forgeos import _select_reference_routes
from scripts.run_benchmark_v3_only import _decode_completion_text


def test_route_probe_decodes_openai_json_completion() -> None:
    body = json.dumps(
        {
            "choices": [
                {"message": {"content": '{"actions":[{"kind":"write_file"}]}'}}
            ]
        }
    )

    assert json.loads(_decode_completion_text(body))["actions"]


def test_route_probe_decodes_sse_completion_and_ignores_done() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"{\\"ok\\": "}}]}',
            'data: {"choices":[{"delta":{"content":"true}"}}]}',
            "data: [DONE]",
        ]
    )

    assert json.loads(_decode_completion_text(body)) == {"ok": True}


def test_reference_benchmark_preserves_dynamic_route_ladder(monkeypatch) -> None:
    monkeypatch.setenv(
        "LOCALFORGE_BENCHMARK_ROUTE_LADDER",
        "nvidia/nvidia/nemotron-3-nano-30b-a3b,missing-route",
    )

    routes = _select_reference_routes(
        [
            "nvidia/nvidia/nemotron-3-nano-30b-a3b",
            "auto/best-free",
        ]
    )

    assert routes[0] == "nvidia/nvidia/nemotron-3-nano-30b-a3b"
    assert "missing-route" not in routes
