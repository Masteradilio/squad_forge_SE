from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.storage.orm import ProductDocumentORM, ProjectORM
from localforge.services.tenant_context import session_tenant


class ProjectService:
    """Service layer for Project and ProductDocument persistence and management."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _tenant_id(self) -> str:
        return session_tenant(self.session)

    async def create_project(self, project: domain.Project) -> domain.Project:
        """Create a new project in the database."""
        if project.tenant_id != self._tenant_id():
            project = project.model_copy(update={"tenant_id": self._tenant_id()})
        orm_obj = ProjectORM.from_domain(project)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_project(self, project_id: int) -> domain.Project | None:
        """Retrieve a project by its primary key ID."""
        result = await self.session.execute(
            select(ProjectORM).where(
                ProjectORM.id == project_id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_project_by_path(self, root_path: str) -> domain.Project | None:
        """Retrieve a project by its root path."""
        result = await self.session.execute(
            select(ProjectORM).where(
                ProjectORM.root_path == root_path,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def list_projects(self) -> list[domain.Project]:
        """List all projects in the database."""
        result = await self.session.execute(
            select(ProjectORM)
            .where(ProjectORM.tenant_id == self._tenant_id())
            .order_by(ProjectORM.name)
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]

    async def update_project(self, project: domain.Project) -> domain.Project:
        """Update an existing project's data."""
        if not project.id:
            raise ValueError("Cannot update a project without an ID")
        result = await self.session.execute(
            select(ProjectORM).where(
                ProjectORM.id == project.id,
                ProjectORM.tenant_id == self._tenant_id(),
            )
        )
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"Project with ID {project.id} not found")

        orm_obj.name = project.name
        orm_obj.root_path = project.root_path
        orm_obj.default_branch = project.default_branch
        orm_obj.remote_url = project.remote_url
        orm_obj.localforge_config_path = project.localforge_config_path
        orm_obj.updated_at = project.updated_at
        await self.session.flush()
        return orm_obj.to_domain()

    async def create_document(self, doc: domain.ProductDocument) -> domain.ProductDocument:
        """Add a product document to a project."""
        orm_obj = ProductDocumentORM.from_domain(doc)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def get_document(self, doc_id: int) -> domain.ProductDocument | None:
        """Retrieve a document by ID."""
        result = await self.session.execute(
            select(ProductDocumentORM).where(ProductDocumentORM.id == doc_id)
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_document_by_hash(
        self, project_id: int, content_hash: str
    ) -> domain.ProductDocument | None:
        """Retrieve a document by project and its content hash."""
        result = await self.session.execute(
            select(ProductDocumentORM).where(
                ProductDocumentORM.project_id == project_id,
                ProductDocumentORM.content_hash == content_hash,
            )
        )
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def get_document_by_path(
        self, project_id: int, path: str
    ) -> domain.ProductDocument | None:
        """Retrieve the latest document imported from a project path."""
        result = await self.session.execute(
            select(ProductDocumentORM)
            .where(
                ProductDocumentORM.project_id == project_id,
                ProductDocumentORM.path == path,
            )
            .order_by(ProductDocumentORM.imported_at.desc())
        )
        orm_obj = result.scalars().first()
        return orm_obj.to_domain() if orm_obj else None

    async def list_documents_for_project(self, project_id: int) -> list[domain.ProductDocument]:
        """List all product documents for a given project."""
        result = await self.session.execute(
            select(ProductDocumentORM)
            .where(ProductDocumentORM.project_id == project_id)
            .order_by(ProductDocumentORM.imported_at.desc())
        )
        return [orm_obj.to_domain() for orm_obj in result.scalars().all()]
