from datetime import datetime

import pytest
from localforge.models.domain import Epic, Project, Task
from localforge.models.enums import TaskStatus
from pydantic import ValidationError


def test_project_model_validation():
    # Valid Project creation
    proj = Project(
        name="LocalForge OS",
        root_path="/path/to/project",
        default_branch="main",
    )
    assert proj.name == "LocalForge OS"
    assert proj.root_path == "/path/to/project"
    assert proj.default_branch == "main"
    assert isinstance(proj.created_at, datetime)
    assert proj.id is None

    # Invalid project (missing required fields)
    with pytest.raises(ValidationError):
        Project(root_path="/path/to/project")  # type: ignore


def test_task_model_defaults():
    task = Task(
        project_id=1,
        key="LF-0101",
        title="Define domain models",
        description="Write Pydantic models for domain entities",
    )
    assert task.status == TaskStatus.BACKLOG
    assert task.risk_level == "low"
    assert task.acceptance_criteria == []
    assert task.dependency_task_ids == []
    assert task.metadata == {}


def test_epic_model():
    epic = Epic(
        project_id=1,
        title="Foundation",
        summary="Set up core architecture",
    )
    assert epic.priority == 1
    assert epic.status == "BACKLOG"
    assert epic.acceptance_summary is None
