import hashlib
import os
import tempfile

from localforge.models import domain
from localforge.models.enums import ArtifactType
from localforge.storage.transactions import UnitOfWork

ALLOWED_FILENAMES = {
    "plan.md",
    "diff.patch",
    "tests.md",
    "risk.md",
    "review.md",
    "repair.md",
    "pr.md",
    "blocker.md",
}

FILENAME_TO_TYPE = {
    "plan.md": ArtifactType.PLAN,
    "diff.patch": ArtifactType.DIFF,
    "tests.md": ArtifactType.TEST,
    "risk.md": ArtifactType.RISK,
    "review.md": ArtifactType.REVIEW,
    "repair.md": ArtifactType.REPAIR,
    "pr.md": ArtifactType.PR,
    "blocker.md": ArtifactType.BLOCKER,
}


class ArtifactStoreError(ValueError):
    """Raised when an operation on the artifact store violates file layout or fails."""

    pass


class ArtifactStore:
    """Manages the physical atomic writing and database metadata registration of artifacts."""

    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def write_artifact(
        self,
        project_root: str,
        task_run_id: int,
        task_key: str,
        run_id: int,
        filename: str,
        content: str,
        summary: str | None = None,
    ) -> domain.Artifact:
        """Write an artifact atomically to disk and register in the database.

        Disk path: .localforge/artifacts/runs/<run-id>/tasks/<task-key>/<filename>
        """
        if not _is_allowed_filename(filename):
            raise ArtifactStoreError(
                f"Filename '{filename}' is not in the allowed list: {ALLOWED_FILENAMES}"
            )

        # 1. Establish path structure
        target_dir = os.path.realpath(
            os.path.abspath(
                os.path.join(
                    project_root,
                    ".localforge",
                    "artifacts",
                    "runs",
                    str(run_id),
                    "tasks",
                    task_key.lower(),
                )
            )
        )
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)

        # 2. Write file atomically: write to temp file then replace
        temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(temp_fd)
            os.replace(temp_path, target_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            raise ArtifactStoreError(f"Atomic write failed for '{filename}': {e}") from e

        # 3. Calculate SHA-256 content hash
        content_bytes = content.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        # 4. Save metadata to database
        assert self.uow.audits is not None
        art_type = _artifact_type_for(filename)
        artifact_data = domain.Artifact(
            task_run_id=task_run_id,
            type=art_type,
            path=os.path.relpath(target_path, project_root).replace("\\", "/"),
            content_hash=content_hash,
            summary=summary,
        )
        saved = await self.uow.audits.create_artifact(artifact_data)
        return saved

    async def read_artifact(
        self,
        project_root: str,
        run_id: int,
        task_key: str,
        filename: str,
    ) -> str:
        """Read artifact content from disk."""
        if not _is_allowed_filename(filename):
            raise ArtifactStoreError(
                f"Filename '{filename}' is not in the allowed list: {ALLOWED_FILENAMES}"
            )

        target_path = os.path.realpath(
            os.path.abspath(
                os.path.join(
                    project_root,
                    ".localforge",
                    "artifacts",
                    "runs",
                    str(run_id),
                    "tasks",
                    task_key.lower(),
                    filename,
                )
            )
        )

        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Artifact file not found at: {target_path}")

        with open(target_path, encoding="utf-8") as f:
            return f.read()


def _is_allowed_filename(filename: str) -> bool:
    return filename in ALLOWED_FILENAMES or (
        filename.startswith("role-") and filename.endswith(".md") and "/" not in filename
    )


def _artifact_type_for(filename: str) -> ArtifactType:
    if filename.startswith("role-") and filename.endswith(".md"):
        return ArtifactType.ROLE
    return FILENAME_TO_TYPE[filename]
