import os

import git
import pytest
from localforge.gitops import GitAdapter, WorktreeManager, get_task_branch_name
from localforge.models import domain
from localforge.models.enums import TaskStatus
from localforge.storage import UnitOfWork


def test_git_branch_naming():
    """Verify branch slug format generation."""
    branch = get_task_branch_name("LF-0601", "Add Worktree Isolation & Checks!")
    assert branch == "localforge/lf-0601-add-worktree-isolation-checks"

    # Very long title truncation
    long_title = "a" * 100
    branch_long = get_task_branch_name("LF-02", long_title)
    assert len(branch_long) <= 50  # localforge/lf-02- + 30 chars slug
    assert branch_long.startswith("localforge/lf-02-")


@pytest.fixture
def temp_git_repo(tmp_path):
    """Fixture initializing a clean-room temporary Git repository with an initial commit."""
    repo_dir = tmp_path / "main_repo"
    repo_dir.mkdir()

    # git init
    repo = git.Repo.init(repo_dir)
    repo.config_writer().set_value("user", "name", "LocalForge Test").set_value(
        "user", "email", "localforge-test@example.invalid"
    ).release()

    # Initial commit to create main branch and HEAD
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo")
    repo.index.add([str(readme)])
    repo.index.commit("initial commit")

    # Force main branch name in case default is different (e.g. master)
    try:
        repo.git.branch("-M", "main")
    except Exception:
        pass

    return repo_dir


@pytest.mark.anyio
async def test_git_adapter_and_checkpoints(temp_git_repo, db_session):
    """Verify GitAdapter commands and WorktreeManager checkpointing/rollback."""
    uow = UnitOfWork()
    uow.session = db_session

    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    # Register project
    proj_data = domain.Project(
        name="GitopsTest",
        root_path=str(temp_git_repo),
        default_branch="main",
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    task_data = domain.Task(
        project_id=project.id,
        key="LF-08",
        title="Checkpoints Task",
        description="Testing commit checkpoints",
    )
    task = await uow.tasks.create_task(task_data)
    assert task.id is not None

    # Register active run with worktree path
    from localforge.models.enums import TaskRunStatus
    task_run_data = domain.TaskRun(
        run_id=1,
        task_id=task.id,
        status=TaskRunStatus.RUNNING,
        worktree_path=str(temp_git_repo),  # Use main repo for simple checkpoint test
        branch_name="main",
    )
    await uow.tasks.create_task_run(task_run_data)
    await uow.session.commit()

    # 1. Test GitAdapter basic status
    adapter = GitAdapter(project_id=project.id, uow=uow, task_id=task.id)
    curr_branch = await adapter.current_branch()
    assert curr_branch == "main"

    # 2. Test WorktreeManager checkpointing
    manager = WorktreeManager(project_id=project.id, uow=uow)
    cp_hash = await manager.create_checkpoint(task.id, "initial_cp")
    assert len(cp_hash) == 40  # SHA-1 commit hash

    # Write a new file
    test_file = temp_git_repo / "new_file.txt"
    test_file.write_text("modified content")

    # Staged change status should be dirty
    status_out = await adapter.status()
    assert "new_file.txt" in status_out

    # 3. Rollback checkpoint
    await manager.rollback_checkpoint(task.id, cp_hash)

    # The new file should be deleted or untracked file cleaned
    assert not test_file.exists()


@pytest.mark.anyio
async def test_worktree_manager_setup_and_isolation(temp_git_repo, db_session):
    """Verify worktree setup creation and safety kernel filesystem boundary isolation."""
    uow = UnitOfWork()
    uow.session = db_session

    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService
    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    # Register project
    proj_data = domain.Project(
        name="IsolationTest",
        root_path=str(temp_git_repo),
        default_branch="main",
    )
    project = await uow.projects.create_project(proj_data)
    assert project.id is not None

    task_data = domain.Task(
        project_id=project.id,
        key="LF-09",
        title="Isolated Worktree Task",
        description="Testing path isolation",
    )
    task = await uow.tasks.create_task(task_data)
    assert task.id is not None

    # 1. Setup worktree
    manager = WorktreeManager(project_id=project.id, uow=uow)
    worktree_path, branch_name = await manager.setup_worktree(task.id)

    assert os.path.exists(worktree_path)
    assert branch_name == "localforge/lf-09-isolated-worktree-task"

    # Register active run with worktree path
    from localforge.models.enums import TaskRunStatus
    task_run_data = domain.TaskRun(
        run_id=1,
        task_id=task.id,
        status=TaskRunStatus.RUNNING,
        worktree_path=worktree_path,
        branch_name=branch_name,
    )
    await uow.tasks.create_task_run(task_run_data)
    await uow.session.commit()

    # 2. Test filesystem boundary isolation:
    # A write target inside the active task's worktree should be ALLOWED.
    safe_write_file = os.path.join(worktree_path, "worktree_file.txt")

    # Execute a safe shell write (echo test > file)
    # We must use safe execution
    from localforge.models.enums import ActionKind
    from localforge.safety import ActionRequest, SafetyDecision, SafetyKernel

    req_safe = ActionRequest(
        project_id=project.id,
        task_id=task.id,
        kind=ActionKind.WRITE_FILE,
        payload={"path": safe_write_file},
        purpose="Writing inside worktree boundary",
    )
    # Inside run_safe_command or SafetyKernel:
    # Evaluating path safety: project_root will be overridden to worktree_path
    decision, reason = await SafetyKernel.evaluate(req_safe, uow, worktree_path)
    assert decision == SafetyDecision.ALLOW

    # A write target pointing to the main project repository root should be DENIED!
    unsafe_write_file = os.path.join(str(temp_git_repo), "main_file.txt")
    req_unsafe = ActionRequest(
        project_id=project.id,
        task_id=task.id,
        kind=ActionKind.WRITE_FILE,
        payload={"path": unsafe_write_file},
        purpose="Writing outside worktree boundary",
    )
    # Since uow active task run is bound to worktree_path,
    # evaluating with worktree_path as project_root
    decision_unsafe, reason_unsafe = await SafetyKernel.evaluate(req_unsafe, uow, worktree_path)
    assert decision_unsafe == SafetyDecision.DENY
    assert "outside workspace root" in reason_unsafe

    # 3. Cleanup worktree:
    # Task needs to be in final state
    await uow.tasks.update_task_status(task.id, TaskStatus.READY)
    await uow.tasks.update_task_status(task.id, TaskStatus.CLAIMED)
    await uow.tasks.update_task_status(task.id, TaskStatus.PLANNING)
    await uow.tasks.update_task_status(task.id, TaskStatus.IMPLEMENTING)
    await uow.tasks.update_task_status(task.id, TaskStatus.TESTING)
    await uow.tasks.update_task_status(task.id, TaskStatus.REVIEWING)
    await uow.tasks.update_task_status(task.id, TaskStatus.PR_READY)
    await uow.tasks.update_task_status(task.id, TaskStatus.DONE)
    await uow.session.commit()

    # Now clean up
    await manager.cleanup_worktree(task.id)
    assert not os.path.exists(worktree_path)


@pytest.mark.anyio
async def test_worktree_manager_replaces_stale_task_worktree_path(temp_git_repo, db_session):
    uow = UnitOfWork()
    uow.session = db_session

    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService

    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="StaleWorktree", root_path=str(temp_git_repo), default_branch="main")
    )
    assert project.id is not None
    task = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-12",
            title="Replace stale path",
            description="Create worktree after stale directory from an old run.",
        )
    )
    assert task.id is not None

    stale_path = temp_git_repo / ".localforge" / "worktrees" / "lf-12"
    stale_path.mkdir(parents=True)
    (stale_path / "stale.txt").write_text("old", encoding="utf-8")

    manager = WorktreeManager(project_id=project.id, uow=uow, run_id=77)
    worktree_path, branch_name = await manager.setup_worktree(task.id)

    assert worktree_path == os.path.realpath(os.path.abspath(stale_path))
    assert branch_name.endswith("-run-77")
    assert os.path.exists(worktree_path)
    assert not (stale_path / "stale.txt").exists()
    assert (stale_path / ".git").exists()


@pytest.mark.anyio
async def test_worktree_manager_uses_ready_dependency_branch_as_base(temp_git_repo, db_session):
    uow = UnitOfWork()
    uow.session = db_session

    from localforge.models.enums import TaskRunStatus
    from localforge.services.audit import AuditService
    from localforge.services.project import ProjectService
    from localforge.services.safety import SafetyService
    from localforge.services.task import TaskService

    uow.projects = ProjectService(db_session)
    uow.tasks = TaskService(db_session)
    uow.audits = AuditService(db_session)
    uow.safety = SafetyService(db_session)

    project = await uow.projects.create_project(
        domain.Project(name="StackedPRs", root_path=str(temp_git_repo), default_branch="main")
    )
    assert project.id is not None
    dependency = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-10",
            title="Base scaffold",
            description="Create shared base files",
        )
    )
    assert dependency.id is not None
    child = await uow.tasks.create_task(
        domain.Task(
            project_id=project.id,
            key="LF-11",
            title="Feature work",
            description="Build on the base scaffold",
            dependency_task_ids=[dependency.id],
        )
    )
    assert child.id is not None

    manager = WorktreeManager(project_id=project.id, uow=uow)
    dep_worktree, dep_branch = await manager.setup_worktree(dependency.id)
    base_file = os.path.join(dep_worktree, "calculator", "__init__.py")
    os.makedirs(os.path.dirname(base_file), exist_ok=True)
    with open(base_file, "w", encoding="utf-8") as handle:
        handle.write("BASE = True\n")
    dep_repo = git.Repo(dep_worktree)
    dep_repo.index.add(["calculator/__init__.py"])
    dep_repo.index.commit("LF-10: base scaffold")

    await uow.tasks.create_task_run(
        domain.TaskRun(
            run_id=1,
            task_id=dependency.id,
            status=TaskRunStatus.COMPLETED,
            worktree_path=dep_worktree,
            branch_name=dep_branch,
        )
    )
    await uow.tasks.update_task_status(dependency.id, TaskStatus.READY)
    await uow.tasks.update_task_status(dependency.id, TaskStatus.CLAIMED)
    await uow.tasks.update_task_status(dependency.id, TaskStatus.PLANNING)
    await uow.tasks.update_task_status(dependency.id, TaskStatus.IMPLEMENTING)
    await uow.tasks.update_task_status(dependency.id, TaskStatus.TESTING)
    await uow.tasks.update_task_status(dependency.id, TaskStatus.REVIEWING)
    await uow.tasks.update_task_status(dependency.id, TaskStatus.PR_READY)
    await uow.session.commit()

    child_worktree, child_branch = await manager.setup_worktree(child.id)

    assert child_branch == "localforge/lf-11-feature-work"
    assert os.path.exists(os.path.join(child_worktree, "calculator", "__init__.py"))
