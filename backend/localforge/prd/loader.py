import hashlib
from dataclasses import dataclass
from pathlib import Path

from localforge.models import domain
from localforge.models.enums import DocumentKind
from localforge.services.project import ProjectService


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LoadedMarkdownDocument:
    document: domain.ProductDocument
    content: str
    content_hash: str
    changed: bool


class MarkdownDocumentLoader:
    def __init__(self, projects: ProjectService):
        self.projects = projects

    async def load(
        self,
        project_id: int,
        path: str | Path,
        kind: DocumentKind = DocumentKind.PRD,
        *,
        persist: bool = True,
        parsed_summary: str | None = None,
    ) -> LoadedMarkdownDocument:
        doc_path = Path(path).resolve()
        content = doc_path.read_text(encoding="utf-8")
        content_hash = sha256_text(content)
        existing = await self.projects.get_document_by_path(project_id, str(doc_path))
        changed = existing is None or existing.content_hash != content_hash
        document = domain.ProductDocument(
            project_id=project_id,
            kind=kind,
            path=str(doc_path),
            content_hash=content_hash,
            parsed_summary=parsed_summary,
        )
        if persist and changed:
            document = await self.projects.create_document(document)
        elif existing is not None:
            document = existing
        return LoadedMarkdownDocument(document, content, content_hash, changed)
