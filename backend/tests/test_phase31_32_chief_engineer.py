import asyncio
import json
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
    _validate_visual_repair_plan,
    _validate_visual_section,
    _visual_section_models,
)
from localforge.core.config import LocalForgeConfig, load_config
from localforge.llm import LLMError
from localforge.llm.base import LLMHTTPError, LLMTimeoutError
from localforge.llm.fallback import FallbackLLMProvider
from localforge.llm.openrouter import OpenRouterProvider
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason, RunMode, RunStatus
from localforge.pipeline.engine import RolePipelineEngine, _chief_model_sequence
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_legacy_vendor_keys_do_not_bypass_cloud_gateway(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "OPENROUTER_MODEL=minimax/minimax-m3\nOPENROUTER_API_KEY=test-secret-key\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "omniroute"
    assert config.chief_engineer.model == "auto/best-free"
    assert config.chief_engineer.api_key is None
    assert config.chief_engineer.base_url == "http://localhost:20128/v1"
    assert config.budgets.max_paid_calls == 30


def test_legacy_nvidia_keys_do_not_bypass_cloud_gateway(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "NVIDIA_LLM_MODEL=minimax/minimax-m3\n"
        "NVIDIA_API_KEY=nvapi-secret\n"
        "OPENROUTER_MODEL=minimax/minimax-m3\n"
        "OPENROUTER_API_KEY=sk-or-fallback\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "omniroute"
    assert config.chief_engineer.model == "auto/best-free"
    assert config.chief_engineer.api_key is None
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
async def test_visual_repair_is_assembled_from_bounded_calls() -> None:
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
        "const stack=[]; function renderDisplay(){return stack[0] ?? 0;}"
        + ("/* state behavior */" * 30),
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
async def test_chief_engineer_falls_back_on_primary_model_not_found():
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

    result = await provider.chat_completion([{"role": "user", "content": "work"}])

    assert result == "ok"
    assert provider.used_fallback is True
    fallback.chat_completion.assert_awaited_once()


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
