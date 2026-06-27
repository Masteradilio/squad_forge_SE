import re
import json
import logging
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
        text = re.sub(r"(api[-_]?key\s*=\s*['\"])[^'\"]+(['\"])", r"\1[REDACTED_API_KEY]\2", text, flags=re.IGNORECASE)
        # Redact password assignments
        text = re.sub(r"(password\s*=\s*['\"])[^'\"]+(['\"])", r"\1[REDACTED_PASSWORD]\2", text, flags=re.IGNORECASE)
        # Redact token assignments
        text = re.sub(r"(token\s*=\s*['\"])[^'\"]+(['\"])", r"\1[REDACTED_TOKEN]\2", text, flags=re.IGNORECASE)
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
            return compressed[:half] + f"\n... [TRUNCATED {len(compressed) - max_chars} CHARS] ...\n" + compressed[-half:]
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
            return content[:half_limit] + "\n\n... [MIDDLE OF FILE OMITTED FOR BREVITY] ...\n\n" + content[-half_limit:]

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
                            snippets.append(f"Line {i+1}: {lines[i]}")
                
            for i in range(start, end):
                snippets.append(f"Line {i+1}: {lines[i]}")
            last_end = end

        if last_end < n:
            snippets.append("...")

        return "\n".join(snippets)

    def build_bundle(
        self,
        reason: ChiefEngineerCallReason,
        task_contract: dict[str, Any],
        changed_files_context: str,
        validation_output: str
    ) -> dict[str, Any]:
        """Build contract-aware bundle payload."""
        # 1. Clean validation output
        compressed_validation = self.compress_diff_and_errors(
            validation_output, 
            max_chars=4000 if task_contract.get("visual_required") else 2000
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

        # Preview token budget
        estimated_input_chars = len(json.dumps(bundle))
        estimated_tokens = max(1, estimated_input_chars // 4)
        logger.info(f"API call budget preview: reason={reason.value}, estimated_input_tokens={estimated_tokens}")
        print(f"[Economy Bundler] Previewing API call: reason={reason.value}, estimated_input_tokens={estimated_tokens}")

        return bundle
