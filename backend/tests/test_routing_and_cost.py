from datetime import UTC, datetime

import pytest
from localforge.models import domain
from localforge.services.model_calls import ModelCallLedgerService
from localforge.services.routing import ModelRoutingService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_pricing_sources_and_snapshots_seeded(db_session: AsyncSession):
    ledger_service = ModelCallLedgerService(db_session)

    sources = await ledger_service.list_pricing_sources()
    assert len(sources) >= 3

    providers = {s.provider for s in sources}
    assert "OpenAI" in providers
    assert "Anthropic" in providers
    assert "Google" in providers

    snapshots = await ledger_service.list_pricing_snapshots()
    assert len(snapshots) >= 9

    model_names = {snap.model_name for snap in snapshots}
    assert "gpt-5.5-large" in model_names
    assert "claude-opus-4.8" in model_names
    assert "gemini-2.5-pro" in model_names


@pytest.mark.asyncio
async def test_model_capabilities_tracking(db_session: AsyncSession):
    routing_service = ModelRoutingService(db_session)

    model = "minimax/minimax-m3"
    task_class = "visual_parity"

    # 1. Initially should be None
    cap = await routing_service.get_model_capability(model, task_class)
    assert cap is None

    # 2. Save new capability
    new_cap = domain.ModelCapability(
        model_name=model, task_class=task_class, success_count=1, failure_count=0
    )
    saved = await routing_service.save_model_capability(new_cap)
    assert saved.model_name == model
    assert saved.success_count == 1

    # 3. Disqualify model
    await routing_service.disqualify_model(
        model, task_class, reason="Truncated large HTML file", duration_seconds=60
    )

    updated = await routing_service.get_model_capability(model, task_class)
    assert updated is not None
    assert updated.failure_count == 1
    assert updated.disqualified_until is not None
    assert updated.disqualification_reason == "Truncated large HTML file"
    assert updated.disqualified_until.replace(tzinfo=None) > datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_cost_benchmark_calculation(db_session: AsyncSession):
    from localforge.models.enums import ChiefEngineerCallReason
    from localforge.services.cost_benchmark import CostBenchmarkService

    ledger_svc = ModelCallLedgerService(db_session)
    benchmark_svc = CostBenchmarkService(db_session)

    # 1. Record mock calls
    # Paid large call (Chief Engineer)
    await ledger_svc.record_call(
        domain.ModelCallLedger(
            project_id=1,
            run_id=10,
            task_id=20,
            provider="openrouter",
            model="minimax/minimax-m3",
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            input_tokens=100000,
            output_tokens=10000,
            estimated_cost_usd=0.042,  # Mock price
            status="success",
        )
    )

    # Local medium call (Coder)
    await ledger_svc.record_call(
        domain.ModelCallLedger(
            project_id=1,
            run_id=10,
            task_id=20,
            provider="ollama",
            model="granite4.1:8b",
            reason=ChiefEngineerCallReason.E2E_RETROSPECTIVE,  # treated as Coder/Medium by fallback
            input_tokens=50000,
            output_tokens=5000,
            estimated_cost_usd=0.0,  # Free
            status="success",
        )
    )

    # 2. Calculate benchmarks
    res = await benchmark_svc.calculate_benchmarks(project_id=1, run_id=10)
    assert res["actual_paid_usd"] == 0.042
    assert res["actual_calls"] == 1
    assert res["local_calls_avoided"] == 1

    # Check hypothetical calculations (OpenAI large and medium tier costs)
    # Paid large: (100k * 5 + 10k * 30)/1M = 0.50 + 0.30 = 0.80 USD
    # Local medium: (50k * 2.5 + 5k * 15)/1M = 0.125 + 0.075 = 0.20 USD
    # OpenAI hypothetical: 0.80 + 0.20 = 1.00 USD
    assert abs(res["openai_hypothetical_usd"] - 1.00) < 0.001
    assert res["openai_savings_usd"] > 0.0

    # 3. Generate markdown
    report = await benchmark_svc.generate_markdown_report(project_id=1, run_id=10)
    assert "Cost Benchmark Report" in report
    assert "OpenAI API-Only" in report
    assert "$0.0420" in report
