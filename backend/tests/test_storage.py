import pytest
from localforge.models.domain import Project
from localforge.storage.bootstrap import get_current_schema_version
from localforge.storage.orm import ProjectORM
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_bootstrap_initialization(db_session: AsyncSession):
    # Verify that schema version table was created and has current version
    version = await get_current_schema_version(db_session)
    assert version == 6

    # Verify that tables like projects, tasks, epics exist by running a simple query
    result = await db_session.execute(text("SELECT COUNT(*) FROM projects"))
    count = result.scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_orm_mapping_and_conversion():
    domain_proj = Project(
        name="Test Project",
        root_path="/tmp/test",
        default_branch="develop",
        remote_url="git@github.com:test/repo.git",
    )

    # Convert to ORM
    orm_proj = ProjectORM.from_domain(domain_proj)
    assert orm_proj.name == "Test Project"
    assert orm_proj.root_path == "/tmp/test"
    assert orm_proj.default_branch == "develop"
    assert orm_proj.remote_url == "git@github.com:test/repo.git"

    # Convert back to domain
    converted_domain = orm_proj.to_domain()
    assert converted_domain.name == domain_proj.name
    assert converted_domain.root_path == domain_proj.root_path
    assert converted_domain.default_branch == domain_proj.default_branch
    assert converted_domain.remote_url == domain_proj.remote_url
