
from localforge.models import domain
from localforge.pipeline.engine import RolePipelineEngine
from localforge.visual.gate import validate_visual_html_structure
from localforge.visual.normalizer import apply_visual_contract_normalization


def test_visual_structure_rejects_nested_row_grid_for_spanning_key(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        """
        <style>
        .key-row { display:grid; grid-template-columns: repeat(10, 1fr); }
        .enter { grid-column: 6; grid-row: 3 / 5; }
        </style>
        <div class='key-row'></div><div class='key-row'></div>
        <div class='key-row'><div class='enter'>ENTER</div></div>
        <div class='key-row'></div>
        """,
        encoding="utf-8",
    )

    findings = validate_visual_html_structure(
        str(html),
        structure_rules=["single_parent_keypad_grid", "spanning_enter_key"],
    )

    assert any("nested row grids" in finding for finding in findings)


def test_visual_structure_accepts_single_parent_grid(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        """
        <style>
        .key-grid {
          display:grid;
          grid-template-columns: repeat(10, minmax(0, 1fr));
          grid-template-rows: repeat(4, minmax(0, 1fr));
        }
        .enter { grid-column: 6; grid-row: 3 / 5; }
        </style>
        <div class='key-grid'><div class='enter'>ENTER</div></div>
        """,
        encoding="utf-8",
    )

    assert validate_visual_html_structure(
        str(html),
        structure_rules=["single_parent_keypad_grid", "spanning_enter_key"],
    ) == []


def test_visual_structure_rejects_restrictive_calculator_width(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        "<style>.calculator { width: 100%; max-width: 900px; }</style>",
        encoding="utf-8",
    )

    findings = validate_visual_html_structure(
        str(html), structure_rules=["full_frame_physical_body"]
    )

    assert any("restrictive max-width" in finding for finding in findings)


def test_visual_structure_rejects_centered_lcd_and_round_badge(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        """
        <style>
        .lcd-container { display:flex; justify-content:center; }
        .hp-badge { border-radius:50%; }
        </style>
        """,
        encoding="utf-8",
    )

    findings = validate_visual_html_structure(
        str(html), structure_rules=["lcd_left_aligned", "rectangular_hp_badge"]
    )

    assert any("left-aligned" in finding for finding in findings)
    assert any("rectangular" in finding for finding in findings)


def test_visual_contract_normalizer_adds_scoped_overrides(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        "<html><head><style>.lcd-container { justify-content:center; } "
        ".hp-badge { border-radius:50%; }</style></head></html>",
        encoding="utf-8",
    )

    assert apply_visual_contract_normalization(
        str(html),
        structure_rules=["lcd_left_aligned", "rectangular_hp_badge"],
    )
    findings = validate_visual_html_structure(
        str(html), structure_rules=["lcd_left_aligned", "rectangular_hp_badge"]
    )

    assert findings == []
    assert html.read_text(encoding="utf-8").count("localforge-visual-contract-overrides") == 1


def test_visual_contract_normalizer_removes_restrictive_frame_cap(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        "<html><head><style>.calculator { max-width: 900px; }</style></head></html>",
        encoding="utf-8",
    )

    assert apply_visual_contract_normalization(
        str(html), structure_rules=["full_frame_physical_body"]
    )
    assert validate_visual_html_structure(
        str(html), structure_rules=["full_frame_physical_body"]
    ) == []


def _visual_task() -> domain.Task:
    return domain.Task(
        project_id=1,
        key="LF-VIS-001",
        title="Visual task",
        description="Preserve the complete visual application.",
        metadata={
            "task_contract": {
                "visual_required": True,
                "visual_actual_output": "frontend/app.html",
            }
        },
    )


def test_visual_reference_resolves_from_execution_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    worktree = workspace / ".localforge" / "worktrees" / "task"
    worktree.mkdir(parents=True)
    reference = workspace / "docs" / "reference.png"
    reference.parent.mkdir()
    reference.write_bytes(b"png")

    engine = object.__new__(RolePipelineEngine)
    (tmp_path / "unrelated").mkdir()
    monkeypatch.chdir(tmp_path / "unrelated")

    resolved = engine._resolve_visual_reference_path(str(worktree), "docs/reference.png")

    assert resolved == str(reference.resolve())


def test_visual_guard_rejects_destructive_html_replacement(tmp_path):
    worktree = tmp_path / "worktree"
    html_path = worktree / "frontend" / "app.html"
    html_path.parent.mkdir(parents=True)
    existing = "<html><style>body{color:black}</style><button>key</button>" + ("x" * 8000)
    html_path.write_text(existing, encoding="utf-8")

    engine = object.__new__(RolePipelineEngine)
    task = _visual_task()

    rejected = engine._visual_write_would_destroy_candidate(
        task=task,
        worktree_path=str(worktree),
        relative_path="frontend/app.html",
        content="<html><style></style><script></script></html>",
    )

    assert rejected is True
