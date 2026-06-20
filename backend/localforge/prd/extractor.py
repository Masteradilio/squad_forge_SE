import re

from localforge.prd.schemas import ExtractedEpic, ExtractedPlan, ExtractedTask


class DeterministicPRDExtractor:
    """Small Markdown parser for clean-room PRD baseline extraction."""

    def extract(self, markdown: str) -> ExtractedPlan:
        epics: list[ExtractedEpic] = []
        tasks: list[ExtractedTask] = []
        current_epic: ExtractedEpic | None = None
        table_headers: list[str] = []

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            heading = re.match(r"^(#{2,3})\s+(.+)$", line)
            if heading:
                title = self._clean_text(heading.group(2))
                current_epic = ExtractedEpic(title=title, summary=f"Work related to {title}.")
                epics.append(current_epic)
                table_headers = []
                continue

            bullet = re.match(r"^[-*]\s+(?:\[[ xX]\]\s+)?(.+)$", line)
            if bullet:
                title = self._clean_text(bullet.group(1))
                if title:
                    tasks.append(self._task_from_text(title, current_epic))
                continue

            if line.startswith("|") and line.endswith("|"):
                cells = [self._clean_text(cell) for cell in line.strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                    continue
                if not table_headers:
                    table_headers = [cell.lower() for cell in cells]
                    continue
                if cells:
                    title = cells[0]
                    acceptance = cells[1] if len(cells) > 1 else f"Complete {title}"
                    tasks.append(
                        ExtractedTask(
                            epic_title=current_epic.title if current_epic else None,
                            title=title,
                            description=title,
                            acceptance_criteria=[acceptance],
                            metadata={"source": "table", "headers": table_headers},
                        )
                    )

        if tasks and not epics:
            epics.append(ExtractedEpic(title="Imported PRD", summary="Tasks imported from PRD."))

        return ExtractedPlan(epics=epics, tasks=tasks)

    def _task_from_text(
        self, text: str, current_epic: ExtractedEpic | None
    ) -> ExtractedTask:
        return ExtractedTask(
            epic_title=current_epic.title if current_epic else None,
            title=text,
            description=text,
            acceptance_criteria=[f"Complete: {text}"],
            metadata={"source": "markdown"},
        )

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text.rstrip(".")
