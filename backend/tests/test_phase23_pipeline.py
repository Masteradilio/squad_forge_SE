import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.models import domain
from localforge.models.enums import (
    AgentRole,
    HandoffKind,
    RunMode,
    RunStatus,
    TaskStatus,
)
from localforge.pipeline import PIPELINES, PipelineMode, RolePipelineEngine
from localforge.pipeline.context import RoleContextBuilder
from localforge.runtime.handoffs import RuntimeHandoffService
from localforge.runtime.actions import RuntimeActionProposal
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager


def test_phase23_pipeline_modes_match_backlog_sequences():
    assert PIPELINES[PipelineMode.FAST] == (
        AgentRole.CODER,
        AgentRole.TESTER,
        AgentRole.REVIEWER,
        AgentRole.PR_WRITER,
    )
    assert PIPELINES[PipelineMode.DEFAULT][0] == AgentRole.PLANNER
    assert PIPELINES[PipelineMode.DEFAULT][-1] == AgentRole.PR_WRITER
    assert AgentRole.CLEANER in PIPELINES[PipelineMode.STRICT]
    assert AgentRole.QA in PIPELINES[PipelineMode.STRICT]


def test_node_eval_html_harness_uses_detectable_argument_slot():
    broken = '''
result = subprocess.run(["node", "-e", script, str(HTML)], check=True)
html = fs.readFileSync(process.argv[2], "utf8")
'''
    valid = '''
result = subprocess.run(["node", "-e", script, str(HTML)], check=True)
html = fs.readFileSync(process.argv[1], "utf8")
'''

    assert RolePipelineEngine._has_node_eval_html_arg_slot(broken) is True
    assert RolePipelineEngine._has_node_eval_html_arg_slot(valid) is False


def test_role_context_includes_recent_human_review_comments(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(manager, tmp_path)

        async def exercise() -> str:
            async with UnitOfWork(manager) as uow:
                assert uow.projects is not None
                assert uow.tasks is not None
                assert uow.coordination is not None
                task = await uow.tasks.get_task(ids["task_id"])
                project = await uow.projects.get_project(ids["project_id"])
                task_run = await uow.tasks.get_task_run(ids["task_run_id"])
                assert task is not None
                assert project is not None
                assert task_run is not None
                await uow.coordination.add_task_comment(
                    domain.TaskComment(
                        project_id=ids["project_id"],
                        task_id=ids["task_id"],
                        author="human-reviewer",
                        body="Do not invent a financial module; import the real product API.",
                    )
                )
                context = await RoleContextBuilder(uow).build(
                    project=project,
                    task=task,
                    task_run=task_run,
                    role=AgentRole.CODER,
                    consumed_handoffs=[],
                )
                return context.rendered

        rendered = asyncio.run(exercise())

        assert "Recent comments:" in rendered
        assert "human-reviewer" in rendered
        assert "Do not invent a financial module" in rendered
    finally:
        close_manager(manager)


def test_default_role_pipeline_completes_sample_task(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(manager, tmp_path)

        async def exercise() -> dict[str, object]:
            async with UnitOfWork(manager) as uow:
                result = await RolePipelineEngine(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                ).run_task(
                    task_id=ids["task_id"],
                    task_run_id=ids["task_run_id"],
                    mode=PipelineMode.DEFAULT,
                )
                assert uow.tasks is not None
                task = await uow.tasks.get_task(ids["task_id"])
                assert task is not None
                return {
                    "status": task.status.value,
                    "roles": [role.value for role in result.roles],
                    "artifacts": result.artifact_paths,
                    "pr": result.pr_artifact_path,
                }

        data = asyncio.run(exercise())

        assert data["status"] == TaskStatus.PR_READY.value
        assert data["roles"] == [role.value for role in PIPELINES[PipelineMode.DEFAULT]]
        assert any(str(path).endswith("role-planner.md") for path in data["artifacts"])
        assert str(data["pr"]).endswith("pr.md")
    finally:
        close_manager(manager)


def test_role_pipeline_repairs_generated_pytest_failure(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(
            manager,
            tmp_path,
            metadata={
                "runtime_actions": json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "calculator/__init__.py",
                                "content": "",
                            },
                            {
                                "kind": "write_file",
                                "path": "calculator/app.py",
                                "content": "def add(a, b):\n    return a + b\n",
                            },
                            {
                                "kind": "write_file",
                                "path": "tests/test_calculator.py",
                                "content": "from calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                            },
                        ]
                    }
                )
            },
        )

        class RepairingEngine(RolePipelineEngine):
            async def _request_repair_actions(self, **kwargs) -> str:
                return json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "calculator/__init__.py",
                                "content": "from .app import add\n",
                            }
                        ]
                    }
                )

        async def exercise() -> dict[str, object]:
            async with UnitOfWork(manager) as uow:
                result = await RepairingEngine(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                ).run_task(
                    task_id=ids["task_id"],
                    task_run_id=ids["task_run_id"],
                    mode=PipelineMode.DEFAULT,
                )
                assert uow.tasks is not None
                task = await uow.tasks.get_task(ids["task_id"])
                assert task is not None
                return {
                    "status": task.status.value,
                    "pr": result.pr_artifact_path,
                    "changed_files": task.metadata.get("changed_files", []),
                }

        data = asyncio.run(exercise())

        assert data["status"] == TaskStatus.PR_READY.value
        assert str(data["pr"]).endswith("pr.md")
        assert "calculator/__init__.py" in data["changed_files"]
    finally:
        close_manager(manager)


def test_role_pipeline_ignores_pytest_repair_that_rewrites_tests(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(
            manager,
            tmp_path,
            metadata={
                "runtime_actions": json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "calculator/__init__.py",
                                "content": "",
                            },
                            {
                                "kind": "write_file",
                                "path": "tests/test_calculator.py",
                                "content": "from calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                            },
                        ]
                    }
                )
            },
        )

        class TestRewritingEngine(RolePipelineEngine):
            async def _request_repair_actions(self, **kwargs) -> str:
                return json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "tests/test_calculator.py",
                                "content": "; invalid repair\n",
                            }
                        ]
                    }
                )

        async def exercise() -> str:
            async with UnitOfWork(manager) as uow:
                try:
                    await TestRewritingEngine(
                        uow, project_id=ids["project_id"], run_id=ids["run_id"]
                    ).run_task(
                        task_id=ids["task_id"],
                        task_run_id=ids["task_run_id"],
                        mode=PipelineMode.DEFAULT,
                    )
                except ValueError:
                    test_path = tmp_path / "tests" / "test_calculator.py"
                    return test_path.read_text(encoding="utf-8")
                raise AssertionError("Pipeline should fail because repair only rewrites tests.")

        content = asyncio.run(exercise())
        validation_artifact = (
            tmp_path
            / ".localforge"
            / "artifacts"
            / "runs"
            / str(ids["run_id"])
            / "tasks"
            / "lf-2301"
            / "tests.md"
        )

        assert "; invalid repair" not in content
        assert "assert add(2, 3) == 5" in content
        assert "Validation Failure" in validation_artifact.read_text(encoding="utf-8")
    finally:
        close_manager(manager)


def test_role_pipeline_repairs_invalid_generated_python_before_pytest(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(
            manager,
            tmp_path,
            metadata={
                "runtime_actions": json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "calculator/__init__.py",
                                "content": "from .broken import answer\n",
                            },
                            {
                                "kind": "write_file",
                                "path": "calculator/broken.py",
                                "content": "def answer(:\n",
                            },
                            {
                                "kind": "write_file",
                                "path": "tests/test_broken.py",
                                "content": "from calculator import answer\n\n\ndef test_answer():\n    assert answer() == 42\n",
                            },
                        ]
                    }
                )
            },
        )

        class SyntaxRepairingEngine(RolePipelineEngine):
            validation_outputs: list[str] = []

            async def _request_repair_actions(self, **kwargs) -> str:
                self.validation_outputs.append(str(kwargs["validation_output"]))
                return json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "calculator/broken.py",
                                "content": "def answer():\n    return 42\n",
                            }
                        ]
                    }
                )

        async def exercise() -> dict[str, object]:
            async with UnitOfWork(manager) as uow:
                engine = SyntaxRepairingEngine(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                )
                await engine.run_task(
                    task_id=ids["task_id"],
                    task_run_id=ids["task_run_id"],
                    mode=PipelineMode.DEFAULT,
                )
                assert uow.tasks is not None
                task = await uow.tasks.get_task(ids["task_id"])
                assert task is not None
                return {
                    "status": task.status.value,
                    "validation_outputs": engine.validation_outputs,
                }

        data = asyncio.run(exercise())

        assert data["status"] == TaskStatus.PR_READY.value
        assert "Python syntax validation failed before pytest" in str(data["validation_outputs"][0])
    finally:
        close_manager(manager)


def test_role_pipeline_filters_missing_changed_files_before_commit(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(manager, tmp_path)
        existing = tmp_path / "calculator" / "core.py"
        existing.parent.mkdir()
        existing.write_text("class Calculator:\n    pass\n", encoding="utf-8")

        async def exercise() -> list[str]:
            async with UnitOfWork(manager) as uow:
                return RolePipelineEngine(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                )._existing_changed_files(
                    str(tmp_path),
                    ["calculator/core.py", "tests/__init__.py", "../outside.py"],
                )

        assert asyncio.run(exercise()) == ["calculator/core.py"]
    finally:
        close_manager(manager)


def test_role_pipeline_blocks_writes_outside_task_contract(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(
            manager,
            tmp_path,
            metadata={
                "task_contract": {
                    "allowed_files": ["allowed.py"],
                    "canonical_test_command": "python -m pytest -q",
                },
                "runtime_actions": json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "outside.py",
                                "content": "VALUE = 1\n",
                            }
                        ]
                    }
                ),
            },
        )

        async def exercise() -> str:
            async with UnitOfWork(manager) as uow:
                await RolePipelineEngine(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                ).run_task(
                    task_id=ids["task_id"],
                    task_run_id=ids["task_run_id"],
                    mode=PipelineMode.DEFAULT,
                )
                assert uow.tasks is not None
                task = await uow.tasks.get_task(ids["task_id"])
                assert task is not None
                return task.status.value

        assert asyncio.run(exercise()) == TaskStatus.FAILED_SAFE.value
        assert not (tmp_path / "outside.py").exists()
    finally:
        close_manager(manager)


def test_role_pipeline_sanitizes_generated_test_markdown_noise(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(
            manager,
            tmp_path,
            metadata={
                "runtime_actions": json.dumps(
                    {
                        "actions": [
                            {
                                "kind": "write_file",
                                "path": "calculator/__init__.py",
                                "content": "def add(a, b):\n    return a + b\n",
                            },
                            {
                                "kind": "write_file",
                                "path": "tests/test_calculator.py",
                                "content": '```python\n;"""test module"""\nfrom calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n```\n',
                            },
                        ]
                    }
                )
            },
        )

        async def exercise() -> dict[str, object]:
            async with UnitOfWork(manager) as uow:
                await RolePipelineEngine(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                ).run_task(
                    task_id=ids["task_id"],
                    task_run_id=ids["task_run_id"],
                    mode=PipelineMode.DEFAULT,
                )
                assert uow.tasks is not None
                task = await uow.tasks.get_task(ids["task_id"])
                assert task is not None
                content = (tmp_path / "tests" / "test_calculator.py").read_text(encoding="utf-8")
                return {"status": task.status.value, "content": content}

        data = asyncio.run(exercise())

        assert data["status"] == TaskStatus.PR_READY.value
        assert "```" not in str(data["content"])
        assert str(data["content"]).startswith('"""test module"""')
    finally:
        close_manager(manager)


def test_role_pipeline_python_sanitizer_preserves_dict_closing_braces():
    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    sanitized = engine._sanitize_python_content("SEGMENTS = {\n    1: ['   ', '  |', '  |'],\n}\n")

    assert sanitized == ("SEGMENTS = {\n    1: ['   ', '  |', '  |'],\n}\n")


def test_role_pipeline_python_sanitizer_drops_only_unmatched_lone_braces():
    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    sanitized = engine._sanitize_python_content("def test_ok():\n    assert True\n}\n")

    assert sanitized == "def test_ok():\n    assert True\n"


def test_generated_static_html_acceptance_test_is_marked_for_one_qa_repair(tmp_path):
    test_file = tmp_path / "tests" / "test_export.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "html = open('app/index.html', encoding='utf-8').read()\n"
        "def test_export():\n"
        "    assert 'function exportSummary' in html\n"
        "    assert 'outputEl.value = exportSummary()' in html\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_pytest_fixture_called_directly_is_marked_for_harness_repair(tmp_path):
    test_file = tmp_path / "tests" / "test_product.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "def test_product():\n"
        "    page_js()\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._acceptance_test_needs_remediation(
        str(test_file),
        validation_output=(
            'Fixture "page_js" called directly. Fixtures are not meant to be '
            "called directly"
        ),
    ) is True


def test_empty_acceptance_repair_action_is_rejected(tmp_path):
    test_file = tmp_path / "tests" / "test_product.py"
    test_file.parent.mkdir()
    test_file.write_text("\n", encoding="utf-8")
    proposal = RuntimeActionProposal(
        kind="write_file", path="tests/test_product.py", content=" \n"
    )

    assert RolePipelineEngine._proposal_would_empty_file(
        proposal, str(test_file)
    ) is True
    assert RolePipelineEngine._has_empty_acceptance_test(str(tmp_path)) is True

    proposal = RuntimeActionProposal(
        kind="append_content",
        path="tests/test_product.py",
        content="def test_ok():\n    assert True\n",
    )
    assert RolePipelineEngine._proposal_would_empty_file(
        proposal, str(test_file)
    ) is False


def test_canonical_test_path_is_derived_from_task_contract():
    task = type(
        "ContractTask",
        (),
        {
            "metadata": {
                "task_contract": {
                    "canonical_test_command": (
                        "python -m pytest tests/test_tvm_solver.py -q"
                    )
                }
            }
        },
    )()

    assert RolePipelineEngine._canonical_test_paths(task) == [
        "tests/test_tvm_solver.py"
    ]


def test_behavioral_html_acceptance_test_is_not_marked_as_static_only(tmp_path):
    test_file = tmp_path / "tests" / "test_export.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import subprocess\n"
        "def test_export():\n"
        "    result = subprocess.run(['node', 'tests/export.js'], check=True)\n"
        "    assert result.returncode == 0\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is False
    assert engine._acceptance_test_needs_remediation(str(test_file)) is False


def test_html_parser_and_copied_node_algorithm_are_untrusted_acceptance_evidence(tmp_path):
    test_file = tmp_path / "tests" / "test_export.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "from html.parser import HTMLParser\n"
        "import subprocess\n"
        "def test_export():\n"
        "    content = open('app/index.html').read()\n"
        "    assert 'id=\\\"exportBtn\\\"' in content\n"
        "    node = 'function exportSummary() { let items = [] }'\n"
        "    subprocess.run(['node', '-e', node], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_self_contained_html_product_stub_is_untrusted_acceptance_evidence(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import os\n"
        "TEST_DIR = os.path.dirname(os.path.abspath(__file__))\n"
        "INDEX_PATH = os.path.join(TEST_DIR, '..', 'app', 'index.html')\n"
        "class RPNStack:\n"
        "    def __init__(self):\n"
        "        self.x = 0.0\n"
        "    def roll_down(self):\n"
        "        self.x = 1.0\n"
        "def get_stack():\n"
        "    with open(INDEX_PATH, encoding='utf-8') as handle:\n"
        "        handle.read()\n"
        "    return RPNStack()\n"
        "def test_roll_down():\n"
        "    stack = get_stack()\n"
        "    stack.roll_down()\n"
        "    assert stack.x == 1.0\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_python_import_of_html_entrypoint_is_untrusted_acceptance_evidence(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "from app.index import Calculator\n"
        "def test_stack():\n"
        "    assert Calculator().x == 0\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_python_import_of_missing_html_app_module_is_untrusted(tmp_path):
    test_file = tmp_path / "tests" / "test_tvm.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "from app.tvm_solver import tvm_solver\n"
        "def test_tvm():\n"
        "    assert tvm_solver(PV=1)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_html_acceptance_selectors_must_exist_in_product_dom(tmp_path):
    app_dir = tmp_path / "app"
    tests_dir = tmp_path / "tests"
    app_dir.mkdir()
    tests_dir.mkdir()
    (app_dir / "index.html").write_text(
        '<div id="display"></div><button id="toggle">Toggle</button>',
        encoding="utf-8",
    )
    test_file = tests_dir / "test_alg.py"
    test_file.write_text(
        "from playwright.sync_api import sync_playwright\n"
        "def test_alg(page):\n"
        "    page.click(\"[data-key='g']\")\n"
        "    assert page.locator('#display').input_value() == 'ALG'\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_html_harness_must_use_exposed_calculator_api(tmp_path):
    app_dir = tmp_path / "app"
    tests_dir = tmp_path / "tests"
    app_dir.mkdir()
    tests_dir.mkdir()
    (app_dir / "index.html").write_text(
        "<script>globalThis.CalculatorApp={press(){},getRegister(){return 0;}};</script>",
        encoding="utf-8",
    )
    test_file = tests_dir / "test_memory.py"
    test_file.write_text(
        "import subprocess\n"
        "STORE_NAMES = ['sto', 'store']\n"
        "RECALL_NAMES = ['rcl', 'recall']\n"
        "if typeof global[candidate] == 'function': pass\n"
        "subprocess.run(['node', 'harness.js', 'app/index.html'], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_python_fstring_must_escape_node_template_interpolation(tmp_path):
    test_file = tmp_path / "tests" / "test_memory.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import subprocess\n"
        "APP_HTML = 'app/index.html'\n"
        "def build():\n"
        "    return f'''const run = (key) => `Unhandled key: ${key}`;'''\n"
        "subprocess.run(['node', '-e', build(), APP_HTML], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_fstring_node_template_mismatch(test_file.read_text()) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_python_cannot_import_embedded_es_module_as_python(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import importlib.util\n"
        "APP_HTML = 'app/index.html'\n"
        "assert 'export function createRpnStack' in APP_HTML\n"
        "spec = importlib.util.spec_from_file_location('rpn', 'app/index.mjs')\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_cross_language_js_import_harness(test_file.read_text()) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_html_acceptance_cannot_fallback_to_a_python_product_simulation(tmp_path):
    test_file = tmp_path / "tests" / "test_alg.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import subprocess\n"
        "PRODUCT = 'app/index.html'\n"
        "class CalculatorCoreProxy:\n"
        "    def _rpn_operation(self, op):\n"
        "        self._stack.append(1)\n"
        "    def _fallback_evaluate(self, expr):\n"
        "        return 14\n"
        "subprocess.run(['node', '-e', '...'], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_self_contained_html_fallback(test_file.read_text()) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_html_harness_cannot_mutate_unexported_internal_stack(tmp_path):
    app_dir = tmp_path / "app"
    tests_dir = tmp_path / "tests"
    app_dir.mkdir()
    tests_dir.mkdir()
    (app_dir / "index.html").write_text(
        "<script>const stack=[];</script>", encoding="utf-8"
    )
    test_file = tests_dir / "test_rpn.py"
    test_file.write_text(
        "import subprocess\n"
        "APP_HTML = 'app/index.html'\n"
        "DRIVER = 'eval(source); for (const op of ops) stack.push(op)'\n"
        "subprocess.run(['node', '-e', DRIVER, APP_HTML], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_html_internal_state_harness(
        str(tmp_path), test_file.read_text()
    ) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_placeholder_html_harness_is_eligible_for_qa_repair(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "APP_HTML = 'app/index.html'\n"
        "HARNESS_JS = '...stack harness...'\n"
        "def _build_harness():\n"
        "    return HARNESS_JS\n"
        "def _run_harness():\n"
        "    # placeholder body to satisfy py_compile\n"
        "    return None\n"
        "def test_stack_api(stack_api):\n"
        "    assert stack_api\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_placeholder_html_harness(test_file.read_text()) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_vm_harness_global_scope_mismatch_is_untrusted_acceptance_evidence(tmp_path):
    test_file = tmp_path / "tests" / "test_calculator.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "APP_HTML = open('app/index.html', encoding='utf-8').read()\n"
        "NODE_HARNESS = 'const calc = sandbox.window.Calculator; vm.runInContext(test_expr, sandbox)'\n"
        "def test_calculator():\n"
        "    test_expr = \"({result: Calculator.evaluate('2+2')})\"\n"
        "    assert 'window.Calculator' in NODE_HARNESS\n"
        "    assert 'vm.runInContext' in NODE_HARNESS\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_node_json_parse_of_html_is_untrusted_acceptance_evidence(tmp_path):
    test_file = tmp_path / "tests" / "test_calculator.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import subprocess\n"
        "APP_HTML = 'app/index.html'\n"
        "NODE_SCRIPT = 'const source = JSON.parse(fs.readFileSync(process.argv[1], \\\"utf8\\\"));'\n"
        "def test_calculator():\n"
        "    subprocess.run(['node', '-e', NODE_SCRIPT, APP_HTML], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_node_eval_of_inline_html_script_without_browser_scope_is_untrusted(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import subprocess\n"
        "APP_HTML = 'app/index.html'\n"
        "NODE_HARNESS = 'const scriptMatch = html.match(/<script>([\\\\s\\\\S]*?)<\\\\\\\\/script>/); const wrapped = scriptMatch[1]; const Stack = eval(wrapped)'\n"
        "def test_stack():\n"
        "    subprocess.run(['node', '-e', NODE_HARNESS, APP_HTML], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_python_source_assertion_harness_for_html_is_untrusted(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import ast\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "APP_HTML = Path('app/index.html')\n"
        "def test_stack():\n"
        "    ast.parse(APP_HTML.read_text())\n"
        "    subprocess.run(['node', '-e', 'class RPNStack: def push(self): pass'], check=True)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_node_eval_scope_and_callable_result_harness_is_untrusted(tmp_path):
    test_file = tmp_path / "tests" / "test_rpn.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "import subprocess\n"
        "APP_HTML = 'app/index.html'\n"
        "def _run_js(script):\n"
        "    return {}\n"
        "def test_stack():\n"
        "    subprocess.run(['node', '-e', 'eval(script); if (typeof RpnStack === \\\"undefined\\\") {}'], check=True)\n"
        "    return _run_js(full_js)(ops)\n",
        encoding="utf-8",
    )

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._has_untrusted_static_acceptance_test(str(tmp_path)) is True
    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_empty_acceptance_test_is_eligible_for_qa_materialization(tmp_path):
    test_file = tmp_path / "tests" / "test_empty.py"
    test_file.parent.mkdir()
    test_file.write_text("\n", encoding="utf-8")

    engine = RolePipelineEngine.__new__(RolePipelineEngine)

    assert engine._acceptance_test_needs_remediation(str(test_file)) is True


def test_acceptance_fixture_target_is_protected_for_normalized_paths():
    task = domain.Task(
        project_id=1,
        key="LF-TEST-001",
        title="Fixture",
        description="Fixture",
        metadata={
            "task_contract": {
                "acceptance_test_fixture_target": "tests/test_mini_checklist.py"
            }
        },
    )

    assert RolePipelineEngine._is_acceptance_fixture_path(
        task, r".\tests\test_mini_checklist.py"
    ) is True
    assert RolePipelineEngine._is_acceptance_fixture_path(
        task, "worktree/tests/test_mini_checklist.py"
    ) is True
    assert RolePipelineEngine._is_acceptance_fixture_path(task, "tests/other.py") is False


def test_generated_html_vm_harness_mismatch_is_classified_as_qa(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    Path(tests_dir / "test_product.py").write_text(
        "html = open('app/index.html').read()\n"
        "vm.runInContext(html, sandbox)\n",
        encoding="utf-8",
    )

    assert RolePipelineEngine._has_generated_html_vm_harness_mismatch(
        str(tmp_path), "SyntaxError: Unexpected token '<'"
    ) is True

    Path(tests_dir / "test_product.py").write_text(
        "html = open('app/index.html').read()\n"
        "subprocess.run(['node', '-e', html], check=True)\n",
        encoding="utf-8",
    )
    assert RolePipelineEngine._has_generated_html_vm_harness_mismatch(
        str(tmp_path), "CalledProcessError: Node failed on <!DOCTYPE html>"
    ) is True

    Path(tests_dir / "test_product.py").write_text(
        "html = Path('app/index.html').read_text()\n"
        "assert 'document.getElementById(\"cf0\")' in html\n",
        encoding="utf-8",
    )
    assert RolePipelineEngine._has_brittle_html_acceptance_harness(str(tmp_path)) is True

    Path(tests_dir / "test_product.py").write_text(
        "import subprocess\n"
        "APP_INDEX = 'app/index.html'\n"
        "JS_CODE = 'const htmlPath = process.argv[2];'\n"
        "subprocess.run(['node', '-e', JS_CODE, APP_INDEX], check=True)\n",
        encoding="utf-8",
    )
    engine = RolePipelineEngine.__new__(RolePipelineEngine)
    assert engine._acceptance_test_needs_remediation(
        str(tests_dir / "test_product.py")
    ) is True


def test_handoffs_are_consumed_once_in_priority_order(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(manager, tmp_path)

        async def exercise() -> tuple[list[int], str]:
            async with UnitOfWork(manager) as uow:
                assert uow.executions is not None
                await uow.executions.create_handoff(
                    domain.Handoff(
                        task_run_id=ids["task_run_id"],
                        from_role=AgentRole.PLANNER,
                        to_role=AgentRole.CODER,
                        kind=HandoffKind.PLAN,
                        priority=1,
                    )
                )
                await uow.executions.create_handoff(
                    domain.Handoff(
                        task_run_id=ids["task_run_id"],
                        from_role=AgentRole.SPECIFIER,
                        to_role=AgentRole.CODER,
                        kind=HandoffKind.PLAN,
                        priority=5,
                    )
                )
                pending = await uow.executions.list_pending_handoffs(AgentRole.CODER)
                service = RuntimeHandoffService(
                    uow, project_id=ids["project_id"], run_id=ids["run_id"]
                )
                consumed = await service.consume_once(pending[0].id)
                try:
                    await service.consume_once(consumed.id)
                except ValueError as exc:
                    error = str(exc)
                else:
                    error = ""
                return [h.id or 0 for h in pending], error

        ordered_ids, error = asyncio.run(exercise())

        assert ordered_ids[0] > ordered_ids[1]
        assert "already been consumed" in error
    finally:
        close_manager(manager)


def test_model_routing_and_memory_api_persist_backups(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_pipeline_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        route = client.put(
            f"/projects/{ids['project_id']}/model-routes",
            json={
                "role": "Coder",
                "provider": "omniroute",
                "model_profile_id": "auto/best-coding-fast",
                "endpoint_url": "http://localhost:20128/v1",
            },
        )
        assert route.status_code == 200
        assert route.json()["model_profile_id"] == "auto/best-coding-fast"
        assert (
            client.get(f"/projects/{ids['project_id']}/model-routes").json()[0]["role"] == "Coder"
        )

        fact = client.post(
            f"/projects/{ids['project_id']}/memory",
            json={"fact": "Use targeted tests first", "pinned": True, "tags": ["testing"]},
        )
        assert fact.status_code == 200
        exported = client.get(f"/projects/{ids['project_id']}/memory/export?format=json")
        assert "Use targeted tests first" in exported.text

        payload = json.loads(exported.text)
        imported = client.post(
            f"/projects/{ids['project_id']}/memory/import",
            json={"format": "json", "payload": payload},
        )
        assert imported.status_code == 200
        assert imported.json()[0]["fact"] == "Use targeted tests first"
    finally:
        close_manager(manager)


def make_db_manager(tmp_path) -> DatabaseManager:
    manager = DatabaseManager(f"sqlite+aiosqlite:///{(tmp_path / 'phase23.db').as_posix()}")
    asyncio.run(bootstrap_database(manager))
    return manager


def close_manager(manager: DatabaseManager) -> None:
    asyncio.run(manager.close())


def seed_pipeline_state(
    db_manager: DatabaseManager,
    tmp_path,
    metadata: dict[str, object] | None = None,
    title: str = "Pipeline",
    description: str = "Complete sample pipeline",
) -> dict[str, int]:
    async def seed() -> dict[str, int]:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            assert uow.tasks is not None
            assert uow.executions is not None
            project = await uow.projects.create_project(
                domain.Project(name="Phase 23", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            task_metadata: dict[str, object] = {
                "changed_files": ["src/sample.py"],
                "source_commit": "source-commit",
                "target_commit": "target-commit",
            }
            if metadata:
                task_metadata.update(metadata)
            task = await uow.tasks.create_task(
                domain.Task(
                    project_id=project.id,
                    key="LF-2301",
                    title=title,
                    description=description,
                    status=TaskStatus.READY,
                    acceptance_criteria=["PR artifact is ready"],
                    metadata=task_metadata,
                )
            )
            assert task.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.INTERACTIVE,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                )
            )
            assert run.id is not None
            task_run = await uow.tasks.create_task_run(
                domain.TaskRun(
                    run_id=run.id,
                    task_id=task.id,
                    worktree_path=str(tmp_path),
                    branch_name="localforge/lf-2301",
                )
            )
            assert task_run.id is not None
            return {
                "project_id": project.id,
                "task_id": task.id,
                "run_id": run.id,
                "task_run_id": task_run.id,
            }

    return asyncio.run(seed())
