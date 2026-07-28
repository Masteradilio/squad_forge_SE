import re
import unicodedata

from pydantic import BaseModel, Field

from localforge.prd.schemas import ExtractedPlan, ExtractedTask


class TaskContract(BaseModel):
    task_title: str
    allowed_files: list[str] = Field(default_factory=list)
    required_public_apis: list[str] = Field(default_factory=list)
    forbidden_dependencies: list[str] = Field(default_factory=list)
    canonical_test_command: str = "python -m pytest -q"
    risk_level: str = "low"
    seniority_class: str = "local_assisted"
    visual_required: bool = False
    implementation_notes: list[str] = Field(default_factory=list)


class ArchitectureContract(BaseModel):
    contract_id: str = "architecture-contract-v1"
    module_map: dict[str, list[str]] = Field(default_factory=dict)
    public_apis: dict[str, list[str]] = Field(default_factory=dict)
    dependency_graph: dict[str, list[str]] = Field(default_factory=dict)
    canonical_test_command: str = "python -m pytest -q"
    task_contracts: dict[str, TaskContract] = Field(default_factory=dict)


def build_architecture_contract(plan: ExtractedPlan) -> ArchitectureContract:
    """Build a domain-neutral architecture contract from explicit PRD evidence."""
    task_contracts: dict[str, TaskContract] = {}
    module_map: dict[str, list[str]] = {}
    public_apis: dict[str, list[str]] = {}
    dependency_graph: dict[str, list[str]] = {}
    titles = {task.title for task in plan.tasks}

    for task in plan.tasks:
        contract = _task_contract(task)
        task_contracts[task.title] = contract
        package = _package_for_task(contract.allowed_files, task.title)
        package_files = module_map.setdefault(package, [])
        for file_path in contract.allowed_files:
            if file_path not in package_files:
                package_files.append(file_path)
        public_apis[task.title] = contract.required_public_apis
        dependency_graph[task.title] = _dependencies_for_task(task, titles)

    return ArchitectureContract(
        module_map=module_map,
        public_apis=public_apis,
        dependency_graph=dependency_graph,
        task_contracts=task_contracts,
    )


def _task_contract(task: ExtractedTask) -> TaskContract:
    allowed_files = task.expected_files or _infer_allowed_files(task.title)
    return TaskContract(
        task_title=task.title,
        allowed_files=allowed_files,
        required_public_apis=_string_list_metadata(task, "required_public_apis"),
        forbidden_dependencies=_string_list_metadata(task, "forbidden_dependencies"),
        canonical_test_command=_test_command_for(allowed_files),
        risk_level=_risk_for_task(task.title, task.risk_level),
        seniority_class=_seniority_for_task(task.title, allowed_files, task.risk_level),
        visual_required=_visual_required_for_task(task.title, allowed_files),
        implementation_notes=_implementation_notes(task),
    )


def _infer_allowed_files(title: str) -> list[str]:
    """Create a conservative generic file contract when the PRD names no files."""
    slug = _slug(title)
    if _contains_term(
        title, "documentation", "document", "readme", "guide", "changelog"
    ):
        return [f"docs/{slug}.md"]
    if _contains_term(title, "frontend", "interface", "ui", "component", "page", "view"):
        return [
            f"frontend/src/components/{slug}.tsx",
            f"frontend/src/components/{slug}.test.tsx",
        ]
    if _contains_term(title, "api", "endpoint", "route"):
        return [f"backend/{slug}.py", f"backend/tests/test_{slug}.py"]
    if _contains_term(title, "migration", "schema", "database"):
        return [f"migrations/{slug}.py", f"tests/test_{slug}.py"]
    return [f"src/{slug}.py", f"tests/test_{slug}.py"]


def _test_command_for(allowed_files: list[str]) -> str:
    python_tests = [
        path
        for path in allowed_files
        if path.startswith(("tests/", "backend/tests/")) and path.endswith(".py")
    ]
    if python_tests:
        return f"python -m pytest {' '.join(python_tests)} -q"

    frontend_tests = [
        path.removeprefix("frontend/")
        for path in allowed_files
        if path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    ]
    if frontend_tests:
        return f"npm test --prefix frontend -- {' '.join(frontend_tests)}"
    return "git diff --check"


def _risk_for_task(title: str, declared_risk: str) -> str:
    normalized = declared_risk.lower()
    if normalized in {"high", "critical"}:
        return normalized
    if _contains_term(
        title,
        "architecture",
        "authentication",
        "authorization",
        "security",
        "migration",
        "database",
        "payment",
        "breaking",
        "public api",
    ):
        return "high"
    if _contains_term(title, "frontend", "integration", "concurrency", "state machine"):
        return "medium"
    return normalized if normalized in {"low", "medium"} else "low"


def _visual_required_for_task(title: str, allowed_files: list[str]) -> bool:
    return _contains_term(title, "visual", "frontend", "ui", "layout", "design") or any(
        path.endswith((".html", ".css", ".tsx", ".jsx")) for path in allowed_files
    )


def _seniority_for_task(title: str, allowed_files: list[str], declared_risk: str) -> str:
    if _contains_term(title, "documentation", "changelog", "readme", "summary"):
        return "local_only"
    risk = _risk_for_task(title, declared_risk)
    if risk == "critical" or len(allowed_files) > 5:
        return "chief_only"
    if risk == "high" or _contains_term(
        title, "architecture", "public api", "cross-module", "breaking change"
    ):
        return "chief_only"
    if _visual_required_for_task(title, allowed_files) or len(allowed_files) > 2:
        return "chief_led"
    return "local_assisted"


def _dependencies_for_task(task: ExtractedTask, known_titles: set[str]) -> list[str]:
    dependencies = _string_list_metadata(task, "depends_on")
    if not dependencies:
        dependencies = _string_list_metadata(task, "dependency_titles")
    return list(dict.fromkeys(item for item in dependencies if item in known_titles and item != task.title))


def _implementation_notes(task: ExtractedTask) -> list[str]:
    notes = _string_list_metadata(task, "implementation_notes")
    if task.expected_files:
        notes.append("Do not write outside the explicit files listed by the PRD contract.")
    else:
        notes.append(
            "File paths are conservative deterministic defaults; request a contract change "
            "before expanding scope."
        )
    return list(dict.fromkeys(notes))


def _string_list_metadata(task: ExtractedTask, key: str) -> list[str]:
    value = task.metadata.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _package_for_task(allowed_files: list[str], title: str) -> str:
    if not allowed_files:
        return _slug(title)
    first = allowed_files[0]
    return first.split("/", 1)[0] if "/" in first else first.removesuffix(".py")


def _contains_term(value: str, *terms: str) -> bool:
    normalized = _slug(value).replace("_", " ")
    return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in terms)


def _slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower())
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_") or "task"
