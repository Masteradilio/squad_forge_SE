import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.chief_engineer.service import (
    ChiefEngineerRepairPlan,
    ChiefEngineerService,
    _deterministic_visual_css_section,
    _extract_visual_document,
    _is_transient_gateway_error,
    _normalize_visual_section_content,
    _visual_control_partition,
    _validate_visual_repair_plan,
    _validate_visual_section,
    _visual_section_models,
)
from localforge.core.config import LocalForgeConfig, load_config
from localforge.llm import LLMError
from localforge.llm.base import LLMHTTPError, LLMTimeoutError
from localforge.llm.fallback import FallbackLLMProvider
from localforge.llm.factory import build_chief_engineer_provider
from localforge.llm.openrouter import OpenRouterProvider
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason, RunMode, RunStatus
from localforge.pipeline.engine import RolePipelineEngine, _chief_model_sequence
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_openrouter_dotenv_selects_paid_chief_route_when_no_route_is_explicit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "OPENROUTER_MODEL=minimax/minimax-m3\nOPENROUTER_API_KEY=test-secret-key\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "openrouter"
    assert config.chief_engineer.model == "minimax/minimax-m3"
    assert config.chief_engineer.api_key == "test-secret-key"
    assert config.chief_engineer.base_url == "https://openrouter.ai/api/v1"
    assert config.budgets.max_paid_calls == 30


def test_new_openrouter_paid_and_free_lanes_are_normalized_and_prioritized(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    for name in (
        "OPENROUTER_PAID_MODEL",
        "OPENROUTER_FREE_MODEL",
        "OPENROUTER_MODEL",
        "OPENROUTER_API_KEY",
        "LOCALFORGE_CHIEF_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "LOCALFORGE_CHIEF_BASE_URL=http://127.0.0.1:20128/v1\n"
        "LOCALFORGE_CHIEF_MODEL=legacy/free-model\n"
        "OPENROUTER_PAID_MODEL= ~deepseek/deepseek-v4-flash-latest \n"
        "OPENROUTER_FREE_MODEL=nvidia/nemotron-3.5-lightning:free\n"
        "OPENROUTER_API_KEY=test-secret-key\n"
        "NVIDIA_LLM_MODEL=minimaxai/minimax-m3\n"
        "NVIDIA_API_KEY=test-nvidia-key\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "openrouter"
    assert config.chief_engineer.model == "~deepseek/deepseek-v4-flash-latest"
    assert [route.provider for route in config.chief_engineer.fallback_routes] == [
        "openrouter",
        "nvidia",
    ]
    assert [route.model for route in config.chief_engineer.fallback_routes] == [
        "nvidia/nemotron-3.5-lightning:free",
        "minimaxai/minimax-m3",
    ]


def test_legacy_openrouter_model_remains_paid_alias(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "OPENROUTER_MODEL=deepseek/deepseek-v4-flash-0731\n"
        "OPENROUTER_API_KEY=test-secret-key\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "openrouter"
    assert config.chief_engineer.model == "deepseek/deepseek-v4-flash-0731"


def test_explicit_omniroute_keeps_paid_fallback_before_free_routes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "LOCALFORGE_CHIEF_PROVIDER=omniroute\n"
        "LOCALFORGE_CHIEF_BASE_URL=http://127.0.0.1:20128/v1\n"
        "LOCALFORGE_CHIEF_MODEL=auto/best-free\n"
        "OPENROUTER_PAID_MODEL=~deepseek/deepseek-v4-flash-latest\n"
        "OPENROUTER_FREE_MODEL=nvidia/nemotron-3.5-lightning:free\n"
        "OPENROUTER_API_KEY=test-secret-key\n"
        "NVIDIA_LLM_MODEL=minimaxai/minimax-m3\n"
        "NVIDIA_API_KEY=test-nvidia-key\n",
        encoding="utf-8",
    )

    config = load_config()
    provider = build_chief_engineer_provider(config)

    assert config.chief_engineer.provider == "omniroute"
    assert config.chief_engineer.fallback_provider == "openrouter"
    assert config.chief_engineer.fallback_model == "~deepseek/deepseek-v4-flash-latest"
    assert isinstance(provider, FallbackLLMProvider)
    assert provider.fallback_provider_name == "nvidia"
    assert isinstance(provider.primary, FallbackLLMProvider)
    assert provider.primary.fallback_provider_name == "openrouter"


def test_openrouter_route_wins_over_unrelated_legacy_nvidia_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "NVIDIA_LLM_MODEL=minimax/minimax-m3\n"
        "NVIDIA_API_KEY=nvapi-secret\n"
        "OPENROUTER_MODEL=minimax/minimax-m3\n"
        "OPENROUTER_API_KEY=sk-or-fallback\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "openrouter"
    assert config.chief_engineer.model == "minimax/minimax-m3"
    assert config.chief_engineer.api_key == "sk-or-fallback"
    assert config.chief_engineer.fallback_provider is None


def test_visual_repair_rejects_css_only_patch() -> None:
    contract = {"visual_required": True, "visual_actual_output": "app/index.html"}
    css_patch = ChiefEngineerRepairPlan.model_validate(
        {
            "actions": [
                {"kind": "append_content", "path": "app/index.html", "content": ".key {}"}
            ]
        }
    )
    with pytest.raises(ValueError, match="complete write_file"):
        _validate_visual_repair_plan(css_patch, contract)

    complete_html = "<html><body><style></style><script></script>" + ("x" * 6000)
    valid_plan = ChiefEngineerRepairPlan.model_validate(
        {
            "actions": [
                {"kind": "write_file", "path": "app/index.html", "content": complete_html}
            ]
        }
    )
    _validate_visual_repair_plan(valid_plan, contract)


def test_extract_visual_document_discards_gateway_transport_noise() -> None:
    raw = "Here is the file:\n```html\n<!doctype html><html><body><script>ok()</script></body></html>\n```\nDone."
    assert _extract_visual_document(raw).startswith("<!doctype html>")
    assert _extract_visual_document(raw).endswith("</html>")


def test_visual_sections_reject_wrappers_and_omissions() -> None:
    _validate_visual_section(
        "css_layout", ".key{display:block}" + ("/*x*/" * 140), 600, 1200
    )

    with pytest.raises(ValueError, match="wrapper tag"):
        _validate_visual_section(
            "script_core", "<script>run()</script>" + ("/*x*/" * 200), 900, 1600
        )
    with pytest.raises(ValueError, match="omission marker"):
        _validate_visual_section(
            "body_shell", "placeholder" + ("<!--x-->" * 100), 600, 1200
        )


def test_visual_section_normalizer_removes_safe_model_wrappers() -> None:
    assert _normalize_visual_section_content("script_core", "<script>run()</script>") == "run()"
    assert _normalize_visual_section_content("css_layout", "<style>body{}</style>") == "body{}"


@pytest.mark.parametrize(
    "section_name,minimum_length",
    [
        ("css_reset", 300),
        ("css_frame_container", 400),
        ("css_frame_surface", 300),
        ("css_frame_inner", 400),
        ("css_display", 300),
        ("css_controls_grid", 400),
        ("css_controls_labels", 400),
    ],
)
def test_deterministic_visual_css_fallback_is_contract_sized(
    section_name: str, minimum_length: int
) -> None:
    content = _deterministic_visual_css_section(section_name)
    _validate_visual_section(section_name, content, minimum_length, 6000)


def test_visual_section_normalizer_extracts_full_document_body_fragments() -> None:
    document = (
        "<html><body><main><header>LCD</header><section class='key-grid'>"
        + "".join(f"<button data-key='k{i}'>K{i}</button>" for i in range(20))
        + "</section></main></body></html>"
    )
    assert _normalize_visual_section_content("body_shell", document) == "<header>LCD</header>"
    controls = _normalize_visual_section_content("body_controls_2", document)
    assert "data-key='k5'" in controls
    assert "data-key='k0'" not in controls


def test_visual_control_sections_follow_declared_matrix_without_duplicates() -> None:
    matrix = [
        {"locator": f"[data-row='{index // 8}'][data-column='{index % 8}']"}
        for index in range(40)
    ]
    buttons = "".join(f"<button data-key='k{index}'>K{index}</button>" for index in range(40))

    sections = []
    for section_index in range(1, 7):
        partition = _visual_control_partition(
            f"body_controls_{section_index}", matrix
        )
        sections.append(
            _normalize_visual_section_content(
                f"body_controls_{section_index}",
                buttons,
                control_partition=partition,
            )
        )

    rendered_keys = re.findall(r"data-key='(k\d+)'", "\n".join(sections))
    assert rendered_keys == [f"k{index}" for index in range(40)]
    assert len(rendered_keys) == len(set(rendered_keys))


def test_body_control_section_accepts_legitimate_finite_size() -> None:
    content = "<button data-key='control'>control</button>" + ("<!--x-->" * 419)
    assert len(content) == 3395
    _validate_visual_section("body_controls_3", content + "!", 120, 4800)


def test_omniroute_visual_sections_use_equivalent_coding_alias(monkeypatch) -> None:
    monkeypatch.setenv("LOCALFORGE_FALLBACK_MODELS", "auto/coding:free,auto/best-free")
    monkeypatch.setenv("LOCALFORGE_CHIEF_FALLBACK_MODELS", "auto/coding:free,auto/best-free")
    monkeypatch.setenv(
        "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS", "auto/coding:free,auto/best-free"
    )
    assert _visual_section_models("omniroute", "auto/pro-vision") == [
        "auto/best-free",
        "auto/coding:free",
    ]
    assert _visual_section_models("omniroute", "auto/best-vision")[0] == "auto/best-free"
    assert _visual_section_models("nvidia", "vendor/vision-model") == [
        "vendor/vision-model"
    ]


def test_omniroute_visual_sections_follow_configured_free_ladder(monkeypatch) -> None:
    monkeypatch.setenv("LOCALFORGE_CHIEF_FALLBACK_MODELS", "oc/catalog-a-free")
    monkeypatch.setenv(
        "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS", "oc/catalog-visual-free"
    )
    monkeypatch.setenv("LOCALFORGE_FALLBACK_MODELS", "oc/catalog-b-free")

    assert _visual_section_models("omniroute", "auto/pro-vision") == [
        "auto/best-free",
        "oc/catalog-a-free",
        "oc/catalog-visual-free",
        "oc/catalog-b-free",
    ]


def test_omniroute_visual_sections_prefer_verified_routes_to_stale_aliases(monkeypatch) -> None:
    monkeypatch.setenv(
        "LOCALFORGE_CLOUD_VERIFIED_ROUTES",
        "nvidia/live-primary,nvidia/live-secondary,nvidia/live-primary",
    )
    monkeypatch.setenv("LOCALFORGE_FALLBACK_MODELS", "auto/best-free")
    monkeypatch.setenv("LOCALFORGE_CHIEF_FALLBACK_MODELS", "auto/coding:free")
    monkeypatch.setenv(
        "LOCALFORGE_CHIEF_VISUAL_FALLBACK_MODELS", "auto/best-free"
    )

    models = _visual_section_models("omniroute", "nvidia/live-primary")

    assert models[:2] == ["nvidia/live-primary", "nvidia/live-secondary"]
    assert models.count("nvidia/live-primary") == 1
    assert models.index("nvidia/live-secondary") < models.index("auto/best-free")


def test_transient_gateway_error_classifier() -> None:
    assert _is_transient_gateway_error(LLMHTTPError("limited", status_code=429))
    assert _is_transient_gateway_error(LLMTimeoutError("timeout"))
    assert not _is_transient_gateway_error(LLMHTTPError("unauthorized", status_code=401))


@pytest.mark.anyio
async def test_omniroute_transient_alias_failure_uses_next_alias_without_chief(
    monkeypatch,
):
    config = LocalForgeConfig.model_validate(
        {
            "models": {"provider": "omniroute"},
            "chief_engineer": {"provider": "omniroute", "model": "auto/best-reasoning"},
        }
    )
    monkeypatch.setattr("localforge.pipeline.engine.load_config", lambda: config)

    class LocalGateway:
        provider_name = "omniroute"

        def __init__(self):
            self.models: list[str] = []

        async def chat_completion(self, *args, **kwargs):
            model = str(kwargs["model"])
            self.models.append(model)
            if model == "auto/best-fast":
                raise LLMHTTPError("free pool exhausted", status_code=429)
            return '{"actions": []}'

    local = LocalGateway()
    monkeypatch.setattr(
        "localforge.pipeline.engine.OpenAICompatibleProvider",
        lambda **kwargs: local,
    )
    monkeypatch.setattr(
        "localforge.pipeline.engine.build_chief_engineer_provider",
        lambda config: (_ for _ in ()).throw(AssertionError("Chief is not needed")),
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)
    engine.uow = MagicMock(model_calls=None)
    engine._local_model_candidates = AsyncMock(
        return_value=["auto/best-fast", "auto/best-coding"]
    )

    response, model = await engine._chat_completion_with_local_fallback(
        prompt="return action JSON",
        preferred_model="auto/best-fast",
        timeout=180.0,
    )

    assert response == '{"actions": []}'
    assert model == "auto/best-coding"
    assert local.models == ["auto/best-fast", "auto/best-coding"]


@pytest.mark.anyio
async def test_local_lane_uses_direct_free_provider_before_paid_chief(monkeypatch):
    config = LocalForgeConfig.model_validate(
        {
            "models": {
                "provider": "omniroute",
                "fallback_routes": [
                    {
                        "provider": "nvidia",
                        "base_url": "https://integrate.api.nvidia.com/v1",
                        "model": "minimaxai/minimax-m3",
                        "api_key": "test-nvidia-key",
                    }
                ],
            },
            "chief_engineer": {"provider": "openrouter", "model": "paid-model"},
        }
    )
    monkeypatch.setattr("localforge.pipeline.engine.load_config", lambda: config)

    class LocalGateway:
        provider_name = "omniroute"

        async def chat_completion(self, *args, **kwargs):
            raise LLMHTTPError("gateway unavailable", status_code=502)

    class DirectFreeGateway:
        provider_name = "nvidia"
        default_model = "minimaxai/minimax-m3"

        async def chat_completion(self, *args, **kwargs):
            return '{"actions": []}'

    monkeypatch.setattr(
        "localforge.pipeline.engine.OpenAICompatibleProvider",
        lambda **kwargs: LocalGateway(),
    )
    monkeypatch.setattr(
        "localforge.pipeline.engine.build_free_provider_ladder",
        lambda config: [DirectFreeGateway()],
    )
    monkeypatch.setattr(
        "localforge.pipeline.engine.build_chief_engineer_provider",
        lambda config: (_ for _ in ()).throw(AssertionError("Paid Chief is not needed")),
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)
    engine.uow = MagicMock(model_calls=None)
    engine._local_model_candidates = AsyncMock(return_value=["auto/best-fast"])

    response, model = await engine._chat_completion_with_local_fallback(
        prompt="return action JSON",
        preferred_model="auto/best-fast",
        timeout=180.0,
    )

    assert response == '{"actions": []}'
    assert model == "minimaxai/minimax-m3"


@pytest.mark.anyio
async def test_omniroute_local_lane_tries_chief_alias_after_transient_primary_failure(
    monkeypatch,
):
    config = LocalForgeConfig.model_validate(
        {
            "models": {"provider": "omniroute", "default_model": "auto/best-fast"},
            "chief_engineer": {
                "provider": "omniroute",
                "model": "auto/best-reasoning",
                "fallback_models": ["auto/best-coding", "auto/best-chat"],
            },
        }
    )
    monkeypatch.setattr("localforge.pipeline.engine.load_config", lambda: config)

    class LocalGateway:
        provider_name = "omniroute"

        async def chat_completion(self, *args, **kwargs):
            raise LLMHTTPError("free pool exhausted", status_code=429)

    class ChiefGateway:
        provider_name = "omniroute"

        def __init__(self):
            self.models: list[str] = []

        async def chat_completion(self, *args, **kwargs):
            model = str(kwargs["model"])
            self.models.append(model)
            if model == "auto/best-reasoning":
                raise LLMTimeoutError("reasoning route timed out")
            return '{"actions": []}'

    chief = ChiefGateway()
    monkeypatch.setattr(
        "localforge.pipeline.engine.OpenAICompatibleProvider",
        lambda **kwargs: LocalGateway(),
    )
    monkeypatch.setattr(
        "localforge.pipeline.engine.build_chief_engineer_provider",
        lambda config: chief,
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)
    engine.uow = MagicMock(model_calls=None)
    engine._local_model_candidates = AsyncMock(return_value=["auto/best-fast"])

    response, model = await engine._chat_completion_with_local_fallback(
        prompt="return action JSON",
        preferred_model="auto/best-fast",
        timeout=180.0,
    )

    assert response == '{"actions": []}'
    assert model == "auto/best-coding"
    assert chief.models == ["auto/best-reasoning", "auto/best-coding"]


@pytest.mark.anyio
@pytest.mark.parametrize("script_state_length", [4715, 9742])
async def test_visual_repair_is_assembled_from_bounded_calls(
    script_state_length: int,
) -> None:
    script_state_prefix = "const stack=[]; function renderDisplay(){return stack[0] ?? 0;}"
    if script_state_length == 4715:
        script_state = (
            script_state_prefix
            + ("/* state behavior */" * 232)
            + "/*12345678*/"
        )
    else:
        script_state = script_state_prefix + "/*" + (
            "x" * (script_state_length - len(script_state_prefix) - 4)
        ) + "*/"
    assert len(script_state) == script_state_length

    chunks = [
        "*{box-sizing:border-box}body{margin:0}" + ("/*r*/" * 80),
        ".calculator-shell{display:grid;min-height:80vh}" + ("/*c*/" * 71),
        ".calculator-shell{max-width:900px;margin:auto}" + ("/*o*/" * 70),
        ".calculator-shell{background:#ddd;border-radius:8px}" + ("/*s*/" * 70),
        ".display{font:inherit}" + ("/*f*/" * 70),
        ".key-grid{display:grid}.key{display:block}" + ("/*g*/" * 100),
        ".key{font-weight:700}.key small{display:block}" + ("/*l*/" * 100),
        ".display{box-shadow:inset 0 0 4px #000}" + ("/*z*/" * 70),
        '<header><output id="display">0</output></header>' + ("<!--s-->" * 90),
        '<button class="key" data-key="1">1</button>' * 8,
        '<button class="key" data-key="2">2</button>' * 8,
        '<button class="key" data-key="3">3</button>' * 8,
        '<button class="key" data-key="4">4</button>' * 8,
        '<button class="key" data-key="5">5</button>' * 8,
        '<button class="key" data-key="6">6</button>' * 8,
        # Both the historical 4,715-character regression and the benchmark's
        # 9,742-character complete section must remain intact.
        script_state,
        "function enter(){stack.push(renderDisplay());} function add(){return 0;}"
        + ("/* operation behavior */" * 30),
        "document.querySelectorAll('.key').forEach((key)=>key.onclick=()=>{});"
        + ("/* control behavior */" * 30),
        "function advancedOperation(){return 0;}" + ("/* advanced behavior */" * 48),
    ]
    provider = MagicMock(provider_name="nvidia")
    provider.chat_completion = AsyncMock(
        side_effect=[json.dumps({"content": chunk}) for chunk in chunks]
    )
    uow = MagicMock()
    uow.model_calls.ensure_budget = AsyncMock()
    uow.model_calls.record_call = AsyncMock()

    plan = await ChiefEngineerService(uow).plan_semantic_repair(
        project_id=1,
        run_id=2,
        task_id=3,
        task_contract={
            "title": "Build calculator shell",
            "visual_required": True,
            "visual_actual_output": "app/index.html",
            "allowed_files": ["app/index.html"],
        },
        changed_files_context="app/index.html is missing",
        validation_output="visual output is missing",
        provider=provider,
        model="vision-model",
    )

    assert provider.chat_completion.await_count == 19
    assert uow.model_calls.record_call.await_count == 19
    assert plan.actions[0].kind == "write_file"
    assert plan.actions[0].path == "app/index.html"
    assert plan.actions[0].content.startswith("<!DOCTYPE html>")
    assert all(chunk in plan.actions[0].content for chunk in chunks)


@pytest.mark.anyio
async def test_omniroute_visual_generation_uses_monolithic_recovery_after_segment_failure(
    monkeypatch,
) -> None:
    service = ChiefEngineerService(MagicMock())
    expected = ChiefEngineerRepairPlan(
        summary="monolithic recovery",
        actions=[
            {
                "kind": "write_file",
                "path": "app/index.html",
                "content": "<html><body><script>run()</script></body></html>",
            }
        ],
    )
    segmented = AsyncMock(side_effect=LLMError("script section unavailable"))
    monolithic = AsyncMock(return_value=expected)
    monkeypatch.setattr(service, "_plan_segmented_visual_repair", segmented)
    monkeypatch.setattr(service, "_plan_single_visual_repair", monolithic)

    plan = await service.plan_semantic_repair(
        project_id=1,
        run_id=2,
        task_id=3,
        task_contract={
            "visual_required": True,
            "visual_actual_output": "app/index.html",
            "allowed_files": ["app/index.html"],
        },
        changed_files_context="app/index.html is missing",
        validation_output="visual output is missing",
        provider=MagicMock(provider_name="omniroute"),
        model="nvidia/live-primary",
    )

    assert plan is expected
    segmented.assert_awaited_once()
    monolithic.assert_awaited_once()


def test_chief_engineer_provider_metadata_records_fallback_use():
    from localforge.chief_engineer.service import _provider_metadata

    provider = MagicMock()
    provider.primary_provider_name = "nvidia"
    provider.fallback_provider_name = "openrouter"
    provider.used_fallback = True

    assert _provider_metadata(provider) == {
        "primary_provider": "nvidia",
        "fallback_provider": "openrouter",
        "used_fallback": True,
    }


@pytest.mark.anyio
async def test_chief_engineer_falls_back_on_primary_timeout():
    primary = MagicMock(provider_name="nvidia", default_model="primary-model")
    primary.chat_completion = AsyncMock(side_effect=LLMTimeoutError("timeout"))
    fallback = MagicMock(provider_name="openrouter", default_model="fallback-model")
    fallback.chat_completion = AsyncMock(return_value="ok")
    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
        primary_timeout=30.0,
    )

    result = await provider.chat_completion([{"role": "user", "content": "work"}])

    assert result == "ok"
    assert provider.used_fallback is True
    fallback.chat_completion.assert_awaited_once()


@pytest.mark.anyio
async def test_chief_engineer_does_not_fallback_on_missing_model_configuration():
    primary = MagicMock(provider_name="nvidia", default_model="primary-model")
    primary.chat_completion = AsyncMock(
        side_effect=LLMHTTPError("model not found", status_code=404)
    )
    fallback = MagicMock(provider_name="openrouter", default_model="fallback-model")
    fallback.chat_completion = AsyncMock(return_value="ok")
    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
        primary_timeout=30.0,
    )

    with pytest.raises(LLMHTTPError, match="model not found"):
        await provider.chat_completion([{"role": "user", "content": "work"}])

    assert provider.used_fallback is False
    fallback.chat_completion.assert_not_awaited()


@pytest.mark.anyio
async def test_chief_engineer_falls_back_on_provider_server_failure():
    primary = MagicMock(provider_name="omniroute", default_model="primary-model")
    primary.chat_completion = AsyncMock(
        side_effect=LLMHTTPError("upstream unavailable", status_code=503)
    )
    fallback = MagicMock(provider_name="openrouter", default_model="fallback-model")
    fallback.chat_completion = AsyncMock(return_value="ok")
    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
        primary_timeout=30.0,
    )

    assert await provider.chat_completion([{"role": "user", "content": "work"}]) == "ok"
    assert provider.used_fallback is True
    fallback.chat_completion.assert_awaited_once()


@pytest.mark.anyio
async def test_chief_engineer_circuit_skips_repeated_primary_outage():
    primary = MagicMock(
        provider_name="omniroute",
        base_url="http://gateway.test/v1",
        default_model="primary-model",
    )
    primary.chat_completion = AsyncMock(
        side_effect=LLMHTTPError("upstream unavailable", status_code=503)
    )
    fallback = MagicMock(provider_name="openrouter", default_model="fallback-model")
    fallback.chat_completion = AsyncMock(return_value="ok")
    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
        primary_timeout=30.0,
    )

    await provider.chat_completion([{"role": "user", "content": "first"}])
    await provider.chat_completion([{"role": "user", "content": "second"}])
    await provider.chat_completion([{"role": "user", "content": "third"}])

    assert primary.chat_completion.await_count == 2
    assert fallback.chat_completion.await_count == 3


def test_nvidia_chief_does_not_send_provider_aliases_to_primary():
    provider = MagicMock(primary_provider_name="nvidia", provider_name="nvidia")

    assert _chief_model_sequence(
        provider,
        "minimaxai/minimax-m3",
        ["auto/pro-coding", "auto/best-coding"],
    ) == ["minimaxai/minimax-m3"]


def test_omniroute_chief_keeps_gateway_aliases_even_with_nvidia_primary_metadata():
    provider = MagicMock(primary_provider_name="nvidia", provider_name="omniroute")

    assert _chief_model_sequence(
        provider,
        "nvidia/minimaxai/minimax-m3",
        ["auto/best-coding", "nvidia/nvidia/nemotron-3-nano-30b-a3b"],
    ) == [
        "nvidia/minimaxai/minimax-m3",
        "auto/best-coding",
        "nvidia/nvidia/nemotron-3-nano-30b-a3b",
    ]


@pytest.mark.anyio
async def test_chief_engineer_keeps_multimodal_failure_on_primary_route():
    primary = MagicMock(provider_name="nvidia", default_model="primary-model")
    primary.chat_completion = AsyncMock(side_effect=LLMTimeoutError("vision timeout"))
    fallback = MagicMock(provider_name="openrouter", default_model="fallback-model")
    fallback.chat_completion = AsyncMock(return_value="should not receive an image")
    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
        primary_timeout=30.0,
    )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "repair the visual layout"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,test"}},
            ],
        }
    ]
    with pytest.raises(LLMTimeoutError, match="vision timeout"):
        await provider.chat_completion(messages)

    assert provider.used_fallback is False
    fallback.chat_completion.assert_not_awaited()


def test_chief_engineer_repair_plan_normalizes_singular_action():
    plan = ChiefEngineerRepairPlan.model_validate(
        {
            "summary": "single action response",
            "action": {
                "type": "write_file",
                "file": "app/index.html",
                "text": "<html></html>",
            },
        }
    )

    assert len(plan.actions) == 1
    assert plan.actions[0].kind == "write_file"
    assert plan.actions[0].path == "app/index.html"


def test_chief_engineer_repair_plan_normalizes_nested_operation_action():
    plan = ChiefEngineerRepairPlan.model_validate(
        {
            "summary": "nested action response",
            "actions": [
                {
                    "write_file": {
                        "path": "app/forge_ledger.py",
                        "content": "def add_entry():\n    return True\n",
                    }
                }
            ],
            "risk_notes": "The action is bounded to the contracted product file.",
        }
    )

    assert len(plan.actions) == 1
    assert plan.actions[0].kind == "write_file"
    assert plan.actions[0].path == "app/forge_ledger.py"
    assert "add_entry" in plan.actions[0].content
    assert plan.risk_notes == ["The action is bounded to the contracted product file."]


@pytest.mark.anyio
async def test_chief_engineer_does_not_hide_primary_authentication_error():
    primary = MagicMock(provider_name="nvidia", default_model="primary-model")
    primary.chat_completion = AsyncMock(side_effect=LLMHTTPError("unauthorized", status_code=401))
    fallback = MagicMock(provider_name="openrouter", default_model="fallback-model")
    fallback.chat_completion = AsyncMock(return_value="should not run")
    provider = FallbackLLMProvider(
        primary=primary,
        fallback=fallback,
        primary_timeout=30.0,
    )

    with pytest.raises(LLMHTTPError, match="unauthorized"):
        await provider.chat_completion([{"role": "user", "content": "work"}])

    assert provider.used_fallback is False
    fallback.chat_completion.assert_not_awaited()


@pytest.mark.anyio
async def test_openrouter_provider_redacts_api_key_on_http_error():
    provider = OpenRouterProvider(
        api_key="sk-or-secret",
        default_model="minimax/minimax-m3",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 402
    mock_resp.text = "insufficient credits for sk-or-secret"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(LLMError) as exc:
            await provider.chat_completion(
                [{"role": "user", "content": "return json"}],
                response_schema={"type": "object"},
            )

    assert "sk-or-secret" not in str(exc.value)
    assert "[redacted]" in str(exc.value)
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["model"] == "minimax/minimax-m3"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-or-secret"


def test_paid_model_ledger_records_and_enforces_run_budget(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase31.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))

    async def exercise() -> dict[str, object]:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            assert uow.model_calls is not None
            project = await uow.projects.create_project(
                domain.Project(name="Phase 31", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.UNATTENDED,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                    resource_limits={
                        "max_paid_calls": 1,
                        "max_paid_input_tokens": 100,
                        "max_paid_output_tokens": 100,
                        "max_paid_usd": 0.01,
                    },
                )
            )
            assert run.id is not None
            await uow.model_calls.ensure_budget(
                project_id=project.id,
                run_id=run.id,
                estimated_input_tokens=20,
                estimated_output_tokens=10,
            )
            call = await uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project.id,
                    run_id=run.id,
                    provider="openrouter",
                    model="minimax/minimax-m3",
                    reason=ChiefEngineerCallReason.ARCHITECTURE_PLAN,
                    input_tokens=20,
                    output_tokens=10,
                    estimated_cost_usd=0.000018,
                    status="success",
                )
            )
            try:
                await uow.model_calls.ensure_budget(
                    project_id=project.id,
                    run_id=run.id,
                    estimated_input_tokens=1,
                    estimated_output_tokens=1,
                )
            except ValueError as exc:
                blocked = str(exc)
            else:
                blocked = ""
            calls = await uow.model_calls.list_calls(project_id=project.id, run_id=run.id)
            return {"call_id": call.id, "blocked": blocked, "count": len(calls)}

    data = asyncio.run(exercise())
    asyncio.run(manager.close())

    assert data["call_id"] is not None
    assert data["count"] == 1
    assert "max_paid_calls" in str(data["blocked"])


def test_omniroute_gateway_budget_is_separate_from_paid_budget(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'gateway-budget.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))

    async def exercise() -> str:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            assert uow.model_calls is not None
            project = await uow.projects.create_project(
                domain.Project(
                    name="Gateway budget",
                    root_path=str(tmp_path),
                    default_branch="main",
                )
            )
            assert project.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.UNATTENDED,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                    resource_limits={
                        "max_gateway_calls": 2,
                        "max_paid_calls": 1,
                        "max_paid_input_tokens": 1,
                        "max_paid_output_tokens": 1,
                        "max_paid_usd": 0.01,
                    },
                )
            )
            assert run.id is not None

            for _ in range(2):
                await uow.model_calls.ensure_budget(
                    project_id=project.id,
                    run_id=run.id,
                    estimated_input_tokens=20,
                    estimated_output_tokens=10,
                    provider="omniroute",
                    model="nvidia/minimaxai/minimax-m3",
                )
                await uow.model_calls.record_call(
                    domain.ModelCallLedger(
                        project_id=project.id,
                        run_id=run.id,
                        provider="omniroute",
                        model="nvidia/minimaxai/minimax-m3",
                        reason=ChiefEngineerCallReason.ARCHITECTURE_PLAN,
                        input_tokens=20,
                        output_tokens=10,
                        estimated_cost_usd=0.0,
                        status="success",
                    )
                )

            with pytest.raises(ValueError, match="gateway budget.*max_gateway_calls"):
                await uow.model_calls.ensure_budget(
                    project_id=project.id,
                    run_id=run.id,
                    estimated_input_tokens=20,
                    estimated_output_tokens=10,
                    provider="omniroute",
                    model="nvidia/minimaxai/minimax-m3",
                )
            return "ok"

    assert asyncio.run(exercise()) == "ok"
    asyncio.run(manager.close())


def test_omniroute_reported_cost_uses_shared_usd_budget(tmp_path):
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'gateway-cost.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))

    async def exercise() -> str:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.executions is not None
            assert uow.model_calls is not None
            project = await uow.projects.create_project(
                domain.Project(name="Gateway cost", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.UNATTENDED,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                    resource_limits={"max_gateway_calls": 4, "max_paid_usd": 0.01},
                )
            )
            assert run.id is not None
            call = await uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project.id,
                    run_id=run.id,
                    provider="omniroute",
                    model="nvidia/minimaxai/minimax-m3",
                    reason=ChiefEngineerCallReason.ARCHITECTURE_PLAN,
                    input_tokens=20,
                    output_tokens=10,
                    estimated_cost_usd=0.02,
                    status="success",
                )
            )
            assert call.estimated_cost_usd == 0.02
            with pytest.raises(ValueError, match="gateway budget.*max_paid_usd") as exc:
                await uow.model_calls.ensure_budget(
                    project_id=project.id,
                    run_id=run.id,
                    estimated_input_tokens=20,
                    estimated_output_tokens=10,
                    provider="omniroute",
                    model="nvidia/minimaxai/minimax-m3",
                )
            return str(exc.value)

    message = asyncio.run(exercise())
    asyncio.run(manager.close())

    assert "max_paid_usd" in message


def test_api_exposes_chief_engineer_call_ledger_without_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALFORGE_CHIEF_MODEL", "auto/best-reasoning")
    monkeypatch.setenv("LOCALFORGE_CHIEF_API_KEY", "gateway-secret")
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase32.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))

    async def seed() -> int:
        async with UnitOfWork(manager) as uow:
            assert uow.projects is not None
            assert uow.model_calls is not None
            project = await uow.projects.create_project(
                domain.Project(name="Phase 32", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            await uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project.id,
                    provider="openrouter",
                    model="minimax/minimax-m3",
                    reason=ChiefEngineerCallReason.FINAL_PR_REVIEW,
                    input_tokens=10,
                    output_tokens=5,
                    estimated_cost_usd=0.000009,
                    status="success",
                )
            )
            return project.id

    project_id = asyncio.run(seed())
    client = TestClient(create_app(db_manager=manager))

    response = client.get(f"/projects/{project_id}/chief-engineer/calls")
    asyncio.run(manager.close())

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "auto/best-reasoning"
    assert payload["api_key_configured"] is True
    assert "sk-or-hidden" not in response.text
    assert payload["calls"][0]["reason"] == "FINAL_PR_REVIEW"
