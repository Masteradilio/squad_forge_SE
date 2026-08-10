import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from localforge.models import domain

SkillRuntime = Literal["instruction", "python"]
SkillPermission = Literal[
    "read_files",
    "write_files",
    "run_tests",
    "run_commands",
    "network",
]
ALLOWED_EXECUTION_PERMISSIONS = frozenset(
    {"read_files", "write_files", "run_tests", "run_commands", "network"}
)


class SkillDefinition(BaseModel):
    name: str
    purpose: str
    system_prompt: str = ""
    triggers: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    # Agent Harness profile. ``auto`` preserves the role-aware default while
    # allowing user-created skills to request a bounded strategy explicitly.
    strategy: Literal["auto", "predict", "code_act"] = "auto"
    max_retries: int = Field(default=1, ge=0, le=3)
    context_budget: int = Field(default=12000, ge=1000, le=50000)
    # Executable metadata is declarative only.  SkillRegistry never imports
    # or executes the referenced entrypoint.
    runtime: SkillRuntime = "instruction"
    entrypoint: str | None = None
    permissions: list[SkillPermission] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    manifest_version: int = Field(default=1, ge=1)
    source: str = "builtin"
    enabled: bool = True
    last_used_at: str | None = None
    success_rate: float | None = None

    @model_validator(mode="after")
    def _validate_execution_metadata(self) -> "SkillDefinition":
        if self.runtime == "python" and not self.entrypoint:
            raise ValueError("python skills require a non-empty entrypoint")
        if self.entrypoint is not None and not self.entrypoint.strip():
            if self.runtime == "python":
                raise ValueError("python skills require a non-empty entrypoint")
            self.entrypoint = None
        invalid_permissions = set(self.permissions) - ALLOWED_EXECUTION_PERMISSIONS
        if invalid_permissions:
            invalid = ", ".join(sorted(invalid_permissions))
            raise ValueError(f"unsupported skill execution permission(s): {invalid}")
        return self


BUILTIN_SKILLS = [
    SkillDefinition(
        name="grill-with-docs",
        purpose=(
            "Stress-test requirements against the existing codebase and record "
            "shared terminology, unresolved decisions, and ADR-ready context before implementation."
        ),
        triggers=["grill-with-docs", "requirements interview", "context.md", "adr"],
        allowed_actions=[
            "inspect repository context",
            "ask bounded requirement questions",
            "write context and ADR notes",
        ],
        expected_artifacts=["CONTEXT.md", "docs/ADR.md"],
        failure_modes=["ambiguous requirement", "unrecorded decision", "terminology drift"],
        examples=["Resolve the smallest set of unanswered branches before ticket implementation."],
    ),
    SkillDefinition(
        name="to-tickets",
        purpose=(
            "Turn an approved specification into dependency-aware tracer-bullet tickets "
            "with explicit ownership, file scope, and observable acceptance behavior."
        ),
        triggers=["to-tickets", "tracer bullet", "vertical slice", "ticket decomposition"],
        allowed_actions=[
            "compile task dependencies",
            "freeze task contracts",
            "write backlog evidence",
        ],
        expected_artifacts=["plan.md"],
        failure_modes=["synthetic task order", "missing dependency", "unbounded ticket scope"],
        examples=["Each ticket must expose its blocking edges and a real acceptance command."],
    ),
    SkillDefinition(
        name="tdd",
        purpose=(
            "Keep acceptance behavior executable and observable through a red-green-refactor "
            "workflow; tests must exercise the real production API and cannot bypass failures."
        ),
        triggers=["tdd", "red-green-refactor", "acceptance test", "canonical test"],
        allowed_actions=[
            "write behavioral tests",
            "run focused tests",
            "preserve assertions during repair",
        ],
        expected_artifacts=["tests.md"],
        failure_modes=["duplicated algorithm", "weakened assertion", "skipped test"],
        examples=["Start from a failing observable behavior, then implement only the bounded contract."],
    ),
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

    @staticmethod
    def canonical_manifest(skill: SkillDefinition | dict[str, Any]) -> dict[str, Any]:
        """Return the stable, data-only manifest used for replay bindings."""
        definition = skill if isinstance(skill, SkillDefinition) else SkillDefinition.model_validate(skill)
        return json.loads(
            json.dumps(definition.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        )

    @classmethod
    def manifest_digest(cls, skill: SkillDefinition | dict[str, Any]) -> str:
        payload = json.dumps(cls.canonical_manifest(skill), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

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
        self.validate_executable(skill)
        target_dir = Path(self.project_root) / ".localforge" / "skills"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{_safe_name(skill.name)}.json"
        data = skill.model_dump(mode="json")
        data["source"] = "local"
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return SkillDefinition.model_validate(data)

    def validate_executable(
        self,
        skill: SkillDefinition | dict[str, Any] | str,
    ) -> bool:
        """Validate declarative executable metadata without executing it."""

        definition = self._resolve_skill(skill)
        if definition.runtime not in {"instruction", "python"}:
            raise ValueError(f"unsupported skill runtime: {definition.runtime}")
        if definition.runtime == "python" and not definition.entrypoint:
            raise ValueError("python skills require a non-empty entrypoint")
        invalid_permissions = set(definition.permissions) - ALLOWED_EXECUTION_PERMISSIONS
        if invalid_permissions:
            invalid = ", ".join(sorted(invalid_permissions))
            raise ValueError(f"unsupported skill execution permission(s): {invalid}")
        return True

    def resolve_execution_manifest(
        self,
        skill: SkillDefinition | dict[str, Any] | str,
    ) -> dict[str, Any]:
        """Return a validated, data-only execution manifest for a skill."""

        definition = self._resolve_skill(skill)
        self.validate_executable(definition)
        return {
            "name": definition.name,
            "manifest_version": definition.manifest_version,
            "runtime": definition.runtime,
            "entrypoint": definition.entrypoint,
            "permissions": list(definition.permissions),
            "dependencies": list(definition.dependencies),
        }

    def delete_local(self, name: str) -> bool:
        target = Path(self.project_root) / ".localforge" / "skills" / f"{_safe_name(name)}.json"
        if not target.is_file():
            return False
        target.unlink()
        return True

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

    def _resolve_skill(
        self,
        skill: SkillDefinition | dict[str, Any] | str,
    ) -> SkillDefinition:
        if isinstance(skill, SkillDefinition):
            return skill
        if isinstance(skill, dict):
            return SkillDefinition.model_validate(skill)
        if isinstance(skill, str):
            for definition in self.load_all():
                if definition.name == skill:
                    return definition
            raise KeyError(f"skill not found: {skill}")
        raise TypeError("skill must be a SkillDefinition, mapping, or skill name")


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name.lower())
    return cleaned.strip("-") or "skill"
