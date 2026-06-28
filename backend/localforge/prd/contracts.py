import re

from pydantic import BaseModel, Field

from localforge.prd.schemas import ExtractedPlan, ExtractedTask


class TaskContract(BaseModel):
    task_title: str
    allowed_files: list[str] = Field(default_factory=list)
    required_public_apis: list[str] = Field(default_factory=list)
    forbidden_dependencies: list[str] = Field(default_factory=lambda: ["scipy", "numpy"])
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
    task_contracts: dict[str, TaskContract] = {}
    module_map: dict[str, list[str]] = {}
    public_apis: dict[str, list[str]] = {}
    dependency_graph: dict[str, list[str]] = {}
    for task in plan.tasks:
        contract = _task_contract(task)
        task_contracts[task.title] = contract
        package = _package_for_task(task)
        module_map.setdefault(package, [])
        for file_path in contract.allowed_files:
            if file_path not in module_map[package]:
                module_map[package].append(file_path)
        public_apis[task.title] = contract.required_public_apis
        dependency_graph[task.title] = _dependencies_for_task(task, plan.tasks)
    return ArchitectureContract(
        module_map=module_map,
        public_apis=public_apis,
        dependency_graph=dependency_graph,
        task_contracts=task_contracts,
    )


def _task_contract(task: ExtractedTask) -> TaskContract:
    allowed_files = task.expected_files or _infer_allowed_files(task.title)
    test_command = _test_command_for(allowed_files)
    if task.title.strip().endswith(":"):
        test_command = 'python -c "pass"'
    return TaskContract(
        task_title=task.title,
        allowed_files=allowed_files,
        required_public_apis=_infer_public_apis(task.title),
        forbidden_dependencies=_forbidden_dependencies(task.title),
        canonical_test_command=test_command,
        risk_level=_risk_for_task(task.title, task.risk_level),
        seniority_class=_seniority_for_task(task.title, allowed_files, task.risk_level),
        visual_required=_visual_required_for_task(task.title, allowed_files),
        implementation_notes=_implementation_notes(task.title),
    )


def _infer_allowed_files(title: str) -> list[str]:
    text = title.lower()
    slug = _slug(title)
    if "initialize calculator" in text or "calculator app structure" in text:
        return ["calculator/__init__.py", "calculator/core.py", "tests/test_calculator.py"]
    if "outer casing" in text:
        return ["calculator/ui/casing.py", "tests/test_ui_casing.py", "app/hp12c_platinum.html", "dist/HP12C_Platinum.html"]
    if "lcd display" in text:
        return ["calculator/ui/display.py", "tests/test_ui_display.py", "app/hp12c_platinum.html", "dist/HP12C_Platinum.html"]
    if "button grid" in text:
        return ["calculator/ui/buttons.py", "tests/test_ui_buttons.py", "app/hp12c_platinum.html", "dist/HP12C_Platinum.html"]
    if "visual regression" in text:
        return ["calculator/ui/visual_reference.py", "tests/test_visual_reference.py", "app/hp12c_platinum.html", "dist/HP12C_Platinum.html"]
    if "numeric" in text:
        return ["calculator/input.py", "tests/test_numeric_entry.py"]
    if "rpn stack" in text:
        return ["calculator/stack.py", "tests/test_rpn_stack.py"]
    if "memory register" in text:
        return ["calculator/memory.py", "tests/test_memory.py"]
    if "clear function" in text:
        return ["calculator/clear.py", "tests/test_clear.py"]
    if "tvm register" in text:
        return ["calculator/finance/tvm_model.py", "tests/test_tvm_model.py"]
    if "tvm solving" in text:
        return ["calculator/finance/tvm_solver.py", "tests/test_tvm_solver.py"]
    if "amortization" in text:
        return ["calculator/finance/amortization.py", "tests/test_amortization.py"]
    if "cash-flow" in text or "cash flow" in text:
        return ["calculator/finance/cashflow.py", "tests/test_cashflow.py"]
    if "npv" in text or "irr" in text:
        return ["calculator/finance/npv.py", "tests/test_npv_irr.py"]
    if "bond" in text:
        return ["calculator/finance/bonds.py", "tests/test_bonds.py"]
    if "date parsing" in text:
        return ["calculator/date_modes.py", "tests/test_date_modes.py"]
    if "date arithmetic" in text:
        return ["calculator/date_math.py", "tests/test_date_math.py"]
    if "arithmetic" in text:
        return ["calculator/operations.py", "tests/test_operations.py"]
    if "depreciation" in text:
        return ["calculator/depreciation.py", "tests/test_depreciation.py"]
    if "statistics" in text:
        return ["calculator/statistics.py", "tests/test_statistics.py"]
    if "probability" in text:
        return ["calculator/probability.py", "tests/test_probability.py"]
    if "shift state" in text:
        return ["calculator/shift.py", "tests/test_shift.py"]
    if "mode indicator" in text:
        return ["calculator/modes.py", "tests/test_modes.py"]
    if "keyboard" in text:
        return ["calculator/keyboard.py", "tests/test_keyboard.py"]
    if "program mode" in text:
        return ["calculator/programming.py", "tests/test_programming.py"]
    if "accessible" in text:
        return ["calculator/accessibility.py", "tests/test_accessibility.py"]
    if "financial golden" in text:
        return ["tests/test_financial_golden.py"]
    if "visual fidelity" in text:
        return ["docs/visual_fidelity_checklist.md"]
    if "smoke test" in text:
        return ["tests/test_smoke.py"]
    if "documentation" in text:
        return ["docs/user_guide.md"]
    if "pr-ready" in text or "pr ready" in text:
        return ["docs/pr_ready_summary.md"]
    return [f"{slug}.py", f"tests/test_{slug}.py"]


def _infer_public_apis(title: str) -> list[str]:
    text = title.lower()
    if "initialize calculator" in text or "calculator app structure" in text:
        return ["Calculator", "CalculatorState"]
    if "outer casing" in text:
        return ["PlatinumCasing"]
    if "lcd display" in text:
        return ["LCDDisplay"]
    if "button grid" in text:
        return ["ButtonGrid"]
    if "visual regression" in text:
        return ["render_reference_page"]
    if "tvm register" in text:
        return ["TVMRegisterModel"]
    if "tvm solving" in text:
        return ["solve_tvm"]
    if "numeric" in text:
        return ["NumericEntry"]
    if "rpn stack" in text:
        return ["RPNStack"]
    if "memory register" in text:
        return ["MemoryRegisters"]
    if "clear function" in text:
        return ["clear_all", "clear_entry"]
    if "amortization" in text:
        return ["amortization_schedule"]
    if "cash-flow" in text or "cash flow" in text:
        return ["CashFlowRegister"]
    if "npv" in text or "irr" in text:
        return ["npv", "irr"]
    if "bond" in text:
        return ["bond_price", "bond_yield", "BondStubStatus"]
    if "date parsing" in text:
        return ["DateParser"]
    if "date arithmetic" in text:
        return ["date_difference", "add_days"]
    if "arithmetic" in text:
        return ["add", "subtract", "multiply", "divide"]
    if "depreciation" in text:
        return ["straight_line", "sum_of_years_digits", "declining_balance"]
    if "statistics" in text:
        return ["StatisticsRegister"]
    if "probability" in text:
        return ["normal_cdf", "inverse_normal_cdf"]
    if "shift state" in text:
        return ["ShiftState"]
    if "mode indicator" in text:
        return ["ModeIndicators"]
    if "keyboard" in text:
        return ["KeyboardShortcutMap"]
    if "program mode" in text:
        return ["ProgramState"]
    if "accessible" in text:
        return ["InteractionState"]
    return []


def _package_for_task(task: ExtractedTask) -> str:
    files = task.expected_files or _infer_allowed_files(task.title)
    first = files[0]
    return first.split("/", 1)[0] if "/" in first else first.removesuffix(".py")


def _slug(value: str) -> str:
    import unicodedata
    val_clean = unicodedata.normalize('NFD', value.lower())
    val_ascii = "".join(c for c in val_clean if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", val_ascii).strip("_") or "task"



def _test_command_for(allowed_files: list[str]) -> str:
    test_files = [path for path in allowed_files if path.startswith("tests/")]
    if not test_files:
        docs = [path for path in allowed_files if path.startswith("docs/")]
        if len(docs) == 1:
            return f"python -c \"from pathlib import Path; assert Path('{docs[0]}').is_file()\""
        return 'python -c "pass"'
    if len(test_files) == 1:
        return f"python -m pytest {test_files[0]} -q"
    return "python -m pytest -q"


def _risk_for_task(title: str, declared_risk: str) -> str:
    text = title.lower()
    high_terms = ("architecture", "contract")
    medium_terms = (
        "tvm",
        "npv",
        "irr",
        "probability",
        "statistics",
        "amortization",
        "button grid",
        "lcd",
    )
    if any(term in text for term in high_terms) or declared_risk == "high":
        return "high"
    if any(term in text for term in ("tvm solving", "irr", "inverse")):
        return "high"
    if any(term in text for term in medium_terms):
        return "medium"
    return declared_risk


def _visual_required_for_task(title: str, allowed_files: list[str]) -> bool:
    text = title.lower()
    return any(
        term in text
        for term in ("visual", "frontend", "ui", "outer casing", "lcd", "button grid")
    ) or any(path.endswith((".html", ".css", ".tsx", ".jsx")) for path in allowed_files)


def _seniority_for_task(title: str, allowed_files: list[str], declared_risk: str) -> str:
    text = title.lower()
    if any(term in text for term in ("documentation", "changelog", "readme", "summary")):
        return "local_only"

    if _visual_required_for_task(title, allowed_files):
        return "chief_only"
    if len(allowed_files) > 5:
        return "chief_only"
    if len(allowed_files) > 2:
        return "chief_led"
    if any(
        term in text
        for term in (
            "architecture",
            "public api",
            "cross-module",
            "breaking change",
            "contract",
            "export",
            "json",
            "backend",
            "frontend",
            "crud",
            "test",
            "validation",
            "state machine",
            "machine",
            "criar",
            "editar",
            "listar",
            "deletar",
            "filtrar",
            "exportar",
            "título vazio",
            "titulo vazio",
            "transições proibidas",
            "transicoes proibidas",
        )
    ):
        return "chief_led"
    if declared_risk == "high":
        return "chief_led"
    return "local_assisted"


def _dependencies_for_task(
    task: ExtractedTask, tasks: list[ExtractedTask]
) -> list[str]:
    title = task.title
    text = title.lower()
    titles = [candidate.title for candidate in tasks]
    deps: list[str] = []

    init = _find_title(titles, "initialize calculator")
    if init and title != init and not _is_meta_task(text):
        deps.append(init)
    if "visual regression" in text:
        deps.extend(_find_many(titles, ["outer casing", "lcd display", "button grid"]))
    if "tvm solving" in text:
        deps.extend(_find_many(titles, ["tvm register"]))
    if "amortization" in text:
        deps.extend(_find_many(titles, ["tvm solving"]))
    if "npv" in text or "irr" in text:
        deps.extend(_find_many(titles, ["cash-flow", "cash flow"]))
    if "financial golden" in text:
        deps.extend(
            _find_many(
                titles,
                ["tvm solving", "amortization", "cash-flow", "npv", "irr", "bond"],
            )
        )
    if "prepare pr" in text:
        deps.extend(
            _find_many(
                titles,
                ["financial golden", "smoke test", "user documentation", "visual fidelity"],
            )
        )
    return list(dict.fromkeys(dep for dep in deps if dep != title))


def _find_title(titles: list[str], needle: str) -> str | None:
    for title in titles:
        if needle in title.lower():
            return title
    return None


def _find_many(titles: list[str], needles: list[str]) -> list[str]:
    found: list[str] = []
    for needle in needles:
        match = _find_title(titles, needle)
        if match:
            found.append(match)
    return found


def _is_meta_task(text: str) -> bool:
    return any(term in text for term in ("documentation", "checklist", "smoke test", "pr-ready"))


def _implementation_notes(title: str) -> list[str]:
    text = title.lower()
    notes: list[str] = [
        "Forbidden dependencies apply transitively; aliases and vendored copies are not allowed."
    ]
    if "initialize calculator" in text or "calculator app structure" in text:
        notes.append(
            "CalculatorState must expose registers mapping, display string, pending_op, and error flag."
        )
    if "tvm solving" in text:
        notes.append(
            "Use pure-Python bounded iterative solving with max_iterations=200, "
            "tolerance=1e-9, and NonConvergenceError on failure."
        )
    if "npv" in text or "irr" in text:
        notes.append(
            "Implement NPV directly and IRR with a bounded pure-Python root finder; "
            "IRR requires a cash-flow sign change, max_iterations=200, tolerance=1e-9, "
            "and NonConvergenceError on non-convergence."
        )
    if "bond" in text:
        notes.append(
            "Bond price/yield are explicit stubs: raise NotImplementedError or return "
            "BondStubStatus(status='stub') without pretending to compute real values."
        )
    if "probability" in text:
        notes.append(
            "Use documented pure-Python approximations; normal_cdf and inverse_normal_cdf "
            "must target absolute error <= 1e-7 on the supported input range."
        )
    if "financial golden" in text:
        notes.append("Golden tests must assert the documented bond stub status/error contract.")
    return notes


def _forbidden_dependencies(title: str) -> list[str]:
    forbidden = ["scipy", "numpy"]
    text = title.lower()
    if any(
        term in text
        for term in ("tvm", "npv", "irr", "probability", "statistics", "bond", "financial")
    ):
        forbidden.extend(["sympy", "mpmath"])
    return list(dict.fromkeys(forbidden))
