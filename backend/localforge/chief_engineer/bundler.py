import base64
import io
import json
import logging
import os
import re
from typing import Any

from localforge.models.enums import ChiefEngineerCallReason

logger = logging.getLogger(__name__)


class EconomyPromptBundler:
    """
    Builds context bundles for Chief Engineer API calls.
    Enforces economy-first principles:
    - Context bundle builder per reason code.
    - Token budget previews before paid calls.
    - File snippet selection by relevance.
    - Diff and error compression with hashes.
    - Redaction checks before sending API context.
    """

    def __init__(self, max_file_chars: int = 2000):
        self.max_file_chars = max_file_chars

    def redact_sensitive_info(self, text: str) -> str:
        """Replace API keys, passwords, and other credentials with [REDACTED]."""
        if not text:
            return ""
        # Redact OpenRouter / OpenAI API keys (e.g. sk-or-v1-..., sk-...)
        text = re.sub(r"sk-[a-zA-Z0-9-]{12,}", "[REDACTED_API_KEY]", text)
        # Redact generic api_key assignments
        text = re.sub(
            r"(api[-_]?key\s*=\s*['\"])[^'\"]+(['\"])",
            r"\1[REDACTED_API_KEY]\2",
            text,
            flags=re.IGNORECASE,
        )
        # Redact password assignments
        text = re.sub(
            r"(password\s*=\s*['\"])[^'\"]+(['\"])",
            r"\1[REDACTED_PASSWORD]\2",
            text,
            flags=re.IGNORECASE,
        )
        # Redact token assignments
        text = re.sub(
            r"(token\s*=\s*['\"])[^'\"]+(['\"])", r"\1[REDACTED_TOKEN]\2", text, flags=re.IGNORECASE
        )
        return text

    def compress_diff_and_errors(self, text: str, max_chars: int = 3000) -> str:
        """Compress repetitive stack traces or huge outputs."""
        if not text:
            return ""
        if len(text) <= max_chars:
            return text

        # Truncate repetitiveness inside tracebacks
        lines = text.splitlines()
        compressed_lines = []
        repeat_count = 0
        last_line = ""

        for line in lines:
            # Simple deduplication of identical adjacent lines (often happens in loops/failures)
            if line == last_line and len(line) > 10:
                repeat_count += 1
                if repeat_count > 3:
                    continue
            else:
                if repeat_count > 3:
                    compressed_lines.append(f"... [repeated {repeat_count - 3} times] ...")
                repeat_count = 0
                last_line = line
            compressed_lines.append(line)

        if repeat_count > 3:
            compressed_lines.append(f"... [repeated {repeat_count - 3} times] ...")

        compressed = "\n".join(compressed_lines)
        if len(compressed) > max_chars:
            half = max_chars // 2
            return (
                compressed[:half]
                + f"\n... [TRUNCATED {len(compressed) - max_chars} CHARS] ...\n"
                + compressed[-half:]
            )
        return compressed

    def select_relevant_snippets(self, file_path: str, content: str, error_output: str) -> str:
        """Select relevant lines around errors if file is too large."""
        if not content:
            return ""
        if len(content) <= self.max_file_chars:
            return content

        # Look for file references in the error output
        # E.g. "file_path", line 123
        basename = re.escape(file_path.split("/")[-1])
        line_matches = re.findall(rf"{basename}\",\s*line\s*(\d+)", error_output, re.IGNORECASE)

        target_lines = set()
        for lm in line_matches:
            try:
                target_lines.add(int(lm))
            except ValueError:
                pass

        if not target_lines:
            # Fallback to first part of the file
            half_limit = self.max_file_chars // 2
            return (
                content[:half_limit]
                + "\n\n... [MIDDLE OF FILE OMITTED FOR BREVITY] ...\n\n"
                + content[-half_limit:]
            )

        # Extract segments around target lines
        lines = content.splitlines()
        n = len(lines)
        snippets = []

        # Sort targets
        sorted_targets = sorted(list(target_lines))
        last_end = 0

        for target in sorted_targets:
            # range is 1-indexed in error outputs
            target_idx = target - 1
            if target_idx < 0 or target_idx >= n:
                continue

            start = max(0, target_idx - 15)
            end = min(n, target_idx + 15)

            if start > last_end:
                if last_end > 0:
                    snippets.append("...")
                # Add headers/class definitions if we skipped code
                if start > 5:
                    # Look for class or def statements in the skipped part to keep semantic context
                    for i in range(max(0, start - 50), start):
                        if lines[i].strip().startswith(("class ", "def ")):
                            snippets.append(f"Line {i + 1}: {lines[i]}")

            for i in range(start, end):
                snippets.append(f"Line {i + 1}: {lines[i]}")
            last_end = end

        if last_end < n:
            snippets.append("...")

        return "\n".join(snippets)

    def build_bundle(
        self,
        reason: ChiefEngineerCallReason,
        task_contract: dict[str, Any],
        changed_files_context: str,
        validation_output: str,
        visual_reference_image_path: str | None = None,
        visual_actual_image_path: str | None = None,
    ) -> dict[str, Any]:
        """Build contract-aware bundle payload."""
        # 1. Clean validation output
        compressed_validation = self.compress_diff_and_errors(
            validation_output, max_chars=4000 if task_contract.get("visual_required") else 2000
        )

        # 2. Redact both context and validation output
        redacted_files_context = self.redact_sensitive_info(changed_files_context)
        redacted_validation = self.redact_sensitive_info(compressed_validation)

        # 3. Clean task contract to avoid secrets
        clean_contract = {}
        if isinstance(task_contract, dict):
            for k, v in task_contract.items():
                if k not in ("api_key", "secret", "token", "password"):
                    clean_contract[k] = v

        # 4. Reason-based formatting
        bundle = {
            "reason": reason.value,
            "task_contract": clean_contract,
            "validation_output": redacted_validation,
        }

        if reason == ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN:
            bundle["changed_files_context"] = redacted_files_context
        elif reason == ChiefEngineerCallReason.FINAL_PR_REVIEW:
            bundle["diff_summary"] = redacted_files_context
        else:
            bundle["context"] = redacted_files_context

        if task_contract.get("visual_required"):
            bundle["visual_evidence"] = {
                "reference_attached": bool(
                    visual_reference_image_path and os.path.isfile(visual_reference_image_path)
                ),
                "actual_attached": bool(
                    visual_actual_image_path and os.path.isfile(visual_actual_image_path)
                ),
                "instruction": (
                    "Compare the attached reference and current-render images. Preserve the "
                    "calculator's full functionality while correcting the current render "
                    "toward the reference; never omit controls or use placeholders. The "
                    "reference image has precedence over any conflicting color, material, "
                    "geometry, or layout wording in the task prose."
                ),
            }

        # Preview token budget
        estimated_input_chars = len(json.dumps(bundle))
        estimated_tokens = max(1, estimated_input_chars // 4)
        logger.info(
            f"API call budget preview: reason={reason.value}, estimated_input_tokens={estimated_tokens}"
        )
        print(
            f"[Economy Bundler] Previewing API call: reason={reason.value}, estimated_input_tokens={estimated_tokens}"
        )

        return bundle

    def build_visual_user_content(
        self,
        bundle: dict[str, Any],
        *,
        visual_reference_image_path: str | None = None,
        visual_actual_image_path: str | None = None,
    ) -> str | list[dict[str, Any]]:
        """Build a compact multimodal message for visual repair calls.

        Images are resized and JPEG-compressed before attachment so visual
        feedback remains useful without turning every retry into a large paid
        payload. Text-only models still receive the complete JSON bundle.
        """
        text = json.dumps(bundle, sort_keys=True)
        if bundle.get("visual_evidence"):
            text += (
                "\nFINAL VISUAL CHECKLIST: the reference image is the acceptance authority. "
                "Preserve every existing key and handler. Do not create blank grid rows or "
                "large vertical gaps. The physical calculator must fill the viewport, with "
                "the full bottom row visible; remove only debug/footer chrome absent from the "
                "reference. If the current file is already structurally complete, prefer CSS "
                "changes over rewriting its JavaScript."
            )
        image_parts: list[dict[str, Any]] = []
        for label, path in (
            ("reference", visual_reference_image_path),
            ("current render", visual_actual_image_path),
        ):
            data_url = self._image_data_url(path)
            if data_url:
                image_parts.append({"type": "text", "text": f"Attached image: {label}."})
                image_parts.append(
                    {"type": "image_url", "image_url": {"url": data_url}}
                )
        if not image_parts:
            return text
        return [{"type": "text", "text": text}, *image_parts]

    def _image_data_url(self, path: str | None) -> str | None:
        if not path or not os.path.isfile(path):
            return None
        try:
            from PIL import Image

            with Image.open(path) as image:
                rgb_image = image.convert("RGB")
                rgb_image.thumbnail((768, 768))
                output = io.BytesIO()
                rgb_image.save(output, format="JPEG", quality=68, optimize=True)
                rgb_image.close()
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        except Exception as exc:
            logger.warning("Unable to encode visual evidence %s: %s", path, exc)
            return None
