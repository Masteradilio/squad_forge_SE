"""Claude-Mem Synthesizer — Captures user feedback & test failures to auto-update AGENTS.md."""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class RuleSynthesizer:
    """Synthesizes learned rules and updates root AGENTS.md and GEMINI.md instructions."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.agents_md_path = self.workspace_path / "AGENTS.md"
        self.gemini_md_path = self.workspace_path / "GEMINI.md"

    def synthesize_and_inject_rule(self, category: str, rule_text: str) -> bool:
        """Inject a learned rule into AGENTS.md and GEMINI.md."""
        rule_entry = f"\n- **[{category.upper()}]**: {rule_text}\n"

        for file_path in [self.agents_md_path, self.gemini_md_path]:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                if rule_text not in content:
                    content += rule_entry
                    file_path.write_text(content, encoding="utf-8")
                    logger.info(f"RuleSynthesizer injected rule into {file_path.name}: {rule_text}")

        return True
