from pathlib import Path

from localforge.cli.init import WORKSPACE_SUBDIRECTORIES, ensure_workspace_layout


def test_ensure_workspace_layout_repairs_partial_workspace(tmp_path: Path):
    workspace = tmp_path / ".localforge"
    (workspace / "policies").mkdir(parents=True)

    created = ensure_workspace_layout(str(workspace))

    assert created is False
    assert all((workspace / directory).is_dir() for directory in WORKSPACE_SUBDIRECTORIES)
