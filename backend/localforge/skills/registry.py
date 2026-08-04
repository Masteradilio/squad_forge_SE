import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from localforge.models import domain


class SkillDefinition(BaseModel):
    name: str
    purpose: str
    triggers: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    source: str = "builtin"
    enabled: bool = True
    last_used_at: str | None = None
    success_rate: float | None = None


BUILTIN_SKILLS = [
    SkillDefinition(
        name="python-pytest",
        purpose="Use targeted pytest commands for Python backend validation.",
        triggers=["python", "pytest", "backend", "tests"],
        allowed_actions=["read tests", "write tests", "run targeted pytest"],
        expected_artifacts=["tests.md"],
        failure_modes=["fixture drift", "slow broad suite", "warning masking"],
        examples=["python -m pytest backend/tests/test_api_server.py -q"],
    ),
    SkillDefinition(
        name="fastapi-endpoint",
        purpose="Add or modify FastAPI endpoints with typed request and response contracts.",
        triggers=["fastapi", "api", "endpoint", "route"],
        allowed_actions=["edit app.py", "add request models", "add endpoint tests"],
        expected_artifacts=["review.md", "tests.md"],
        failure_modes=["untyped payloads", "missing 404 path", "schema drift"],
        examples=["Add a Pydantic request model before wiring the route."],
    ),
    SkillDefinition(
        name="react-component",
        purpose="Build small React UI components and wire them to typed API clients.",
        triggers=["react", "tsx", "frontend", "component"],
        allowed_actions=["edit TSX", "edit client types", "run frontend build"],
        expected_artifacts=["review.md"],
        failure_modes=["local-only state", "untyped API response", "layout overflow"],
        examples=["Prefer existing Card, Button, Table components."],
    ),
    SkillDefinition(
        name="nextjs-page",
        purpose="Implement Next.js pages when the project uses Next routing.",
        triggers=["nextjs", "next.js", "page", "app router"],
        allowed_actions=["edit page files", "edit route handlers"],
        expected_artifacts=["review.md"],
        failure_modes=["server/client boundary mismatch"],
        examples=["Keep server data loading separate from client controls."],
    ),
    SkillDefinition(
        name="github-pr-writer",
        purpose="Prepare PR-ready summaries and branch protection checklists.",
        triggers=["pull request", "pr", "github", "review"],
        allowed_actions=["write pr.md", "summarize artifacts"],
        expected_artifacts=["pr.md"],
        failure_modes=["missing test evidence", "missing branch name"],
        examples=["Include changed files, tests, risk, and branch protection."],
    ),
    SkillDefinition(
        name="git-worktree-debugging",
        purpose="Diagnose local worktree and branch state safely.",
        triggers=["git", "worktree", "branch", "dirty"],
        allowed_actions=["read git status", "inspect worktrees"],
        expected_artifacts=["risk.md"],
        failure_modes=["destructive reset", "untracked user changes"],
        examples=["Use non-destructive inspection before changing Git state."],
    ),
    SkillDefinition(
        name="security-auditor",
        purpose="Perform post-merge security audit, vulnerability scanning, secret leakage prevention, and generate relatorio_conformidade_seguranca.md.",
        triggers=["security", "audit", "vulnerability", "secret", "cve", "sast"],
        allowed_actions=["audit source code", "scan secrets", "scan dependencies", "generate relatorio_conformidade_seguranca.md"],
        expected_artifacts=["relatorio_conformidade_seguranca.md"],
        failure_modes=["hardcoded secrets", "cve vulnerabilities", "bypassed security gates"],
        examples=["Check for plain-text secrets and unauthenticated endpoints."],
    ),
    SkillDefinition(
        name="e2e-release-tester",
        purpose=(
            "Universal post-merge E2E quality & PRD compliance verification using "
            "Playwright, HTTP client, CLI runner, and DB inspector to generate "
            "relatorio_conformidade_funcional.md."
        ),
        triggers=["e2e", "test", "compliance", "prd", "release", "quality", "functional"],
        allowed_actions=["browser automation", "http api request", "run subprocess", "inspect database", "generate relatorio_conformidade_funcional.md"],
        expected_artifacts=["relatorio_conformidade_funcional.md"],
        failure_modes=["prd non-conformity", "broken user flows", "untested acceptance criteria"],
        examples=["Execute Playwright user journeys and compare against PRD.md criteria."],
    ),
]


class SkillRegistry:
    def __init__(self, project_root: str):
        self.project_root = project_root

    def load_all(self) -> list[SkillDefinition]:
        skills = {skill.name: skill for skill in BUILTIN_SKILLS}
        for skill in self._load_local():
            skills[skill.name] = skill
        return sorted(skills.values(), key=lambda skill: skill.name)

    def select_for_task(self, task: domain.Task) -> list[SkillDefinition]:
        skills = self.load_all()
        metadata_text = " ".join(
            str(value)
            for value in [
                task.key,
                task.title,
                task.description,
                task.risk_level,
                task.metadata,
                " ".join(task.acceptance_criteria),
            ]
        ).lower()
        selected: list[SkillDefinition] = []
        for skill in skills:
            if any(trigger.lower() in metadata_text for trigger in skill.triggers):
                selected.append(skill)
        return selected[:6]

    def write_local(self, skill: SkillDefinition) -> SkillDefinition:
        target_dir = Path(self.project_root) / ".localforge" / "skills"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{_safe_name(skill.name)}.json"
        data = skill.model_dump(mode="json")
        data["source"] = "local"
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return SkillDefinition.model_validate(data)

    def _load_local(self) -> list[SkillDefinition]:
        skill_dir = Path(self.project_root) / ".localforge" / "skills"
        if not skill_dir.is_dir():
            return []
        loaded: list[SkillDefinition] = []
        for path in sorted(skill_dir.glob("*.json")):
            try:
                raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                raw["source"] = "local"
                loaded.append(SkillDefinition.model_validate(raw))
            except (OSError, json.JSONDecodeError, ValidationError):
                continue
        return loaded


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name.lower())
    return cleaned.strip("-") or "skill"
