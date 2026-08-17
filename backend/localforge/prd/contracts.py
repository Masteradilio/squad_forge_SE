import hashlib
import re
import unicodedata
from pathlib import Path

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
    visual_reference_image: str | None = None
    visual_actual_output: str | None = None
    visual_similarity_threshold: float = 0.75
    visual_viewport: str = "1280x720"
    visual_structure_rules: list[str] = Field(default_factory=list)
    visual_acceptance_matrix: list[dict[str, object]] = Field(default_factory=list)
    visual_acceptance_contract_version: str = "visual-contract-v1"
    acceptance_test_policy: str = "observable_behavior_only"
    acceptance_behaviors: list[str] = Field(default_factory=list)
    acceptance_test_fixture_source: str | None = None
    acceptance_test_fixture_target: str | None = None
    implementation_notes: list[str] = Field(default_factory=list)


class ArchitectureContract(BaseModel):
    contract_id: str = "architecture-contract-v1"
    module_map: dict[str, list[str]] = Field(default_factory=dict)
    public_apis: dict[str, list[str]] = Field(default_factory=dict)
    dependency_graph: dict[str, list[str]] = Field(default_factory=dict)
    canonical_test_command: str = "python -m pytest -q"
    task_contracts: dict[str, TaskContract] = Field(default_factory=dict)


def build_architecture_contract(
    plan: ExtractedPlan, project_root: Path | None = None
) -> ArchitectureContract:
    """Build a domain-neutral architecture contract from explicit PRD evidence."""
    task_contracts: dict[str, TaskContract] = {}
    module_map: dict[str, list[str]] = {}
    public_apis: dict[str, list[str]] = {}
    dependency_graph: dict[str, list[str]] = {}
    titles = {task.title for task in plan.tasks}
    web_product = _plan_has_web_surface(plan)

    for task in plan.tasks:
        contract = _task_contract(task, project_root=project_root, web_product=web_product)
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


def _task_contract(
    task: ExtractedTask,
    *,
    project_root: Path | None = None,
    web_product: bool = False,
) -> TaskContract:
    allowed_files = task.expected_files or _infer_allowed_files(task.title, web_product=web_product)
    declared_visual_reference = _metadata_path(task, "visual_reference_image")
    visual_reference_image = declared_visual_reference
    visual_required = _visual_required_for_task(
        task.title,
        allowed_files,
        metadata=task.metadata,
        reference=declared_visual_reference,
    )
    if (
        visual_required
        and visual_reference_image is None
        and project_root is not None
        and _has_web_surface(allowed_files)
    ):
        visual_reference_image = _discover_visual_reference(project_root)
    visual_actual_output: str | None = None
    visual_viewport = "1280x720"
    if project_root is not None and visual_required:
        actual = _metadata_path(task, "visual_actual_output")
        if actual is None:
            actual = _first_allowed_html(allowed_files)
        if actual is None:
            actual = _discover_visual_output(project_root)
        # A clean PRD workspace has no generated HTML yet. Publish a
        # deterministic product target so visual tasks create an executable
        # artifact instead of falling back to a Python placeholder file.
        if actual is None:
            actual = "app/index.html"
        if actual:
            visual_actual_output = actual
            if actual not in allowed_files:
                allowed_files = [actual, *allowed_files]
        if visual_reference_image:
            visual_viewport = _viewport_for_reference(project_root / visual_reference_image)
    implementation_notes = _implementation_notes(task)
    visual_structure_rules = _visual_structure_rules_for_task(task.title, visual_required)
    visual_acceptance_matrix = _visual_acceptance_matrix(task, visual_required)
    if visual_structure_rules:
        implementation_notes.extend(
            [
                "Use one parent keypad grid with direct child key elements; do not nest "
                "separate row grids when a key spans rows.",
                "For a spanning ENTER-style key, reserve the same column in both rows and "
                "use explicit grid-column and grid-row placement.",
            ]
        )
    if visual_required and visual_reference_image:
        implementation_notes.append(
            "The visual reference image is authoritative for geometry, materials, colors, "
            "labels, and spacing when it conflicts with prose."
        )
    return TaskContract(
        task_title=task.title,
        allowed_files=allowed_files,
        required_public_apis=_string_list_metadata(task, "required_public_apis"),
        forbidden_dependencies=_string_list_metadata(task, "forbidden_dependencies"),
        canonical_test_command=_test_command_for(allowed_files),
        risk_level=_risk_for_task(task.title, task.risk_level),
        seniority_class=_seniority_for_task(task.title, allowed_files, task.risk_level),
        visual_required=visual_required,
        visual_reference_image=visual_reference_image,
        visual_actual_output=visual_actual_output,
        visual_viewport=visual_viewport,
        visual_structure_rules=visual_structure_rules,
        visual_acceptance_matrix=visual_acceptance_matrix,
        acceptance_test_policy=str(
            task.metadata.get("acceptance_test_policy", "observable_behavior_only")
        ),
        acceptance_behaviors=_string_list_metadata(task, "acceptance_behaviors"),
        acceptance_test_fixture_source=_metadata_path(task, "acceptance_test_fixture_source"),
        acceptance_test_fixture_target=_metadata_path(task, "acceptance_test_fixture_target"),
        implementation_notes=implementation_notes,
    )


def _infer_allowed_files(title: str, *, web_product: bool = False) -> list[str]:
    """Create a conservative generic file contract when the PRD names no files."""
    slug = _slug(title)
    if _contains_term(title, "documentation", "document", "readme", "guide", "changelog"):
        return [f"docs/{slug}.md"]
    if web_product:
        # A web PRD without explicit paths still needs a shared product surface.
        # Keep the scope bounded to the single-page artifact and one task test;
        # do not invent per-task source files that make integration impossible.
        return ["app/index.html", f"tests/test_{slug}.py"]
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


def _plan_has_web_surface(plan: ExtractedPlan) -> bool:
    web_terms = (
        "web",
        "desktop",
        "html",
        "css",
        "frontend",
        "interface",
        "ui",
        "layout",
        "calculator",
        "chassis",
        "keypad",
        "lcd",
        "display",
        "keyboard",
    )
    return any(
        _contains_term(task.title, *web_terms)
        or any(path.endswith((".html", ".css", ".tsx", ".jsx")) for path in task.expected_files)
        for task in plan.tasks
    )


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


def _visual_required_for_task(
    title: str,
    allowed_files: list[str],
    *,
    metadata: dict[str, object] | None = None,
    reference: str | None = None,
) -> bool:
    if metadata is not None and isinstance(metadata.get("visual_required"), bool):
        return bool(metadata["visual_required"])
    explicit_visual_gate = _contains_term(
        title,
        "visual validation",
        "visual fidelity",
        "screenshot",
        "pixel",
    )
    final_visual_assembly = _contains_term(
        title, "integration", "release", "assembly", "package", "bundle"
    ) and any(path.endswith((".html", ".css", ".tsx", ".jsx")) for path in allowed_files)
    product_surface = _has_web_surface(allowed_files)
    domain_visual_task = _is_visual_domain_task(title) and product_surface
    return explicit_visual_gate or final_visual_assembly or domain_visual_task or reference is not None


def _is_visual_domain_task(title: str) -> bool:
    if _contains_term(title, "map", "mapping") and _contains_term(title, "keyboard"):
        return False
    return _contains_term(
        title,
        "visual",
        "frontend",
        "ui",
        "layout",
        "design",
        "grid",
        "keypad",
        "calculator",
        "chassis",
        "lcd",
        "display",
        "dashboard",
        "view",
        "component",
        "page",
        "screen",
        "styling",
        "theme",
    )


def _visual_structure_rules_for_task(title: str, visual_required: bool) -> list[str]:
    if not visual_required:
        return []
    return [
        "single_product_surface",
        "stable_interactive_locators",
        "declared_visual_matrix",
        "responsive_reference_convergence",
    ]


def _visual_acceptance_matrix(
    task: ExtractedTask, visual_required: bool
) -> list[dict[str, object]]:
    """Normalize an optional PRD-declared visual matrix into an executable contract.

    The harness deliberately does not infer domain labels or controls. A PRD or
    the Scrum Master may declare a matrix as a list of records; the contract
    preserves only JSON-safe records and adds generic release requirements when
    the task is visual. This keeps the mechanism useful for any product surface.
    """
    raw = task.metadata.get("visual_acceptance_matrix")
    if not isinstance(raw, list):
        raw = task.metadata.get("visual_matrix")
    matrix = [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    if not visual_required:
        return matrix
    if not matrix:
        return [
            {
                "contract": "rendered_product_surface",
                "required": True,
                "assertions": [
                    "rendered_surface_exists",
                    "interactive_elements_have_stable_locators",
                    "every_declared_user_journey_is_click_executable",
                    "no_placeholder_or_unwired_control_is_releasable",
                ],
            }
        ]
    return matrix


def _discover_visual_output(project_root: Path) -> str | None:
    candidates = [
        path
        for path in project_root.glob("**/*.html")
        if not any(part in {".git", ".localforge", "node_modules", "dist"} for part in path.parts)
    ]
    candidates.sort(key=lambda path: ("index" not in path.name.lower(), str(path)))
    return candidates[0].relative_to(project_root).as_posix() if candidates else None


def _has_web_surface(allowed_files: list[str]) -> bool:
    return any(path.lower().endswith((".html", ".css", ".tsx", ".jsx")) for path in allowed_files)


def _first_allowed_html(allowed_files: list[str]) -> str | None:
    for path in allowed_files:
        if path.lower().endswith(".html"):
            return path
    return None


def _metadata_path(task: ExtractedTask, key: str) -> str | None:
    value = task.metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("\\", "/")
    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in normalized:
        return None
    return candidate.as_posix().lstrip("./")


def _discover_visual_reference(project_root: Path) -> str | None:
    candidates = [
        path
        for path in project_root.glob("docs/**/*")
        if path.is_file()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        and any(
            term in path.stem.lower()
            for term in ("reference", "design", "target", "actual")
        )
    ]
    candidates.sort(key=lambda path: str(path))
    return candidates[0].relative_to(project_root).as_posix() if candidates else None


def _viewport_for_reference(reference_path: Path) -> str:
    """Preserve the reference aspect ratio while keeping a useful render size."""
    try:
        from PIL import Image

        with Image.open(reference_path) as image:
            width, height = image.size
        if width > 0 and height > 0:
            return f"1280x{round(1280 * height / width)}"
    except Exception:
        pass
    return "1280x720"


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
    if (
        _visual_required_for_task(title, allowed_files)
        or _is_visual_domain_task(title)
        or len(allowed_files) > 2
    ):
        return "chief_led"
    return "local_assisted"


def _dependencies_for_task(task: ExtractedTask, known_titles: set[str]) -> list[str]:
    dependencies = _string_list_metadata(task, "depends_on")
    if not dependencies:
        dependencies = _string_list_metadata(task, "dependency_titles")
    return list(
        dict.fromkeys(item for item in dependencies if item in known_titles and item != task.title)
    )


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
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_") or "task"
    # Keep generated test/source paths below Windows path-length limits even
    # when a PRD task title is very descriptive. The digest preserves stable
    # distinction between titles that share the same shortened prefix.
    if len(slug) > 64:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug[:55].rstrip('_')}_{digest}"
    return slug
