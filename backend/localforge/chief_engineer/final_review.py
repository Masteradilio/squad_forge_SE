import json
from typing import Any

from pydantic import BaseModel, Field

from localforge.chief_engineer.service import ChiefEngineerService, _estimate_tokens
from localforge.llm.base import BaseLLMProvider, LLMError
from localforge.llm.validator import chat_completion_validated
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason
from localforge.services.model_calls import estimate_paid_call_cost_usd


class FinalPRReview(BaseModel):
    approved: bool
    summary: str
    required_changes: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class FinalReviewService:
    def __init__(self, chief_engineer: ChiefEngineerService):
        self.chief_engineer = chief_engineer

    async def review_pr(
        self,
        *,
        project_id: int,
        run_id: int | None,
        task_id: int | None,
        provider: BaseLLMProvider,
        model: str,
        task_contract: dict[str, Any],
        diff_summary: str,
        verifier_results: dict[str, Any],
        test_output_summary: str,
        risk_notes: list[str],
    ) -> FinalPRReview:
        uow = self.chief_engineer.uow
        assert uow.model_calls is not None
        bundler = self.chief_engineer.bundler

        redacted_diff = bundler.redact_sensitive_info(diff_summary[:8000])
        redacted_test_output = bundler.redact_sensitive_info(
            bundler.compress_diff_and_errors(test_output_summary, max_chars=4000)
        )
        clean_contract = {}
        if isinstance(task_contract, dict):
            for k, v in task_contract.items():
                if k not in ("api_key", "secret", "token", "password"):
                    clean_contract[k] = v

        bundle = {
            "task_contract": clean_contract,
            "diff_summary": redacted_diff,
            "verifier_results": verifier_results,
            "test_output_summary": redacted_test_output,
            "risk_notes": risk_notes[:10],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You are LocalForge Chief Engineer. Economy-first final PR review: "
                    "approve only when deterministic evidence supports the diff. "
                    "Return strict JSON with approved, summary, required_changes, risk_notes."
                ),
            },
            {"role": "user", "content": json.dumps(bundle, sort_keys=True)},
        ]

        # Budget preview print/log
        estimated_input = _estimate_tokens(json.dumps(messages))
        print(
            f"[Economy Bundler] Previewing API call: reason=FINAL_PR_REVIEW, estimated_input_tokens={estimated_input}"
        )
        estimated_output = 512
        await uow.model_calls.ensure_budget(
            project_id=project_id,
            run_id=run_id,
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
            provider=str(getattr(provider, "provider_name", "omniroute")),
        )
        try:
            review = await chat_completion_validated(
                provider=provider,
                messages=messages,
                schema_model=FinalPRReview,
                model=model,
                timeout=240.0,
                max_retries=0,
            )
            status = "success"
            error_summary = None
            output_tokens = _estimate_tokens(review.model_dump_json())
        except Exception as exc:
            status = "failed"
            error_summary = str(exc)[:500]
            output_tokens = 0
            await uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    provider=str(getattr(provider, "provider_name", "omniroute")),
                    model=model,
                    reason=ChiefEngineerCallReason.FINAL_PR_REVIEW,
                    input_tokens=estimated_input,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, output_tokens),
                    status=status,
                    error_summary=error_summary,
                )
            )
            raise LLMError(f"Chief Engineer final review failed: {error_summary}") from exc
        await uow.model_calls.record_call(
            domain.ModelCallLedger(
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                provider=str(getattr(provider, "provider_name", "omniroute")),
                model=model,
                reason=ChiefEngineerCallReason.FINAL_PR_REVIEW,
                input_tokens=estimated_input,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, output_tokens),
                status=status,
                error_summary=error_summary,
                metadata={"approved": review.approved},
            )
        )
        return review
