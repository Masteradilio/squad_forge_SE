import re

from localforge.prd.schemas import ExtractedEpic, ExtractedPlan, ExtractedTask


class DeterministicPRDExtractor:
    """Conservative Markdown parser for the model-independent PRD baseline."""

    def extract(self, markdown: str) -> ExtractedPlan:
        epics: list[ExtractedEpic] = []
        tasks: list[ExtractedTask] = []
        current_epic: ExtractedEpic | None = None
        current_task: ExtractedTask | None = None
        table_headers: list[str] = []
        visual_matrix_headers: list[str] = []
        in_acceptance_section = False

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            heading = re.match(r"^(#{2,3})\s+(.+)$", line)
            if heading:
                title = self._clean_text(heading.group(2))
                in_acceptance_section = self._is_acceptance_heading(title)
                if in_acceptance_section:
                    current_task = tasks[-1] if tasks else None
                    table_headers = []
                    visual_matrix_headers = []
                    continue
                current_epic = ExtractedEpic(title=title, summary=f"Work related to {title}.")
                epics.append(current_epic)
                current_task = None
                table_headers = []
                visual_matrix_headers = []
                continue

            numbered = re.match(r"^\d+\.\s+(?:\*\*)?(.+?)(?:\*\*)?:?\s*$", line)
            if numbered:
                if in_acceptance_section:
                    continue
                title = self._clean_text(numbered.group(1))
                if title:
                    current_task = self._task_from_text(title, current_epic)
                    tasks.append(current_task)
                continue

            bullet = re.match(r"^[-*]\s+(?:\[[ xX]\]\s+)?(.+)$", line)
            if bullet:
                title = self._clean_text(bullet.group(1))
                if in_acceptance_section:
                    self._append_global_acceptance(tasks, title)
                    continue
                if title and current_task is not None:
                    self._append_acceptance(current_task, title)
                elif title and not title.endswith(":"):
                    tasks.append(self._task_from_text(title, current_epic))
                continue

            if line.startswith("|") and line.endswith("|"):
                cells = [self._clean_text(cell) for cell in line.strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                    continue
                if not table_headers:
                    table_headers = [cell.lower() for cell in cells]
                    if self._is_visual_matrix_header(table_headers):
                        visual_matrix_headers = table_headers
                    continue
                if cells:
                    if visual_matrix_headers:
                        target_task = current_task or (tasks[-1] if tasks else None)
                        if target_task is not None:
                            target_task.metadata.setdefault("visual_acceptance_matrix", []).append(
                                self._visual_matrix_entry(visual_matrix_headers, cells)
                            )
                        continue
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
                    current_task = None

        if tasks and not epics:
            epics.append(ExtractedEpic(title="Imported PRD", summary="Tasks imported from PRD."))
        return ExtractedPlan(epics=epics, tasks=tasks)

    def _task_from_text(self, text: str, current_epic: ExtractedEpic | None) -> ExtractedTask:
        return ExtractedTask(
            epic_title=current_epic.title if current_epic else None,
            title=text,
            description=text,
            acceptance_criteria=[f"Complete: {text}"],
            metadata={"source": "markdown"},
        )

    def _append_acceptance(self, task: ExtractedTask, text: str) -> None:
        criterion = f"Complete: {text}"
        if criterion not in task.acceptance_criteria:
            task.acceptance_criteria.append(criterion)

    def _append_global_acceptance(self, tasks: list[ExtractedTask], text: str) -> None:
        if not text or not tasks:
            return
        # Global criteria lack deterministic task references. Attach them to the nearest
        # preceding task and leave semantic redistribution to human/model plan review.
        self._append_acceptance(tasks[-1], text)

    def _is_acceptance_heading(self, title: str) -> bool:
        normalized = title.lower()
        # PRDs commonly use either the explicit Portuguese heading
        # ``Aceitacao`` or the longer ``Criterios de Aceitacao``. Both are
        # project-level gates; neither should become an implementation task.
        return (
            ("crit" in normalized and "aceita" in normalized)
            or "aceita" in normalized
            or "acceptance" in normalized
        )

    def _is_visual_matrix_header(self, headers: list[str]) -> bool:
        """Recognize a contract table without turning its rows into backlog tasks."""
        normalized = " ".join(headers)
        return (
            any(token in normalized for token in ("row", "linha"))
            and any(token in normalized for token in ("column", "coluna"))
            and any(token in normalized for token in ("action", "acao", "ação"))
            and any(token in normalized for token in ("label", "legenda"))
        )

    def _visual_matrix_entry(self, headers: list[str], cells: list[str]) -> dict[str, object]:
        """Map common localized visual-contract columns to stable contract keys."""
        entry: dict[str, object] = {}
        aliases = {
            "row": ("row", "linha"),
            "column": ("column", "coluna"),
            "primary_label": ("primary label", "label principal", "white"),
            "blue_label": ("blue legend", "legenda azul", "blue"),
            "orange_label": ("orange legend", "legenda laranja", "orange"),
            "action": ("action", "ação", "acao"),
        }
        for index, header in enumerate(headers):
            value = cells[index].strip() if index < len(cells) else ""
            if not value:
                continue
            normalized_header = header.lower()
            key = next(
                (
                    candidate
                    for candidate, names in aliases.items()
                    if any(name in normalized_header for name in names)
                ),
                None,
            )
            if key is not None:
                entry[key] = int(value) if key in {"row", "column"} and value.isdigit() else value
        if "row" in entry and "column" in entry:
            entry["locator"] = f"[data-row='{entry['row']}'][data-column='{entry['column']}']"
        return entry

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().rstrip(".")
