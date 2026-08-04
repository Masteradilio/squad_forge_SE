"""Claude-Mem Synthesizer — Captures user feedback & test failures to auto-update AGENTS.md."""

import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class RuleSynthesizer:
    """Synthesizes learned rules and updates root AGENTS.md and GEMINI.md instructions."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.agents_md_path = self.workspace_path / "AGENTS.md"
        self.gemini_md_path = self.workspace_path / "GEMINI.md"

    def synthesize_and_inject_rule(self, category: str, rule_text: str) -> bool:
        """Inject a learned rule into AGENTS.md and GEMINI.md."""
        category = re.sub(r"[^A-Za-z0-9 _.-]", "", category).strip()[:80]
        rule_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", rule_text).strip()
        if not category or not rule_text or len(rule_text) > 2000:
            raise ValueError("rule category/text is empty or exceeds the safe size limit")
        if "```" in rule_text or re.search(r"(?im)^\s*(system|developer|assistant)\s*:", rule_text):
            raise ValueError("rule text contains prompt/control markup")
        rule_entry = f"\n- **[{category.upper()}]**: {rule_text}\n"

        changed = False
        for file_path in [self.agents_md_path, self.gemini_md_path]:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                if rule_text not in content:
                    content += rule_entry
                    with tempfile.NamedTemporaryFile(
                        "w", encoding="utf-8", dir=file_path.parent, delete=False
                    ) as handle:
                        handle.write(content)
                        temporary_path = Path(handle.name)
                    temporary_path.replace(file_path)
                    changed = True
                    logger.info(f"RuleSynthesizer injected rule into {file_path.name}: {rule_text}")

        return changed
