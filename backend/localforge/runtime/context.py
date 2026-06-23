import os
from dataclasses import dataclass

from localforge.models import domain
from localforge.safety.kernel import is_path_safe
from localforge.skills import SkillRegistry
from localforge.storage import UnitOfWork


@dataclass(frozen=True)
class TaskContext:
    rendered: str
    omitted_files: list[str]


class TaskContextBuilder:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def build(
        self,
        task_id: int,
        worktree_path: str,
        *,
        max_chars: int = 8_000,
        max_file_chars: int = 2_000,
    ) -> TaskContext:
        assert self.uow.tasks is not None
        assert self.uow.audits is not None
        assert self.uow.projects is not None
        task = await self.uow.tasks.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")
        project = await self.uow.projects.get_project(task.project_id)
        if not project:
            raise ValueError(f"Project with ID {task.project_id} not found.")

        policy = await self.uow.audits.get_project_policy(task.project_id, "default")
        selected_skills = SkillRegistry(project.root_path).select_for_task(task)
        relevant_memory: list[domain.MemoryFact] = []
        if self.uow.memory is not None:
            relevant_memory = await self.uow.memory.retrieve_relevant(
                task.project_id,
                query=f"{task.key} {task.title} {task.description} {task.metadata}",
            )
        recent_comments: list[domain.TaskComment] = []
        if self.uow.coordination is not None:
            recent_comments = await self.uow.coordination.recent_comments_for_context(
                task_id,
                limit=5,
            )
        raw_relevant_files = task.metadata.get("relevant_files", [])
        relevant_files: list[object] = raw_relevant_files if isinstance(raw_relevant_files, list) else []

        file_char_budget = min(max_file_chars, max(80, max_chars // 3))
        policy_summary = "default policy"
        if policy:
            protected = ", ".join(policy.rules.get("protected_paths", []))
            blocked = ", ".join(policy.rules.get("blocked_commands", []))
            policy_summary = f"protected={protected or 'none'}; blocked={blocked or 'none'}"

        sections = [
            f"Task: {task.key} {task.title}",
            f"Desc: {task.description}",
            f"Accept: {'; '.join(task.acceptance_criteria) or 'not specified'}",
            f"Worktree: {worktree_path}",
            f"Policy: {policy_summary}",
            "Skills:",
            *([
                f"- {skill.name}: {skill.purpose}; artifacts={', '.join(skill.expected_artifacts) or 'none'}"
                for skill in selected_skills
            ] or ["- none"]),
            "Memory:",
            *([
                f"- {fact.kind.value}: {fact.fact}"
                for fact in relevant_memory
            ] or ["- none"]),
            "Recent comments:",
            *([
                f"- {comment.author}: {comment.body[:240]}"
                for comment in recent_comments
            ] or ["- none"]),
            "Files:",
        ]
        omitted: list[str] = []

        for rel_path in relevant_files:
            if not isinstance(rel_path, str):
                continue
            target = os.path.realpath(os.path.abspath(os.path.join(worktree_path, rel_path)))
            if not is_path_safe(target, worktree_path) or not os.path.isfile(target):
                omitted.append(f"{rel_path} omitted")
                sections.append(f"- {rel_path} omitted")
                continue
            with open(target, encoding="utf-8") as handle:
                content = handle.read()
            if len(content) > file_char_budget:
                omitted.append(f"{rel_path} omitted")
                sections.append(f"{rel_path} omitted: file too large")
                continue
            sections.append(f"{rel_path}:\n{content}")

        rendered = "\n".join(sections)
        if len(rendered) > max_chars:
            rendered = rendered[: max_chars - 24].rstrip() + "\n[context truncated]"
        return TaskContext(rendered=rendered, omitted_files=omitted)
