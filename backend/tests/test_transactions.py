import pytest
from localforge.models import domain
from localforge.services.project import ProjectService
from localforge.storage import DatabaseManager, UnitOfWork


@pytest.mark.asyncio
async def test_unit_of_work_commit(db_manager: DatabaseManager):
    """Test that UnitOfWork commits transaction changes on success."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        proj = await uow.projects.create_project(
            domain.Project(name="UOW Proj", root_path="/uow/path", default_branch="main")
        )
        assert proj.id is not None

    # Open a new session to verify the project was committed
    async with await db_manager.get_session() as session:
        service = ProjectService(session)
        fetched = await service.get_project(proj.id)
        assert fetched is not None
        assert fetched.name == "UOW Proj"


@pytest.mark.asyncio
async def test_unit_of_work_rollback(db_manager: DatabaseManager):
    """Test that UnitOfWork rolls back transaction changes if an exception occurs."""
    proj_id = None
    try:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            proj = await uow.projects.create_project(
                domain.Project(name="Rollback Proj", root_path="/r/path", default_branch="main")
            )
            proj_id = proj.id
            assert proj_id is not None
            # Raise an exception to trigger rollback
            raise RuntimeError("Forced Exception")
    except RuntimeError:
        pass

    # Open a new session to verify the project was rolled back and does not exist
    assert proj_id is not None
    async with await db_manager.get_session() as session:
        service = ProjectService(session)
        fetched = await service.get_project(proj_id)
        assert fetched is None
