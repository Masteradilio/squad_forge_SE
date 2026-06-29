import json

from pydantic import BaseModel, Field
from pydantic import field_validator, model_validator

from localforge.llm.base import BaseLLMProvider, LLMError
from localforge.llm.validator import chat_completion_validated
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason
from localforge.prd.contracts import ArchitectureContract
from localforge.runtime.actions import RuntimeActionProposal
from localforge.services.model_calls import estimate_paid_call_cost_usd
from localforge.storage.transactions import UnitOfWork


class ChiefEngineerContractReview(BaseModel):
    approved: bool
    summary: str
    required_changes: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class ChiefEngineerRepairAction(BaseModel):
    kind: str | None = None
    path: str | None = None
    content: str = ""
    command: str | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: object) -> object:
        if isinstance(value, str):
            if value in {
                "create_file",
                "update_file",
                "replace_file",
                "write_content",
                "edit_file",
                "patch_file",
                "modify_file",
                "edit",
            }:
                return "write_file"
        return value

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, obj: object) -> object:
        if not isinstance(obj, dict):
            return obj
        normalized = dict(obj)
        if "kind" not in normalized:
            for key in ("type", "action", "operation"):
                if key in normalized:
                    normalized["kind"] = normalized[key]
                    break
        if "path" not in normalized:
            for key in ("file", "filename", "file_path"):
                if key in normalized:
                    normalized["path"] = normalized[key]
                    break
        if "content" not in normalized:
            for key in ("code", "body", "text"):
                if key in normalized:
                    normalized["content"] = normalized[key]
                    break
        return normalized

    def to_runtime_action(self) -> RuntimeActionProposal:
        return RuntimeActionProposal.model_validate(
            {
                "kind": self.kind or "write_file",
                "path": self.path,
                "content": self.content,
                "command": self.command,
            }
        )


class ChiefEngineerRepairPlan(BaseModel):
    summary: str = "Chief Engineer repair plan"
    failure_class: str = "SEMANTIC_TEST_FAILURE"
    actions: list[ChiefEngineerRepairAction] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("actions", mode="before")
    @classmethod
    def _normalize_actions(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("risk_notes", mode="before")
    @classmethod
    def _normalize_risk_notes(cls, value: object) -> object:
        if isinstance(value, str):
            return [value]
        return value

    @model_validator(mode="after")
    def _require_repair_actions(self) -> "ChiefEngineerRepairPlan":
        if not self.actions:
            raise ValueError("Chief Engineer semantic repair requires at least one action.")
        return self

    def runtime_actions(self) -> list[RuntimeActionProposal]:
        return [action.to_runtime_action() for action in self.actions]


class ChiefEngineerService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        from localforge.chief_engineer.bundler import EconomyPromptBundler
        self.bundler = EconomyPromptBundler()

    async def review_contract(
        self,
        *,
        project_id: int,
        run_id: int | None,
        contract: ArchitectureContract,
        provider: BaseLLMProvider,
        model: str,
    ) -> ChiefEngineerContractReview:
        assert self.uow.model_calls is not None
        contract_json = self.bundler.redact_sensitive_info(contract.model_dump_json())
        messages = [
            {
                "role": "system",
                "content": (
                    "You are LocalForge Chief Engineer. Economy-first: review only the "
                    "architecture contract. Do not write implementation code. Return "
                    "short JSON with approved, summary, required_changes, risk_notes."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review this contract for module/API consistency, task boundaries, "
                    "forbidden dependency risk, and whether local worker tasks are bounded.\n"
                    f"{contract_json}"
                ),
            },
        ]
        estimated_input = _estimate_tokens(json.dumps(messages))
        estimated_output = 512
        await self.uow.model_calls.ensure_budget(
            project_id=project_id,
            run_id=run_id,
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
        )
        try:
            review = await chat_completion_validated(
                provider=provider,
                messages=messages,
                schema_model=ChiefEngineerContractReview,
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
            await self.uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project_id,
                    run_id=run_id,
                    provider="openrouter",
                    model=model,
                    reason=ChiefEngineerCallReason.CONTRACT_FREEZE,
                    input_tokens=estimated_input,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimate_paid_call_cost_usd(
                        estimated_input, output_tokens
                    ),
                    status=status,
                    error_summary=error_summary,
                )
            )
            raise LLMError(f"Chief Engineer contract review failed: {error_summary}") from exc

        await self.uow.model_calls.record_call(
            domain.ModelCallLedger(
                project_id=project_id,
                run_id=run_id,
                provider="openrouter",
                model=model,
                reason=ChiefEngineerCallReason.CONTRACT_FREEZE,
                input_tokens=estimated_input,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_paid_call_cost_usd(
                    estimated_input, output_tokens
                ),
                status=status,
                error_summary=error_summary,
                metadata={"approved": review.approved},
            )
        )
        return review

    async def plan_semantic_repair(
        self,
        *,
        project_id: int,
        run_id: int | None,
        task_id: int | None,
        task_contract: dict[str, object],
        changed_files_context: str,
        validation_output: str,
        provider: BaseLLMProvider,
        model: str,
    ) -> ChiefEngineerRepairPlan:
        assert self.uow.model_calls is not None
        bundle = self.bundler.build_bundle(
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            task_contract=task_contract,
            changed_files_context=changed_files_context,
            validation_output=validation_output,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are LocalForge Chief Engineer. Economy-first hard repair. "
                    "Return strict JSON with summary, failure_class, actions, risk_notes. "
                    "Return at most one action per call; choose the smallest complete file "
                    "rewrite that can make the failing validation pass. "
                    "Actions must use only write_file or append_content. "
                    "Write only paths allowed by task_contract.allowed_files. "
                    "Do not edit tests unless the contract explicitly allows that test file. "
                    "For HTML/CSS visual repairs, return the complete target file content; "
                    "never omit repeated keys, labels, styles, or markup for brevity. "
                    "Do not use placeholders such as 'remaining keys omitted'. "
                    "Fix production code, imports, exports, syntax, and semantics needed for "
                    "the canonical task test to pass."
                ),
            },
            {"role": "user", "content": json.dumps(bundle, sort_keys=True)},
        ]
        estimated_input = _estimate_tokens(json.dumps(messages))
        estimated_output = 8000 if task_contract.get("visual_required") else 1800
        await self.uow.model_calls.ensure_budget(
            project_id=project_id,
            run_id=run_id,
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
        )
        try:
            plan = await chat_completion_validated(
                provider=provider,
                messages=messages,
                schema_model=ChiefEngineerRepairPlan,
                model=model,
                timeout=300.0,
                max_retries=2,
            )
            status = "success"
            error_summary = None
            output_tokens = _estimate_tokens(plan.model_dump_json())
        except Exception as exc:
            status = "failed"
            error_summary = str(exc)[:500]
            output_tokens = 0
            await self.uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    provider="openrouter",
                    model=model,
                    reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                    input_tokens=estimated_input,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimate_paid_call_cost_usd(
                        estimated_input, output_tokens
                    ),
                    status=status,
                    error_summary=error_summary,
                )
            )
            raise LLMError(f"Chief Engineer semantic repair failed: {error_summary}") from exc
        await self.uow.model_calls.record_call(
            domain.ModelCallLedger(
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                provider="openrouter",
                model=model,
                reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                input_tokens=estimated_input,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_paid_call_cost_usd(
                    estimated_input, output_tokens
                ),
                status=status,
                error_summary=error_summary,
                metadata={"failure_class": plan.failure_class, "actions": len(plan.actions or [])},
            )
        )
        return plan


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
