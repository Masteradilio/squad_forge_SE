import asyncio
import json
import logging
import os
import re
from contextlib import contextmanager
from time import monotonic
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.llm.base import (
    BaseLLMProvider,
    LLMConnectionError,
    LLMError,
    LLMHTTPError,
    LLMMessage,
    LLMTimeoutError,
)
from localforge.llm.validator import chat_completion_validated
from localforge.models import domain
from localforge.models.enums import ChiefEngineerCallReason
from localforge.observability.tracer import OpenTelemetryTracer
from localforge.prd.contracts import ArchitectureContract
from localforge.runtime.actions import RuntimeActionProposal
from localforge.runtime.agent_harness import AgentHarness, ContextBlock
from localforge.services.model_calls import estimate_paid_call_cost_usd
from localforge.services.pricing import is_free_gateway_model
from localforge.storage.transactions import UnitOfWork

logger = logging.getLogger(__name__)


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
        # Some OpenAI-compatible routes honor the requested operation schema
        # but wrap the action payload under the operation name instead of
        # returning the canonical flat shape. Preserve that model output while
        # converting it into the frozen ForgeOS action contract.
        for operation in ("write_file", "append_content", "run_command"):
            nested = normalized.get(operation)
            if isinstance(nested, dict):
                normalized = {**normalized, **nested, "kind": operation}
                break
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
        kind = self.kind or "write_file"
        if kind not in ("write_file", "append_content", "run_command"):
            kind = "write_file"
        return RuntimeActionProposal.model_validate(
            {
                "kind": kind,
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

    @model_validator(mode="before")
    @classmethod
    def _normalize_single_action(cls, value: object) -> object:
        """Accept the singular action shape emitted by some strict JSON models."""
        if not isinstance(value, dict) or value.get("actions"):
            return value
        for key in ("action", "repair_action", "proposal"):
            candidate = value.get(key)
            if isinstance(candidate, dict):
                normalized = dict(value)
                normalized["actions"] = [candidate]
                return normalized
        return value

    @model_validator(mode="after")
    def _require_repair_actions(self) -> "ChiefEngineerRepairPlan":
        if not self.actions:
            raise ValueError("Chief Engineer semantic repair requires at least one action.")
        return self

    def runtime_actions(self) -> list[RuntimeActionProposal]:
        return [action.to_runtime_action() for action in self.actions]


class ChiefEngineerVisualSection(BaseModel):
    """One bounded section of a standalone visual product document."""

    content: str


class ChiefEngineerService:
    def __init__(self, uow: UnitOfWork, *, tracer: OpenTelemetryTracer | None = None):
        self.uow = uow
        self.harness = AgentHarness(tracer=tracer)
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
        if self.uow.projects is not None:
            project = await self.uow.projects.get_project(project_id)
            if project is not None:
                self.harness.attach_harness_state(project.root_path)
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
                    "forbidden dependency risk, and whether local worker tasks are bounded."
                ),
            },
        ]
        estimated_input = _estimate_message_tokens(messages)
        estimated_output = 512
        await self.uow.model_calls.ensure_budget(
            project_id=project_id,
            run_id=run_id,
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
            provider=str(getattr(provider, "provider_name", "omniroute")),
        )
        try:
            harness_result = await self.harness.call(
                provider=provider,
                contract=self.harness.contract_for(
                    role="Chief Engineer",
                    method="review_contract",
                    risk_level="high",
                    strategy="predict",
                    max_retries=0,
                    context_budget=8000,
                ),
                messages=messages,
                context_blocks=[
                    ContextBlock(
                        name="architecture_contract",
                        content=contract_json,
                        priority=100,
                        required=True,
                    )
                ],
                model=model,
                timeout=240.0,
                response_model=ChiefEngineerContractReview,
            )
            review = ChiefEngineerContractReview.model_validate(harness_result.parsed)
            status = "success"
            error_summary = None
            output_tokens = _estimate_tokens(harness_result.content)
        except Exception as exc:
            status = "failed"
            error_summary = str(exc)[:500]
            output_tokens = 0
            await self.uow.model_calls.record_call(
                domain.ModelCallLedger(
                    project_id=project_id,
                    run_id=run_id,
                    provider=str(getattr(provider, "provider_name", "omniroute")),
                    model=model,
                    reason=ChiefEngineerCallReason.CONTRACT_FREEZE,
                    input_tokens=estimated_input,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, output_tokens),
                    status=status,
                    error_summary=error_summary,
                    metadata=_provider_metadata(provider),
                )
            )
            raise LLMError(f"Chief Engineer contract review failed: {error_summary}") from exc

        await self.uow.model_calls.record_call(
            domain.ModelCallLedger(
                project_id=project_id,
                run_id=run_id,
                provider=str(getattr(provider, "provider_name", "omniroute")),
                model=model,
                reason=ChiefEngineerCallReason.CONTRACT_FREEZE,
                input_tokens=estimated_input,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, output_tokens),
                status=status,
                error_summary=error_summary,
                metadata={**_provider_metadata(provider), "approved": review.approved},
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
        visual_reference_image_path: str | None = None,
        visual_actual_image_path: str | None = None,
    ) -> ChiefEngineerRepairPlan:
        assert self.uow.model_calls is not None
        if task_contract.get("visual_required"):
            # A visual task remains Chief-only. OmniRoute defaults to bounded
            # independently validated sections because free routes often
            # truncate a monolithic HTML response before validation starts.
            provider_name = str(getattr(provider, "provider_name", "omniroute")).lower()
            if (
                provider_name != "omniroute"
                or os.getenv("LOCALFORGE_VISUAL_SECTION_FALLBACK", "true").lower()
                == "true"
            ):
                try:
                    return await self._plan_segmented_visual_repair(
                        project_id=project_id,
                        run_id=run_id,
                        task_id=task_id,
                        task_contract=task_contract,
                        changed_files_context=changed_files_context,
                        validation_output=validation_output,
                        provider=provider,
                        model=model,
                        visual_reference_image_path=visual_reference_image_path,
                        visual_actual_image_path=visual_actual_image_path,
                    )
                except Exception as segmented_error:
                    # A free route can fail on one section even when it can
                    # still produce the complete document coherently. Give
                    # the same finite OmniRoute ladder one monolithic recovery
                    # opportunity before returning the blocker to Scrum Master.
                    if provider_name != "omniroute":
                        raise
                    logger.warning(
                        "Segmented visual generation exhausted its ladder; "
                        "trying monolithic visual recovery: %s",
                        segmented_error,
                    )
                    try:
                        return await self._plan_single_visual_repair(
                            project_id=project_id,
                            run_id=run_id,
                            task_id=task_id,
                            task_contract=task_contract,
                            changed_files_context=changed_files_context,
                            validation_output=validation_output,
                            provider=provider,
                            model=model,
                            visual_reference_image_path=visual_reference_image_path,
                            visual_actual_image_path=visual_actual_image_path,
                        )
                    except Exception as monolithic_error:
                        raise LLMError(
                            "Segmented and monolithic visual generation both failed: "
                            f"segmented={segmented_error}; monolithic={monolithic_error}"
                        ) from monolithic_error
            return await self._plan_single_visual_repair(
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                task_contract=task_contract,
                changed_files_context=changed_files_context,
                validation_output=validation_output,
                provider=provider,
                model=model,
                visual_reference_image_path=visual_reference_image_path,
                visual_actual_image_path=visual_actual_image_path,
            )
        bundle = self.bundler.build_bundle(
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            task_contract=task_contract,
            changed_files_context=changed_files_context,
            validation_output=validation_output,
            visual_reference_image_path=visual_reference_image_path,
            visual_actual_image_path=visual_actual_image_path,
        )
        user_content = self.bundler.build_visual_user_content(
            bundle,
            visual_reference_image_path=visual_reference_image_path,
            visual_actual_image_path=visual_actual_image_path,
        )
        required_public_apis = task_contract.get("required_public_apis", [])
        required_api_guidance = ""
        if isinstance(required_public_apis, list) and required_public_apis:
            required_api_guidance = (
                " The task requires these existing public production APIs to remain usable: "
                + ", ".join(str(item) for item in required_public_apis)
                + ". If validation reports one as missing, repair the allowed production file; "
                "never diagnose that failure as a test-adapter issue and never edit a prior "
                "acceptance test."
            )
        messages: list[LLMMessage] = [
            {
                "role": "system",
                "content": (
                    "You are LocalForge Chief Engineer. Economy-first hard repair. "
                    "Return strict JSON with summary, failure_class, actions, risk_notes. "
                    "Return at most one action per call; choose the smallest complete file "
                    "rewrite that can make the failing validation pass. "
                    "A failed validation is never an acceptable no-op: actions must contain "
                    "exactly one concrete repair when the current score is below threshold. "
                    "Actions must use only write_file or append_content. "
                    "Write only paths allowed by task_contract.allowed_files. "
                    + required_api_guidance
                    + " "
                    "Do not edit tests unless the contract explicitly allows that test file. "
                    "If validation reports that the contract's canonical test file is missing, "
                    "create that exact allowed test file with focused, headless acceptance checks "
                    "instead of treating the missing file as an unrecoverable blocker. "
                    "If validation reports ImportError, ModuleNotFoundError, a missing required "
                    "public function, or a missing required production file, repair the allowed "
                    "production module named by task_contract.required_product_files first; "
                    "this is an implementation blocker, not a test-harness defect, and must "
                    "never be fixed by rewriting a valid acceptance test. "
                    "When a task depends on an accepted predecessor implementation, read the "
                    "current production file before editing and preserve every existing public "
                    "API and behavior; extend it in place rather than replacing the file with "
                    "a smaller markup or placeholder implementation. "
                    "Existing acceptance tests are immutable during repair, even when their path "
                    "is listed in allowed_files. Acceptance tests must exercise the generated "
                    "product (by importing its public API, executing its script, or inspecting "
                    "the real artifact); never reimplement the requested algorithm inside the "
                    "test, assert only duplicated constants, or declare success without touching "
                    "the product. If a missing test must be created, make that product linkage "
                    "explicit and keep the test independent of the model's prose. "
                    "For HTML/JavaScript products, never execute JavaScript with Python exec(); "
                    "use Node, a browser harness, or a subprocess that returns structured results. "
                    "If collection or syntax validation identifies a malformed test harness, "
                    "you may repair that exact test as bounded QA maintenance (at most three "
                    "attempts tracked by the runner), but preserve its intended assertions and "
                    "make it execute the real product rather than weakening it. Return the "
                    "complete syntactically valid file, never an append-only fragment, unmatched "
                    "triple-quoted block, unified diff markers (such as @@, --- or +++), "
                    "placeholder, or run-command-only no-op. "
                    "If the validation context explicitly labels a generated test as "
                    "static-only or invented-identifier QA, that one test rewrite is also "
                    "permitted: replace source-string checks with observable behavioral "
                    "checks against the real product, and do not use a test rewrite to hide "
                    "a genuine production failure. "
                    "When pytest has collected a valid existing test and reports assertion "
                    "failures, the test is authoritative: return a production-file action only. "
                    "A repair containing only a test write is invalid; fix the allowed product "
                    "file named by the contract instead. "
                    "If Node reports SyntaxError: Unexpected token '<' while a test calls "
                    "vm.runInContext on an HTML file, repair the test harness to extract the "
                    "script or use a browser/Node HTML harness; never make production code "
                    "accommodate raw HTML passed as JavaScript. "
                    "The same rule applies when a subprocess test passes complete <!DOCTYPE "
                    "html> text to node -e: load the file and extract executable scripts or "
                    "use a browser harness instead of interpolating the document into JS. "
                    "For HTML/CSS visual repairs, return the complete target file content; "
                    "never omit repeated keys, labels, styles, or markup for brevity. "
                    "Keep the complete visual file concise (prefer under 18,000 characters) "
                    "by using compact CSS and JavaScript, but never truncate it. "
                    "Before editing a visual product, preserve every declared interactive control, "
                    "stable locator, row/column position, label, legend, state, and action from "
                    "task_contract.visual_acceptance_matrix. Make targeted visual corrections and "
                    "return the complete target file without omitted controls or placeholder text. "
                    "Fix production code, imports, exports, syntax, and semantics needed for "
                    "the canonical task test to pass. "
                    "For visual tasks, the attached reference image and the explicit visual contract "
                    "are authoritative over conflicting prose. Inspect geometry, materials, colors, "
                    "labels, spacing, interaction states, and responsive behavior before editing. "
                    "Preserve the existing product behavior while making the rendered result converge "
                    "to the declared target. If no reference image exists, use the PRD's visual matrix "
                    "and keep the design coherent, accessible, responsive, and free of invented controls. "
                    "When a matrix declares rows, columns, spans, legends, or colors, implement those "
                    "facts exactly and expose stable locators for browser assertions. Never substitute a "
                    "dashboard, mock, static screenshot, or API-only bridge for the product surface."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        if task_contract.get("visual_required"):
            # The contract, attached reference, and gate metrics carry the
            # task-specific evidence; use the compact visual prompt for the
            # paid call and keep the deterministic gate authoritative.
            messages[0]["content"] = _compact_visual_repair_prompt(task_contract)
        else:
            # Keep ordinary backend, test, and repository repairs on a compact
            # contract-driven prompt so the model spends its budget on the
            # reported failure rather than unrelated visual guidance.
            messages[0]["content"] = (
                "You are LocalForge Chief Engineer. Return strict JSON with "
                "summary, failure_class, actions, and risk_notes. Apply the "
                "smallest complete repair that resolves the reported validation "
                "failure. Return at most one concrete write_file or append_content "
                "action per call. Use only task_contract.allowed_files; do not "
                "invent paths or placeholders. Do not edit tests unless the exact "
                "test file is allowed. If validation says the canonical allowed "
                "test file is missing, create that exact file with focused, "
                "headless acceptance checks that execute or import the generated "
                "product. Existing acceptance tests are immutable during repair. "
                "If validation reports ImportError, ModuleNotFoundError, a missing required "
                "public function, or a missing required production file, create or repair the "
                "allowed production module named by task_contract.required_product_files; "
                "this is an implementation blocker, not a test-harness defect, and do not "
                "rewrite a valid acceptance test to hide it. "
                "Treat required_product_files as exact: when it names app/pulse_board.py, "
                "create that Python module and its contracted functions; never infer or "
                "substitute app/index.html, a metrics module, or an unrelated package. "
                "If task_contract.required_artifact is present and validation reports it "
                "missing or incomplete, create that exact allowed artifact and include every "
                "listed marker; do not treat release evidence as optional and do not return "
                "a product-only no-op. "
                "Never reimplement the requested algorithm inside a test or assert "
                "only duplicated constants; the test must exercise the real artifact. "
                "For HTML/JavaScript products, never execute JavaScript with Python exec(); "
                "use Node, a browser harness, or a subprocess with structured output. "
                "Never use pytest.skip, pytest.xfail, pytest.importorskip, or placeholder "
                "branches to bypass an acceptance behavior; every collected test must execute "
                "real assertions against the generated product. "
                "If pytest collection or syntax is broken, a one-time QA repair of "
                "that test is allowed only to preserve its assertions and connect it "
                "to the generated product. When pytest has collected the existing "
                "test and reports assertion failures, modify production only; except "
                "when the validation context explicitly labels a generated test as "
                "static-only/invented-identifier QA, in which case replace that one "
                "test with real behavioral checks without weakening the task contract. "
                "Preserve existing behavior and keep the generated content complete."
            )
        estimated_input = _estimate_message_tokens(messages)
        estimated_output = 8000 if task_contract.get("visual_required") else 1800
        await self.uow.model_calls.ensure_budget(
            project_id=project_id,
            run_id=run_id,
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
            provider=str(getattr(provider, "provider_name", "omniroute")),
        )
        try:
            from localforge.core.config import load_config

            config = load_config()
            configured_timeout = float(config.chief_engineer.timeout)
            provider_name = str(getattr(provider, "provider_name", "")).lower()
            # OmniRoute is a local gateway, but upstream routes can spend
            # longer in hidden reasoning before emitting a complete
            # structured response. Use an explicit, bounded configuration
            # instead of the former fixed 60-second cap; the model ladder
            # still handles genuine failures.
            timeout = (
                min(configured_timeout, float(config.chief_engineer.omniroute_structured_timeout))
                if provider_name == "omniroute"
                else min(configured_timeout, 240.0)
            )
            # The structured Chief path does not pass through the generic
            # Agent Harness request wrapper. Reuse its operator-facing
            # deadline here so a slow OmniRoute stream cannot hold a task
            # without heartbeat while the outer scheduler waits.
            try:
                harness_timeout = float(
                    os.getenv("LOCALFORGE_AGENT_REQUEST_TIMEOUT", "0")
                )
            except ValueError:
                harness_timeout = 0.0
            if harness_timeout > 0:
                timeout = min(timeout, max(15.0, harness_timeout))
            # OmniRoute free/freemium routes occasionally return an empty or
            # malformed structured payload on the first attempt. Give every
            # non-visual Chief repair one bounded self-correction turn before
            # falling through the finite model ladder; visual repairs already
            # use their own segmented retry policy below.
            validation_retries = 1
        except Exception:
            timeout = 90.0
        try:
            # Free OmniRoute routes can spend part of the budget on hidden
            # reasoning even at ``reasoning_effort=low``. Keep enough room for
            # the complete structured repair plan on every task type.
            output_cap = 6000
            with _structured_output_cap(provider, output_cap):
                plan = await chat_completion_validated(
                    provider=provider,
                    messages=messages,
                    schema_model=ChiefEngineerRepairPlan,
                    model=model,
                    timeout=timeout,
                    max_retries=validation_retries,
                )
            if task_contract.get("visual_required"):
                _validate_visual_repair_plan(plan, task_contract)
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
                    provider=str(getattr(provider, "provider_name", "omniroute")),
                    model=model,
                    reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                    input_tokens=estimated_input,
                    output_tokens=output_tokens,
                    estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, output_tokens),
                    status=status,
                    error_summary=error_summary,
                    metadata=_provider_metadata(provider),
                )
            )
            if (
                task_contract.get("visual_required")
                and (visual_reference_image_path or visual_actual_image_path)
                and _is_visual_capability_mismatch(exc)
                and "vision" not in model.lower()
                and os.getenv("LOCALFORGE_CHIEF_TEXT_FALLBACK_IN_SERVICE", "false").lower()
                == "true"
            ):
                # Some OmniRoute pools expose coding aliases while no current
                # target in that pool is multimodal. Keep the Chief Engineer
                # path authoritative by retrying the same model with the
                # contract, gate metrics, and complete HTML context as text.
                # The deterministic visual gate remains mandatory; this is a
                # transport fallback, never a claim that the model saw pixels.
                fallback_bundle = self.bundler.build_bundle(
                    reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                    task_contract=task_contract,
                    changed_files_context=changed_files_context,
                    validation_output=(
                        validation_output
                        + "\nVisual attachment unavailable in the selected gateway pool. "
                        "Use the visual contract, supplied geometry, current HTML, and gate "
                        "metrics to produce the complete repair file."
                    ),
                    visual_reference_image_path=None,
                    visual_actual_image_path=None,
                )
                fallback_evidence = fallback_bundle.get("visual_evidence")
                if isinstance(fallback_evidence, dict):
                    fallback_evidence["instruction"] = (
                        "No multimodal target was available in the selected gateway pool. "
                        "Use the visual contract, reference geometry, current HTML, and "
                        "validation metrics as the repair authority. The deterministic visual "
                        "gate will independently verify the rendered result."
                    )
                fallback_user_content = self.bundler.build_visual_user_content(
                    fallback_bundle,
                    visual_reference_image_path=None,
                    visual_actual_image_path=None,
                )
                fallback_messages: list[LLMMessage] = [
                    messages[0],
                    {"role": "user", "content": fallback_user_content},
                ]
                fallback_input = _estimate_message_tokens(fallback_messages)
                await self.uow.model_calls.ensure_budget(
                    project_id=project_id,
                    run_id=run_id,
                    estimated_input_tokens=fallback_input,
                    estimated_output_tokens=estimated_output,
                    provider=str(getattr(provider, "provider_name", "omniroute")),
                )
                try:
                    plan = await chat_completion_validated(
                        provider=provider,
                        messages=fallback_messages,
                        schema_model=ChiefEngineerRepairPlan,
                        model=model,
                        timeout=timeout,
                        max_retries=validation_retries,
                    )
                except Exception as fallback_exc:
                    fallback_error = str(fallback_exc)[:500]
                    await self.uow.model_calls.record_call(
                        domain.ModelCallLedger(
                            project_id=project_id,
                            run_id=run_id,
                            task_id=task_id,
                            provider=str(getattr(provider, "provider_name", "omniroute")),
                            model=model,
                            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                            input_tokens=fallback_input,
                            output_tokens=0,
                            estimated_cost_usd=estimate_paid_call_cost_usd(
                                fallback_input, 0
                            ),
                            status="failed",
                            error_summary=fallback_error,
                            metadata={
                                **_provider_metadata(provider),
                                "visual_context_fallback": "text_only",
                            },
                        )
                    )
                    raise LLMError(
                        "Chief Engineer semantic repair failed with visual and text fallbacks: "
                        f"{error_summary}; text fallback: {fallback_error}"
                    ) from fallback_exc
                fallback_output = _estimate_tokens(plan.model_dump_json())
                await self.uow.model_calls.record_call(
                    domain.ModelCallLedger(
                        project_id=project_id,
                        run_id=run_id,
                        task_id=task_id,
                        provider=str(getattr(provider, "provider_name", "omniroute")),
                        model=model,
                        reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                        input_tokens=fallback_input,
                        output_tokens=fallback_output,
                        estimated_cost_usd=estimate_paid_call_cost_usd(
                            fallback_input, fallback_output
                        ),
                        status="success",
                        metadata={
                            **_provider_metadata(provider),
                            "failure_class": plan.failure_class,
                            "actions": len(plan.actions or []),
                            "visual_context_fallback": "text_only",
                        },
                    )
                )
                return plan
            raise LLMError(f"Chief Engineer semantic repair failed: {error_summary}") from exc
        await self.uow.model_calls.record_call(
            domain.ModelCallLedger(
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                provider=str(getattr(provider, "provider_name", "omniroute")),
                model=model,
                reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                input_tokens=estimated_input,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, output_tokens),
                status=status,
                error_summary=error_summary,
                metadata={
                    **_provider_metadata(provider),
                    "failure_class": plan.failure_class,
                    "actions": len(plan.actions or []),
                    "visual_context": (
                        "multimodal"
                        if visual_reference_image_path or visual_actual_image_path
                        else ("text_contract_fallback" if task_contract.get("visual_required") else "text")
                    ),
                },
            )
        )
        return plan

    async def _plan_single_visual_repair(
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
        visual_reference_image_path: str | None,
        visual_actual_image_path: str | None,
    ) -> ChiefEngineerRepairPlan:
        """Request one complete visual product with a finite OmniRoute ladder.

        The Chief Engineer owns the complete HTML/CSS/JS artifact. A single
        structured request preserves cross-file and cross-section consistency;
        the old section assembler remains available only for controlled
        experiments because it is too expensive for unattended free routes.
        """

        assert self.uow.model_calls is not None
        bundle = self.bundler.build_bundle(
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            task_contract=task_contract,
            changed_files_context=changed_files_context,
            validation_output=validation_output,
            visual_reference_image_path=visual_reference_image_path,
            visual_actual_image_path=visual_actual_image_path,
        )
        provider_name = str(getattr(provider, "provider_name", "omniroute")).lower()
        is_omniroute = provider_name == "omniroute"
        if is_omniroute:
            user_content: str | list[dict[str, object]] = _compact_visual_section_context(bundle)
        else:
            user_content = self.bundler.build_visual_user_content(
                bundle,
                visual_reference_image_path=visual_reference_image_path,
                visual_actual_image_path=visual_actual_image_path,
            )
        messages: list[LLMMessage] = [
            {
                "role": "system",
                "content": (
                    _plain_visual_repair_prompt(task_contract)
                    if is_omniroute
                    else _compact_visual_repair_prompt(task_contract)
                    + " Return the complete document in one action now; do not split it into sections."
                ),
            },
            {"role": "user", "content": user_content},
        ]
        estimated_input = _estimate_message_tokens(messages)
        estimated_output = 12000
        # The pipeline commits its state before entering the Chief lane. End
        # any read transaction reopened while building the context so the
        # SQLite-backed budget check cannot inherit a scheduler lock.
        if self.uow.session is not None:
            await self.uow.session.rollback()
        try:
            await asyncio.wait_for(
                self.uow.model_calls.ensure_budget(
                    project_id=project_id,
                    run_id=run_id,
                    estimated_input_tokens=estimated_input,
                    estimated_output_tokens=estimated_output,
                    provider=str(getattr(provider, "provider_name", "omniroute")),
                ),
                timeout=15.0,
            )
        except TimeoutError as exc:
            raise LLMError(
                "Chief Engineer budget check timed out while waiting for the workspace database."
            ) from exc
        try:
            from localforge.core.config import load_config

            configured_timeout = float(load_config().chief_engineer.timeout)
        except Exception:
            configured_timeout = 120.0
        try:
            gateway_timeout = float(os.getenv("LOCALFORGE_VISUAL_REQUEST_TIMEOUT", "90"))
        except ValueError:
            gateway_timeout = 90.0
        timeout = min(max(gateway_timeout, 30.0), configured_timeout, 240.0)
        models = _visual_section_models(provider_name, model)
        failures: list[str] = []
        for attempt, candidate_model in enumerate(dict.fromkeys(models), start=1):
            started_at = monotonic()
            try:
                with _structured_output_cap(provider, 12000):
                    if is_omniroute:
                        raw_response = await asyncio.wait_for(
                            provider.chat_completion(
                                messages=messages,
                                response_schema=None,
                                model=candidate_model,
                                timeout=timeout,
                                stream=False,
                            ),
                            timeout=timeout,
                        )
                        if not isinstance(raw_response, str):
                            raise LLMError(
                                "OmniRoute visual response used an unsupported streaming transport."
                            )
                        document = _extract_visual_document(raw_response)
                        plan = ChiefEngineerRepairPlan.model_validate(
                            {
                                "summary": "Complete visual document generated by OmniRoute",
                                "failure_class": "VISUAL_REPAIR",
                                "actions": [
                                    {
                                        "kind": "write_file",
                                        "path": task_contract.get(
                                            "visual_actual_output", "app/index.html"
                                        ),
                                        "content": document,
                                    }
                                ],
                            }
                        )
                    else:
                        plan = await chat_completion_validated(
                            provider=provider,
                            messages=messages,
                            schema_model=ChiefEngineerRepairPlan,
                            model=candidate_model,
                            timeout=timeout,
                            max_retries=0,
                            # A complete HTML document is one structured payload;
                            # non-streaming avoids waiting on free-route SSE
                            # trailers after the JSON body is already complete.
                            stream=False,
                        )
                _validate_visual_repair_plan(plan, task_contract)
                output_tokens = _estimate_tokens(plan.model_dump_json())
                await self.uow.model_calls.record_call(
                    domain.ModelCallLedger(
                        project_id=project_id,
                        run_id=run_id,
                        task_id=task_id,
                        provider=str(getattr(provider, "provider_name", "omniroute")),
                        model=candidate_model,
                        reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                        input_tokens=estimated_input,
                        output_tokens=output_tokens,
                        estimated_cost_usd=estimate_paid_call_cost_usd(
                            estimated_input, output_tokens
                        ),
                        status="success",
                        duration_ms=max(0, int((monotonic() - started_at) * 1000)),
                        metadata={
                            **_provider_metadata(provider),
                            "visual_generation_mode": "single_document",
                            "visual_transport": "plain_html" if is_omniroute else "structured_json",
                            "requested_visual_model": model,
                            "model_attempt": attempt,
                        },
                    )
                )
                return plan
            except Exception as exc:
                error_summary = str(exc)[:500]
                failures.append(f"{candidate_model}: {error_summary}")
                await self.uow.model_calls.record_call(
                    domain.ModelCallLedger(
                        project_id=project_id,
                        run_id=run_id,
                        task_id=task_id,
                        provider=str(getattr(provider, "provider_name", "omniroute")),
                        model=candidate_model,
                        reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                        input_tokens=estimated_input,
                        output_tokens=0,
                        estimated_cost_usd=estimate_paid_call_cost_usd(estimated_input, 0),
                        status="failed",
                        error_summary=error_summary,
                        duration_ms=max(0, int((monotonic() - started_at) * 1000)),
                        metadata={
                            **_provider_metadata(provider),
                            "visual_generation_mode": "single_document",
                            "visual_transport": "plain_html" if is_omniroute else "structured_json",
                            "requested_visual_model": model,
                            "model_attempt": attempt,
                        },
                    )
                )
                if not _is_transient_gateway_error(exc) and attempt >= len(models):
                    break
        raise LLMError(
            "Chief Engineer single-document visual repair exhausted its finite OmniRoute ladder: "
            + "; ".join(failures)
        )

    async def _plan_segmented_visual_repair(
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
        visual_reference_image_path: str | None,
        visual_actual_image_path: str | None,
    ) -> ChiefEngineerRepairPlan:
        """Generate a complete visual file through bounded, atomic sections.

        Long JSON-wrapped HTML responses are unreliable on free/freemium model
        gateways. CSS, body markup, and executable JavaScript are therefore
        generated independently and assembled only after every section passes
        deterministic validation. No partial document is ever exposed to the
        runtime or written to the task worktree.
        """

        assert self.uow.model_calls is not None
        expected_path = task_contract.get("visual_actual_output")
        if not isinstance(expected_path, str) or not expected_path.strip():
            raise LLMError("Visual task contract is missing visual_actual_output.")

        bundle = self.bundler.build_bundle(
            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
            task_contract=task_contract,
            changed_files_context=changed_files_context,
            validation_output=validation_output,
            visual_reference_image_path=visual_reference_image_path,
            visual_actual_image_path=visual_actual_image_path,
        )
        multimodal_content = self.bundler.build_visual_user_content(
            bundle,
            visual_reference_image_path=visual_reference_image_path,
            visual_actual_image_path=visual_actual_image_path,
        )
        text_content = _compact_visual_section_context(bundle)

        try:
            visual_timeout = float(
                os.getenv("LOCALFORGE_VISUAL_REQUEST_TIMEOUT", "90")
            )
        except ValueError:
            visual_timeout = 90.0

        try:
            from localforge.core.config import load_config

            configured_timeout = float(load_config().chief_engineer.timeout)
            provider_name = str(getattr(provider, "provider_name", "")).lower()
            if provider_name == "omniroute":
                try:
                    gateway_timeout = float(
                        os.getenv("LOCALFORGE_OMNIROUTE_REQUEST_TIMEOUT", "180")
                    )
                except ValueError:
                    gateway_timeout = 180.0
                timeout = max(
                    15.0,
                    min(configured_timeout, visual_timeout, gateway_timeout),
                )
            else:
                timeout = max(15.0, min(configured_timeout, visual_timeout, 240.0))
        except Exception:
            provider_name = str(getattr(provider, "provider_name", "")).lower()
            timeout = 90.0

        section_models = _visual_section_models(provider_name, model)
        section_user_content = text_content if provider_name == "omniroute" else multimodal_content

        # These are finite character ceilings for complete sections. The model
        # output cap is token-based, so valid longer JavaScript must not be
        # silently truncated to fit an older character ceiling.
        section_specs: tuple[tuple[str, int, int, str, str | list[dict[str, Any]]], ...] = (
            (
                "css_reset",
                300,
                6000,
                "Return only CSS for page reset, viewport fit, body sizing, and font smoothing "
                "without <style> tags. Keep the rules complete and contract-safe.",
                section_user_content,
            ),
            (
                "css_frame_container",
                400,
                6000,
                "Return only CSS for the outer product container, page placement, width, "
                "height, and bounded responsive geometry. No <style> tags or unrelated "
                "selectors. Use no more than 12 concise rules.",
                section_user_content,
            ),
            (
                "css_frame_surface",
                300,
                6000,
                "Return only CSS for the outer frame surface: background, radius, borders, "
                "and shadows. No <style> tags or unrelated selectors. Use no more than 12 "
                "concise rules.",
                section_user_content,
            ),
            (
                "css_frame_inner",
                400,
                6000,
                "Return only CSS for the bezel, inner panel, borders, shadows, and material "
                "details of the product frame. No <style> tags or unrelated selectors.",
                section_user_content,
            ),
            (
                "css_display",
                300,
                6000,
                "Return only CSS for the product header, display, indicators, branding, and status "
                "elements. No <style> tags or control-grid rules. Use no more than 12 concise rules.",
                section_user_content,
            ),
            (
                "css_controls_grid",
                400,
                6000,
                "Return only CSS for the declared interactive-control grid, control surfaces, "
                "spans, and grid geometry. No <style> tags or markup wrappers. Use no more than "
                "12 concise rules.",
                section_user_content,
            ),
            (
                "css_controls_labels",
                400,
                6000,
                "Return only CSS for primary labels, secondary legends, shifted keys, hover, "
                "focus, active, and disabled interaction states. No wrapper tags.",
                section_user_content,
            ),
            (
                "css_finish",
                350,
                6000,
                "Return only CSS finishing rules for reference colors, typography, shadows, "
                "compact spacing, and bounded responsive scaling. No wrapper tags. Use no more "
                "than 12 concise rules.",
                section_user_content,
            ),
            (
                "body_shell",
                300,
                4000,
                "Return only inner markup for branding, display, indicators, and status elements. "
                "Do not include body/main/control-grid/style/script wrapper tags. Keep it "
                "compact: at most 18 lines and no repeated controls.",
                section_user_content,
            ),
            (
                "body_controls_1",
                120,
                4800,
                "Return only the first sixth of the contract controls in exact visual order. "
                "Every control must be a direct button child; include legends and data-key "
                "attributes. Do not include a grid/container wrapper or omit repeated keys.",
                section_user_content,
            ),
            (
                "body_controls_2",
                120,
                4800,
                "Return only the second sixth of the contract controls in exact visual order, "
                "continuing after the first sixth. Every control must be a direct button child; "
                "include legends and data-key attributes. No grid/container wrapper.",
                section_user_content,
            ),
            (
                "body_controls_3",
                120,
                4800,
                "Return only the third sixth of the contract controls in exact visual order, "
                "continuing after the second sixth. Every control must be a direct button child; "
                "include legends and data-key attributes. No grid/container wrapper.",
                section_user_content,
            ),
            (
                "body_controls_4",
                120,
                4800,
                "Return only the fourth sixth of the contract controls in exact visual order, "
                "continuing after the third sixth. Every control must be a direct button child; "
                "include legends and data-key attributes. No grid/container wrapper.",
                section_user_content,
            ),
            (
                "body_controls_5",
                120,
                4800,
                "Return only the fifth sixth of the contract controls in exact visual order, "
                "continuing after the fourth sixth. Every control must be a direct button child; "
                "include legends and data-key attributes. No grid/container wrapper.",
                section_user_content,
            ),
            (
                "body_controls_6",
                120,
                4800,
                "Return only the final sixth of the contract controls in exact visual order, "
                "continuing after the fifth sixth through the last control. Every control must "
                "be a direct button child; include legends and data-key attributes. No "
                "grid/container wrapper and no omitted controls.",
                section_user_content,
            ),
            (
                "script_state",
                500,
                12000,
                "Return only executable JavaScript declarations for product state, display "
                "formatting, input helpers, and clear/reset. Do "
                "not add event listeners or wrappers. Every function must be complete; no "
                "stubs, TODOs, or prose.",
                text_content,
            ),
            (
                "script_operations",
                500,
                12000,
                "Return only executable JavaScript for the declared primary actions, state "
                "transitions, calculations, and basic operation dispatch. Reuse the state and helper "
                "names required by the contract; do not redeclare them, add event listeners, "
                "or emit wrappers, stubs, TODOs, or prose.",
                text_content,
            ),
            (
                "script_controls",
                500,
                9000,
                "Return only executable JavaScript for shift handling, key lookup, button and "
                "keyboard event wiring, and dispatch to the preceding helpers. Reuse shared "
                "state names; do not redeclare core operations or emit wrappers, stubs, TODOs, "
                "or prose.",
                text_content,
            ),
            (
                "script_advanced",
                500,
                12000,
                "Return only executable JavaScript that appends the advanced operations and "
                "domain behavior required by this task contract. Reuse the preceding shared "
                "state and dispatch names; no wrappers, "
                "stubs, TODOs, or prose.",
                text_content,
            ),
        )
        sections: dict[str, str] = {}

        async def commit_visual_section_checkpoint() -> None:
            # Each section may wait on a separate OmniRoute response. Commit
            # the call ledger before the next request so SQLite never keeps a
            # writer lock across model latency and visual retries.
            if isinstance(self.uow.session, AsyncSession):
                await self.uow.session.commit()

        for (
            section_name,
            minimum_length,
            maximum_length,
            instruction,
            user_content,
        ) in section_specs:
            control_partition = _visual_control_partition(
                section_name, task_contract.get("visual_acceptance_matrix")
            )
            transport_instruction = (
                "Return only the complete section content, without JSON, prose, or analysis."
                if provider_name == "omniroute"
                else "Return exactly one JSON object with the single string field content."
            )
            messages: list[LLMMessage] = [
                {
                    "role": "system",
                    "content": (
                        "You are LocalForge Chief Engineer building one bounded section of a "
                        "standalone visual software product. "
                        f"{transport_instruction} "
                        "Do not reason, plan, explain, or emit analysis; return the requested "
                        "section immediately. "
                        f"{instruction} The content must contain at least {minimum_length} "
                        f"and at most {maximum_length} characters and must be complete for "
                        "this section."
                    ),
                },
                {"role": "user", "content": user_content},
            ]
            estimated_input = _estimate_message_tokens(messages)
            estimated_output = max(1024, minimum_length // 3)
            result: ChiefEngineerVisualSection | None = None
            last_error: Exception | None = None
            physical_attempt = 0
            for section_model in section_models:
                retries = 1
                for retry_index in range(retries):
                    physical_attempt += 1
                    await self.uow.model_calls.ensure_budget(
                        project_id=project_id,
                        run_id=run_id,
                        estimated_input_tokens=estimated_input,
                        estimated_output_tokens=estimated_output,
                        provider=str(getattr(provider, "provider_name", "omniroute")),
                        model=section_model,
                    )
                    started_at = monotonic()
                    try:
                        section_output_cap = max(
                            1200, min(3500, max(1, maximum_length // 2))
                        )
                        if section_name.startswith("css_"):
                            section_output_cap = min(section_output_cap, 1800)
                        elif section_name == "body_shell":
                            section_output_cap = min(section_output_cap, 1500)
                        with _structured_output_cap(provider, section_output_cap):
                            if provider_name == "omniroute":
                                try:
                                    raw_section = await asyncio.wait_for(
                                        provider.chat_completion(
                                            messages=messages,
                                            response_schema=None,
                                            model=section_model,
                                            timeout=timeout,
                                            stream=False,
                                        ),
                                        timeout=timeout,
                                    )
                                except TimeoutError as exc:
                                    raise LLMTimeoutError(
                                        f"OmniRoute visual section {section_name!r} "
                                        f"timed out after {timeout:.0f}s"
                                    ) from exc
                                if not isinstance(raw_section, str):
                                    raise LLMError(
                                        "OmniRoute visual section returned an unsupported transport."
                                    )
                                candidate = ChiefEngineerVisualSection(
                                    content=_extract_visual_section_content(raw_section)
                                )
                            else:
                                candidate = await chat_completion_validated(
                                    provider=provider,
                                    messages=messages,
                                    schema_model=ChiefEngineerVisualSection,
                                    model=section_model,
                                    timeout=timeout,
                                    max_retries=0,
                                    stream=False,
                                )
                        normalized_content = _normalize_visual_section_content(
                            section_name,
                            candidate.content,
                            control_partition=control_partition,
                        )
                        _validate_visual_section(
                            section_name, normalized_content, minimum_length, maximum_length
                        )
                    except Exception as exc:
                        last_error = exc
                        await self.uow.model_calls.record_call(
                            domain.ModelCallLedger(
                                project_id=project_id,
                                run_id=run_id,
                                task_id=task_id,
                                provider=str(getattr(provider, "provider_name", "omniroute")),
                                model=section_model,
                                reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                                input_tokens=estimated_input,
                                output_tokens=0,
                                estimated_cost_usd=(
                                    0.0
                                    if is_free_gateway_model(section_model)
                                    else estimate_paid_call_cost_usd(estimated_input, 0)
                                ),
                                status="failed",
                                error_summary=str(exc)[:500],
                                duration_ms=max(0, int((monotonic() - started_at) * 1000)),
                                metadata={
                                    **_provider_metadata(provider),
                                    "visual_section": section_name,
                                    "segmented_visual_generation": True,
                                    "requested_visual_model": model,
                                    "section_model_attempt": physical_attempt,
                                    "transient_retry": retry_index,
                                },
                            )
                        )
                        await commit_visual_section_checkpoint()
                        if retry_index + 1 < retries and _is_transient_gateway_error(exc):
                            await asyncio.sleep(2.0)
                            continue
                        break

                    result = candidate
                    output_tokens = _estimate_tokens(result.model_dump_json())
                    await self.uow.model_calls.record_call(
                        domain.ModelCallLedger(
                            project_id=project_id,
                            run_id=run_id,
                            task_id=task_id,
                            provider=str(getattr(provider, "provider_name", "omniroute")),
                            model=section_model,
                            reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN,
                            input_tokens=estimated_input,
                            output_tokens=output_tokens,
                            estimated_cost_usd=(
                                0.0
                                if is_free_gateway_model(section_model)
                                else estimate_paid_call_cost_usd(
                                    estimated_input, output_tokens
                                )
                            ),
                            status="success",
                            duration_ms=max(0, int((monotonic() - started_at) * 1000)),
                            metadata={
                                **_provider_metadata(provider),
                                "visual_section": section_name,
                                "segmented_visual_generation": True,
                                "requested_visual_model": model,
                                "section_model_attempt": physical_attempt,
                            },
                        )
                    )
                    await commit_visual_section_checkpoint()
                    break
                if result is not None:
                    break

            if result is None:
                if section_name.startswith("css_"):
                    # CSS is a replaceable presentation layer. Free routes can
                    # return valid compact rules below the historical size
                    # floor, or fail after a transient gateway response. Keep
                    # the Chief lane autonomous by supplying a complete,
                    # deterministic CSS section; the final visual gate still
                    # validates the assembled document and the declared visual
                    # contract remains authoritative for product geometry.
                    sections[section_name] = _deterministic_visual_css_section(
                        section_name
                    )
                    logger.warning(
                        "Chief Engineer visual section %s exhausted its model ladder; "
                        "using deterministic CSS fallback.",
                        section_name,
                    )
                    continue
                raise LLMError(
                    f"Chief Engineer visual section {section_name!r} exhausted its model "
                    f"ladder: {last_error}"
                ) from last_error
            sections[section_name] = _normalize_visual_section_content(
                section_name,
                result.content,
                control_partition=control_partition,
            )

        controls_content = "\n".join(
            sections[f"body_controls_{index}"] for index in range(1, 7)
        )
        script_content = (
            f"{sections['script_state']}\n{sections['script_operations']}\n"
            f"{sections['script_controls']}\n{sections['script_advanced']}"
        )
        complete_html = (
            "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
            "<meta charset=\"UTF-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>LocalForge Visual Product</title>\n<style>\n"
            f"{sections['css_reset']}\n{sections['css_frame_container']}\n"
            f"{sections['css_frame_surface']}\n"
            f"{sections['css_frame_inner']}\n"
            f"{sections['css_display']}\n{sections['css_controls_grid']}\n"
            f"{sections['css_controls_labels']}\n{sections['css_finish']}\n"
            "</style>\n</head>\n<body>\n"
            "<main class=\"calculator-shell\">\n"
            f"{sections['body_shell']}\n<section class=\"key-grid\">\n"
            f"{controls_content}\n"
            "</section>\n</main>\n<script>\n"
            f"{script_content}\n</script>\n"
            "<style id=\"localforge-visual-contract-overrides\">\n"
            f"{_deterministic_visual_overrides()}\n"
            "</style>\n"
            "</body>\n</html>\n"
        )
        plan = ChiefEngineerRepairPlan(
            summary="Assembled complete visual product from validated bounded sections.",
            failure_class="VISUAL_MISMATCH",
            actions=[
                ChiefEngineerRepairAction(
                    kind="write_file", path=expected_path, content=complete_html
                )
            ],
            risk_notes=[
                "The assembled document must pass deterministic syntax, behavior, and visual gates."
            ],
        )
        _validate_visual_repair_plan(plan, task_contract)
        return plan


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _compact_visual_repair_prompt(task_contract: dict[str, object]) -> str:
    rules = task_contract.get("visual_structure_rules", [])
    rule_items = rules if isinstance(rules, list) else []
    rule_text = ", ".join(item for item in rule_items if isinstance(item, str))
    guidance = {
        "single_product_surface": "render one coherent product surface rather than a test stub or dashboard substitute",
        "stable_interactive_locators": "give every declared interactive element a stable semantic locator and keyboard-accessible state",
        "declared_visual_matrix": "materialize every row, column, label, legend, color, span, and action declared by the visual matrix",
        "responsive_reference_convergence": (
            "match the declared reference geometry at the contract viewport and "
            "verify responsive behavior without inventing controls"
        ),
    }
    guidance_text = " ".join(
        guidance[item]
        for item in rule_items
        if isinstance(item, str) and item in guidance
    )
    return (
        "You are LocalForge Chief Engineer. Return only one valid JSON object with "
        "summary, failure_class, actions, and risk_notes. actions must be a non-empty "
        "array containing exactly one concrete action. The action kind must be "
        "write_file, and its path must be in task_contract.allowed_files. Never use "
        "append_content for a visual HTML task. The action content must be the complete "
        "target file, not a patch, snippet, CSS-only override, or explanation. For an "
        "HTML target, the content must be at least 6000 characters and must include a "
        "complete executable product, not just the minimum document shell. "
        "For a visual task, the attached reference image is authoritative. Preserve all "
        "existing behavior and controls; never use placeholders, truncation, or commentary. "
        "If the target file is missing, create a complete compact standalone HTML/CSS/JS "
        "implementation with doctype, html/body, styles, executable script, and real controls. "
        "The HTML must include the complete rendered product surface, visible interactive "
        "controls, declared states, and executable behavior; do not return a short style patch. "
        "Use the validation output, current-file context, contract, reference image, and "
        "gate metrics in the user message. The deterministic visual gate decides acceptance. "
        f"Required structure rules: {rule_text or 'follow the reference image and contract'}. "
        f"Concrete guidance: {guidance_text or 'follow the reference image and contract'}."
    )


def _validate_visual_repair_plan(
    plan: ChiefEngineerRepairPlan, task_contract: dict[str, object]
) -> None:
    """Reject non-material visual patches before they consume a gate attempt."""
    action = plan.actions[0]
    expected_path = task_contract.get("visual_actual_output")
    if action.kind != "write_file":
        raise ValueError("Visual repair must use a complete write_file action.")
    if isinstance(expected_path, str) and action.path != expected_path:
        raise ValueError(
            "Visual repair must write the contract visual_actual_output path "
            f"{expected_path!r}."
        )
    content = action.content
    if len(content) < 6000:
        raise ValueError(
            "Visual HTML repair is too small to be a complete product file; "
            "return the full implementation instead of a style patch."
        )
    lowered = content.lower()
    required_markers = ("<html", "<body", "<style", "<script")
    missing = [marker for marker in required_markers if marker not in lowered]
    if missing:
        raise ValueError(
            "Visual HTML repair is missing required standalone document sections: "
            + ", ".join(missing)
        )


def _extract_visual_document(raw_content: str) -> str:
    """Extract one complete HTML document from a permissive gateway response.

    Free OmniRoute coding routes often return a short explanation or a fenced
    code block even when the prompt requests source only. That transport noise
    is safe to remove deterministically; the visual contract still validates
    the resulting document before it can reach the worktree.
    """
    content = raw_content.strip()
    fenced = re.search(
        r"```(?:html)?\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE
    )
    if fenced:
        content = fenced.group(1).strip()
    lowered = content.lower()
    starts = [
        index
        for marker in ("<!doctype html", "<html")
        if (index := lowered.find(marker)) >= 0
    ]
    if not starts:
        raise ValueError("OmniRoute visual response did not contain an HTML document.")
    content = content[min(starts) :].strip()
    end = content.lower().rfind("</html>")
    if end < 0:
        raise ValueError("OmniRoute visual response contained an incomplete HTML document.")
    return content[: end + len("</html>")].strip()


def _plain_visual_repair_prompt(task_contract: dict[str, object]) -> str:
    """Build a source-first prompt for OmniRoute coding aliases."""
    allowed = task_contract.get("allowed_files", [])
    output = task_contract.get("visual_actual_output", "app/index.html")
    return (
        "You are the Chief Engineer in ForgeOS Cloud. Return only one complete, "
        "standalone HTML document as source code, optionally inside one html code "
        "fence. Do not return JSON, prose, a patch, a placeholder, or an omitted "
        "section. Write the complete executable product for the target file "
        f"{output!r}; the only allowed files are {allowed!r}. Preserve existing "
        "behavior when present. The document must include doctype, html, body, "
        "CSS, executable JavaScript, the complete product surface, visible controls, "
        "and real behavior required by the PRD. "
        "The reference image and visual contract are authoritative. Keep the "
        "document between 6000 and 9000 characters and compact enough for one "
        "response while remaining complete for the deterministic gates."
    )


def _validate_visual_section(
    name: str, content: str, minimum_length: int, maximum_length: int
) -> None:
    stripped = content.strip()
    if len(stripped) < minimum_length:
        raise ValueError(
            f"Visual {name} section is too small ({len(stripped)} characters); "
            f"expected at least {minimum_length}."
        )
    if len(stripped) > maximum_length:
        raise ValueError(
            f"Visual {name} section is too large ({len(stripped)} characters); "
            f"expected at most {maximum_length}."
        )
    lowered = stripped.lower()
    omission_markers: tuple[str, ...] = (
        "omitted for brevity",
        "remaining code",
        "rest of the file",
        "todo: implement",
        "add more here",
    )
    if not name.startswith("css_"):
        omission_markers += ("placeholder",)
    marker = next((item for item in omission_markers if item in lowered), None)
    if marker:
        raise ValueError(f"Visual {name} section contains omission marker {marker!r}.")
    section_kind = name.split("_", 1)[0]
    forbidden_tags = {
        "css": ("<style", "</style"),
        "body": ("<html", "</html", "<body", "</body", "<style", "<script"),
        "script": ("<script", "</script"),
    }
    invalid_tag = next(
        (tag for tag in forbidden_tags.get(section_kind, ()) if tag in lowered), None
    )
    if invalid_tag:
        raise ValueError(
            f"Visual {name} section must not include wrapper tag {invalid_tag!r}."
        )


def _extract_visual_section_content(raw_content: str) -> str:
    """Remove only transport wrappers from an OmniRoute plain-text section."""
    content = raw_content.strip()
    try:
        parsed = json.loads(content, strict=False)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("content"), str):
        return parsed["content"]
    fenced = re.search(
        r"```(?:css|html|javascript|js)?\s*(.*?)\s*```",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        return fenced.group(1).strip()
    if content.startswith("{") or content.startswith("["):
        raise ValueError("OmniRoute visual section returned malformed JSON transport.")
    return content


def _visual_control_partition(
    name: str, visual_acceptance_matrix: object
) -> tuple[int, int] | None:
    """Return the expected button interval for a declared visual matrix."""
    if not name.startswith("body_controls_") or not isinstance(
        visual_acceptance_matrix, list
    ):
        return None
    entries = visual_acceptance_matrix
    if not entries or not all(isinstance(entry, dict) for entry in entries):
        return None
    control_fields = {
        "locator",
        "row",
        "column",
        "label",
        "labels",
        "primary_label",
        "secondary_label",
        "action",
    }
    if not any(control_fields.intersection(entry) for entry in entries):
        return None
    try:
        section_index = int(name.rsplit("_", 1)[1]) - 1
    except (IndexError, ValueError):
        return None
    if not 0 <= section_index < 6:
        return None
    section_size = (len(entries) + 5) // 6
    start = section_index * section_size
    return start, min(len(entries), start + section_size)


def _normalize_visual_section_content(
    name: str,
    content: str,
    *,
    control_partition: tuple[int, int] | None = None,
) -> str:
    """Remove harmless response wrappers before validating a bounded section."""
    normalized = content.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 2:
            normalized = "\n".join(lines[1:-1]).strip()

    # Coding aliases occasionally return the whole HTML document even when a
    # bounded section was requested. Extract the requested body fragment
    # before validation so a valid response cannot duplicate the keypad or
    # scripts during deterministic assembly.
    if name == "body_shell":
        body_match = re.search(
            r"<body\b[^>]*>(.*?)</body>", normalized, re.IGNORECASE | re.DOTALL
        )
        if body_match:
            normalized = body_match.group(1).strip()
        main_match = re.search(r"<main\b[^>]*>", normalized, re.IGNORECASE)
        if main_match:
            inner = normalized[main_match.end() :]
            cut_positions = [
                match.start()
                for pattern in (
                    r"<section\b[^>]*\bkey-grid\b[^>]*>",
                    r"<div\b[^>]*\bkey-grid\b[^>]*>",
                    r"<button\b",
                )
                if (match := re.search(pattern, inner, re.IGNORECASE)) is not None
            ]
            if cut_positions:
                normalized = inner[: min(cut_positions)].strip()

    if name.startswith("body_controls_"):
        buttons = re.findall(
            r"<button\b[^>]*>.*?</button>", normalized, re.IGNORECASE | re.DOTALL
        )
        # A declared matrix gives each section a stable interval even when a
        # model ignores the sixth instruction and returns every control.
        if control_partition is not None:
            start, end = control_partition
            expected_count = max(0, end - start)
            if len(buttons) > expected_count:
                normalized = "\n".join(buttons[start:end]).strip()
        # Without a matrix, preserve the historical content-driven fallback.
        elif len(buttons) > 16:
            sixth = (len(buttons) + 5) // 6
            sixth_index = int(name.rsplit("_", 1)[1]) - 1
            start = sixth_index * sixth
            normalized = "\n".join(buttons[start : start + sixth]).strip()
        elif buttons and any(
            marker in normalized.lower()
            for marker in ("<main", "<section", "<div", "<html", "<body")
        ):
            normalized = "\n".join(buttons).strip()

    # Providers sometimes emit only the opening wrapper before truncating the
    # response. These tags are transport noise for a bounded section, so strip
    # them independently at the edges instead of rejecting otherwise usable
    # content because the closing tag is missing.
    wrapper: tuple[str, str] | None = None
    if name.startswith("script_"):
        wrapper = ("script", "script")
    elif name.startswith("css_"):
        wrapper = ("style", "style")
    elif name.startswith("body"):
        wrapper = ("body", "body")
    if wrapper is not None:
        tag, closing_tag = wrapper
        normalized = re.sub(
            rf"^\s*<{tag}\b[^>]*>\s*",
            "",
            normalized,
            count=1,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            rf"\s*</{closing_tag}>\s*$",
            "",
            normalized,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
    return normalized


def _deterministic_visual_finish_css() -> str:
    """Return a minimal safe polish layer when a free route is unavailable."""
    return (
        ":root{color-scheme:dark;font-synthesis:none;}\n"
        "*,*::before,*::after{box-sizing:border-box;}\n"
        "html,body{min-height:100%;margin:0;}\n"
        "body{overflow:auto;text-rendering:optimizeLegibility;}\n"
        "button{font:inherit;cursor:pointer;transition:filter .12s ease,transform .12s ease;}\n"
        "button:hover{filter:brightness(1.08);}\n"
        "button:active{transform:translateY(1px);}\n"
        "button:focus-visible{outline:2px solid #d9a441;outline-offset:2px;}\n"
        "@media (max-width:760px){.calculator-shell{max-width:100%;width:100%;}}"
    )


def _deterministic_visual_css_section(name: str) -> str:
    """Return a complete CSS fallback for one bounded visual section.

    The model remains authoritative for valid sections, but a compact CSS
    response is not a product failure. These fallbacks keep the visual repair
    lane self-healing when a free route returns a short or transiently invalid
    section; the final declared visual contract remains the geometry authority.
    """
    sections = {
        "css_reset": (
            ":root{color-scheme:dark;font-synthesis:none;text-rendering:optimizeLegibility;}\n"
            "*,*::before,*::after{box-sizing:border-box;}\n"
            "html,body{width:100%;min-height:100%;margin:0;padding:0;}\n"
            "body{overflow:auto;background:#d5d5d0;color:#f4f4f0;font-family:Arial,sans-serif;}\n"
            "button,input,select,textarea{font:inherit;}\n"
            "button{cursor:pointer;touch-action:manipulation;}\n"
            "button:focus-visible{outline:2px solid #d9a441;outline-offset:2px;}"
        ),
        "css_frame_container": (
            ".calculator-shell{position:relative;width:calc(100vw - 40px);"
            "height:calc(100vh - 20px);max-width:none;min-height:420px;"
            "display:grid;grid-template-rows:auto auto auto 1fr;gap:10px;"
            "padding:12px 16px;overflow:hidden;}\n"
            ".calculator-shell>*{min-width:0;}\n"
            ".calculator-shell:focus-within{outline:1px solid rgba(217,164,65,.65);"
            "outline-offset:3px;}\n"
            ".calculator-shell .key-grid{width:100%;align-self:stretch;}\n"
            "@media(max-width:760px){.calculator-shell{width:96vw;height:96vh;"
            "min-height:360px;padding:9px;gap:5px;}}"
        ),
        "css_frame_surface": (
            ".calculator-shell{background:linear-gradient(145deg,#deded9,#a4a4a0);"
            "border:8px solid #292929;border-radius:5px;"
            "box-shadow:0 10px 22px rgba(0,0,0,.45),inset 0 0 0 2px #f4f4ef;}\n"
            ".calculator-shell::before{content:\"\";position:absolute;inset:0;"
            "pointer-events:none;border:1px solid rgba(255,255,255,.22);}\n"
            "@media(max-width:760px){.calculator-shell{border-width:4px;}}"
        ),
        "css_frame_inner": (
            ".calculator-branding{display:flex;align-items:center;justify-content:space-between;"
            "min-height:58px;padding:0 12px;color:#171717;background:#efefeb;"
            "border:1px solid #8b8b86;box-shadow:inset 0 1px #fff;}\n"
            ".calculator-branding .brand-badge{font-weight:700;font-size:18px;"
            "letter-spacing:.02em;color:#171717;}\n"
            ".calculator-branding .model-badge{font-size:15px;font-weight:600;"
            "color:#171717;}\n"
            ".key-grid{min-height:0;border:3px solid #151515;box-shadow:"
            "inset 0 0 0 2px #555,0 3px 8px rgba(0,0,0,.4);}\n"
            ".calculator-shell{isolation:isolate;}"
        ),
        "css_display": (
            ".lcd-display{display:flex;align-items:center;justify-self:center;width:54%;"
            "min-height:64px;padding:10px 22px;background:#a8ad88;border:3px solid #777b62;"
            "border-radius:8px;color:#111;box-shadow:inset 0 3px 8px rgba(0,0,0,.35);}\n"
            ".lcd-glass{width:100%;font-family:Consolas,monospace;text-align:left;}\n"
            ".lcd-row-main{font-size:clamp(22px,4vw,44px);letter-spacing:.12em;text-align:center;}\n"
            ".lcd-row-indicators{display:flex;gap:12px;font-size:11px;font-weight:700;}"
        ),
        "css_controls_grid": (
            ".key-grid{display:grid;grid-template-columns:repeat(10,minmax(0,1fr));"
            "grid-template-rows:repeat(4,minmax(0,1fr));gap:7px;padding:4px;background:#282828;}\n"
            ".key-grid>.key,.key-grid>.key-enter,.key-grid>.key-op{position:relative;"
            "display:flex;min-width:0;min-height:0;flex-direction:column;"
            "align-items:center;justify-content:center;padding:3px;border:2px solid #141414;"
            "border-radius:4px;background:linear-gradient(#4a4a4a,#222);color:#f0f0ed;"
            "font-size:clamp(10px,1.3vw,17px);font-weight:700;}\n"
            ".key-grid>.key-enter{grid-row:3 / 5;grid-column:6;}"
        ),
        "css_controls_labels": (
            ".key-label-main{display:block;line-height:1.1;text-align:center;}\n"
            ".key-label-shift{display:block;min-height:11px;color:#e07a5f;"
            "font-size:clamp(7px,.8vw,11px);font-weight:600;line-height:1;text-align:center;}\n"
            ".key-grid>.key:hover,.key-grid>.key-op:hover,.key-grid>.key-enter:hover{"
            "filter:brightness(1.18);}\n"
            ".key-grid>.key:active,.key-grid>.key-op:active,.key-grid>.key-enter:active{"
            "transform:translateY(1px);box-shadow:inset 0 2px 4px rgba(0,0,0,.7);}\n"
            ".key-grid>[data-key=f]{background:#f36a36;color:#171717;}"
            ".key-grid>[data-key=g]{background:#0497d5;color:#171717;}"
        ),
        "css_finish": _deterministic_visual_finish_css(),
    }
    return sections.get(name, _deterministic_visual_finish_css())


def _deterministic_visual_overrides() -> str:
    """Keep an assembled visual product coherent across model outputs."""
    return (
        "html,body{width:100%;height:100%;margin:0;overflow:hidden;}\n"
        "body{display:grid;place-items:center;background:#d5d5d0;color:#f4f4f0;font-family:Arial,sans-serif;}\n"
        ".calculator-shell{width:calc(100vw - 40px);height:calc(100vh - 20px);"
        "max-width:none;box-sizing:border-box;display:grid;grid-template-rows:auto auto "
        "auto 1fr;gap:10px;padding:12px 16px;background:linear-gradient(145deg,#deded9,"
        "#a4a4a0);border:8px solid #292929;border-radius:5px;box-shadow:0 10px 22px "
        "rgba(0,0,0,.45),inset 0 0 0 2px #f4f4ef;}\n"
        ".calculator-branding{display:flex;align-items:center;justify-content:space-between;"
        "min-height:58px;padding:0 12px;color:#171717;background:#efefeb;"
        "border:1px solid #8b8b86;}\n"
        ".brand-badge{font-weight:700;font-size:18px;letter-spacing:.02em;color:#171717;background:transparent;}\n"
        ".model-badge{font-size:15px;font-weight:600;color:#171717;}\n"
        ".lcd-display{display:flex;align-items:center;justify-self:center;width:54%;"
        "min-height:64px;padding:10px 22px;background:#a8ad88;border:3px solid #777b62;"
        "border-radius:8px;color:#111;box-shadow:inset 0 3px 8px rgba(0,0,0,.35);}\n"
        ".lcd-glass{width:100%;font-family:Consolas,monospace;text-align:left;}\n"
        ".lcd-row-main{font-size:clamp(22px,4vw,44px);letter-spacing:.12em;text-align:center;}\n"
        ".lcd-row-indicators{display:flex;gap:12px;font-size:11px;font-weight:700;letter-spacing:.03em;}\n"
        ".status-bar{display:flex;gap:14px;min-height:16px;padding:0 4px;color:#c8c8c0;font-size:11px;}\n"
        ".key-grid{display:grid;grid-template-columns:repeat(10,minmax(0,1fr));grid-template-rows:repeat(4,minmax(0,1fr));gap:7px;min-height:0;padding:4px;background:#282828;}\n"
        ".key-grid>.key,.key-grid>.key-enter,.key-grid>.key-op{position:relative;display:flex;"
        "min-width:0;min-height:0;flex-direction:column;align-items:center;"
        "justify-content:center;padding:3px;border:2px solid #141414;border-radius:4px;"
        "background:linear-gradient(#4a4a4a,#222);color:#f0f0ed;font-size:clamp(10px,1.3vw,17px);"
        "font-weight:700;box-shadow:0 2px 3px rgba(0,0,0,.55),inset 0 1px "
        "rgba(255,255,255,.16);}\n"
        ".key-grid>.key-op{background:linear-gradient(#555,#2b2b2b);}\n"
        ".key-grid>.key-enter{grid-row:3 / 5;grid-column:6;background:linear-gradient(#5b5b5b,#303030);font-size:12px;letter-spacing:.12em;}\n"
        ".key-label-main{line-height:1.1;}.key-label-shift{min-height:11px;color:#e07a5f;font-size:clamp(7px,.8vw,11px);font-weight:600;line-height:1;}\n"
        ".key-grid>.key:hover,.key-grid>.key-op:hover,.key-grid>.key-enter:hover{filter:brightness(1.18);}\n"
        ".key-grid>.key:active,.key-grid>.key-op:active,.key-grid>.key-enter:active{transform:translateY(1px);box-shadow:inset 0 2px 4px rgba(0,0,0,.7);}\n"
        ".key-grid>[data-key=f]{background:#f36a36;color:#171717;}.key-grid>[data-key=g]{background:#0497d5;color:#171717;}\n"
        "@media(max-width:760px){.calculator-shell{width:96vw;padding:9px;border-width:4px;"
        "gap:5px;}.key-grid{gap:3px;padding:2px;}.lcd-display{min-height:58px;"
        "padding:6px 10px;}.lcd-row-indicators{gap:4px;font-size:8px;}"
        ".status-bar{gap:6px;font-size:8px;}}"
    )


def _visual_section_models(provider_name: str, requested_model: str) -> list[str]:
    """Route bounded source generation away from unstable OmniRoute vision pools.

    The reference image is still consumed by deterministic normalization and
    the final visual gate. OmniRoute coding aliases receive the resulting
    contract, geometry rules, and gate metrics and are materially faster for
    long CSS/HTML/JavaScript output than its free multimodal aliases.
    """

    if provider_name != "omniroute":
        return [requested_model]
    replacements = (
        ("pro-vision", "best-free"),
        ("best-vision", "best-free"),
        ("multimodal", "best-free"),
        ("vision", "best-free"),
    )
    for source, target in replacements:
        if source in requested_model:
            preferred = requested_model.replace(source, target)
            break
    else:
        preferred = requested_model
    # Visual sections are bounded code-generation calls. Keep the Chief role
    # authoritative while deriving the finite ladder from the workspace's
    # current OmniRoute configuration. The benchmark and the server-owned
    # discovery path can replace this list with routes verified in the live
    # catalog; this helper must not reintroduce stale provider aliases.
    configured_routes: list[str] = []
    try:
        from localforge.core.config import configured_free_gateway_models, load_config

        config = load_config()
        configured_routes.extend(configured_free_gateway_models(config))
    except Exception:
        # Keep the pure normalization helper usable in minimal/unit-test
        # environments where a workspace config is intentionally absent.
        configured_routes = []

    verified_routes = [
        item.strip()
        for item in os.getenv("LOCALFORGE_CLOUD_VERIFIED_ROUTES", "").split(",")
        if item.strip()
    ]
    free_routes = list(dict.fromkeys(configured_routes))
    if not free_routes:
        free_routes = ["auto/best-free"]
    ladder = [preferred, *verified_routes, *free_routes]
    return list(dict.fromkeys(ladder))


def _is_transient_gateway_error(error: Exception) -> bool:
    if isinstance(error, (LLMConnectionError, LLMTimeoutError)):
        return True
    if isinstance(error, LLMHTTPError):
        return error.status_code == 429 or error.status_code >= 500
    message = str(error).lower()
    return any(
        marker in message
        for marker in ("rate_limit", "rate limit", "http 429", "timeout", "temporarily unavailable")
    )


def _compact_visual_section_context(bundle: dict[str, object]) -> str:
    """Bound section prompts so freemium routes are not saturated by a full file."""
    context = bundle.get("changed_files_context", "")
    context_text = context if isinstance(context, str) else str(context)
    if len(context_text) > 3000:
        context_text = context_text[:1500] + "\n...\n" + context_text[-1500:]
    validation = bundle.get("validation_output", "")
    validation_text = validation if isinstance(validation, str) else str(validation)
    raw_contract = bundle.get("task_contract", {})
    contract = raw_contract if isinstance(raw_contract, dict) else {}
    visual_keys = (
        "task_title",
        "visual_required",
        "visual_reference_image",
        "visual_actual_output",
        "visual_similarity_threshold",
        "visual_viewport",
        "visual_structure_rules",
        "visual_acceptance_matrix",
        "visual_acceptance_contract_version",
        "implementation_notes",
        "required_public_apis",
    )
    visual_contract = {key: contract[key] for key in visual_keys if key in contract}
    compact = {
        "reason": bundle.get("reason"),
        "task_contract": visual_contract,
        "validation_output": validation_text[:1000],
        "current_file_edges": context_text,
        "visual_evidence": bundle.get("visual_evidence", {}),
    }
    serialized = json.dumps(compact, sort_keys=True)
    return serialized if len(serialized) <= 12000 else serialized[:12000]


def _is_visual_capability_mismatch(error: Exception) -> bool:
    message = str(error).lower()
    return "capability_mismatch" in message or "confirmed vision support" in message


def _estimate_message_tokens(messages: list[LLMMessage]) -> int:
    """Estimate text and multimodal input without counting base64 as text.

    Image data URLs are transport encoding, not proportional text tokens. Count
    each attached image as a conservative fixed visual budget instead of
    charging the full base64 payload against the per-run paid-input ceiling.
    """

    def compact(value: object) -> object:
        if isinstance(value, list):
            return [compact(item) for item in value]
        if isinstance(value, dict):
            if "image_url" in value:
                return {"image_url": "[IMAGE_ATTACHMENT]"}
            return {str(key): compact(item) for key, item in value.items()}
        return value

    text_tokens = _estimate_tokens(json.dumps(compact(messages), sort_keys=True))
    image_count = sum(
        1
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and "image_url" in block
    )
    return text_tokens + image_count * 2048


def _provider_metadata(provider: BaseLLMProvider) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if hasattr(provider, "primary_provider_name"):
        metadata["primary_provider"] = str(provider.primary_provider_name)
        metadata["fallback_provider"] = str(getattr(provider, "fallback_provider_name", ""))
        metadata["used_fallback"] = bool(getattr(provider, "used_fallback", False))
        failure_reason = getattr(provider, "primary_failure_reason", None)
        if isinstance(failure_reason, str) and failure_reason:
            metadata["primary_failure_reason"] = str(failure_reason)[:240]
        selected = (
            getattr(provider, "fallback", None)
            if bool(getattr(provider, "used_fallback", False))
            else getattr(provider, "primary", None)
        )
    else:
        selected = provider
    pricing = getattr(selected, "model_pricing", None)
    selected_model = getattr(selected, "default_model", None)
    if isinstance(pricing, dict) and isinstance(selected_model, str):
        selected_prices = pricing.get(selected_model)
        if isinstance(selected_prices, dict):
            input_price = selected_prices.get("input_per_million")
            output_price = selected_prices.get("output_per_million")
            if isinstance(input_price, (int, float)) and isinstance(output_price, (int, float)):
                metadata["pricing_input_per_million"] = float(input_price)
                metadata["pricing_output_per_million"] = float(output_price)
                metadata["pricing_measurement_source"] = "PROVIDER_CATALOG"
    return metadata


@contextmanager
def _structured_output_cap(provider: BaseLLMProvider, maximum: int):
    """Bound one structured call without changing the provider configuration."""
    attribute = "default_max_output_tokens"
    previous = getattr(provider, attribute, None)
    if isinstance(previous, int) and previous > 0 and maximum > 0:
        setattr(provider, attribute, min(previous, maximum))
    try:
        yield
    finally:
        if isinstance(previous, int):
            setattr(provider, attribute, previous)
