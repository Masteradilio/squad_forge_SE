import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.core.config import load_config
from localforge.llm import LLMError
from localforge.llm.base import LLMHTTPError, LLMTimeoutError
from localforge.llm.factory import build_chief_engineer_provider
from localforge.llm.fallback import FallbackLLMProvider
from localforge.llm.openrouter import OpenRouterProvider
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason, RunMode, RunStatus
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_config_loads_openrouter_chief_engineer_from_env_file(tmp_path, monkeypatch):
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


def test_config_prefers_nvidia_chief_engineer_from_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "NVIDIA_LLM_MODEL=minimax/minimax-m3\n"
        "NVIDIA_API_KEY=nvapi-secret\n"
        "OPENROUTER_MODEL=minimax/minimax-m3\n"
        "OPENROUTER_API_KEY=sk-or-fallback\n",
        encoding="utf-8",
    )

    config = load_config()

    assert config.chief_engineer.provider == "nvidia"
    assert config.chief_engineer.model == "minimax/minimax-m3"
    assert config.chief_engineer.api_key == "nvapi-secret"
    assert config.chief_engineer.fallback_provider == "openrouter"
    assert config.chief_engineer.fallback_api_key == "sk-or-fallback"
    assert isinstance(build_chief_engineer_provider(config), FallbackLLMProvider)


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


def test_api_exposes_chief_engineer_call_ledger_without_secret(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_MODEL", "minimax/minimax-m3")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-hidden")
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
    assert payload["model"] == "minimax/minimax-m3"
    assert payload["api_key_configured"] is True
    assert "sk-or-hidden" not in response.text
    assert payload["calls"][0]["reason"] == "FINAL_PR_REVIEW"
