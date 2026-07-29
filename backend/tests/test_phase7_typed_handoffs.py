import pytest
from localforge.models import domain
from localforge.models.enums import TypedArtifactType
from localforge.services.typed_handoff import compute_artifact_hash
from localforge.storage import UnitOfWork


def test_artifact_hash_computation() -> None:
    """Test V6-701: Deterministic SHA-256 content_hash generation."""
    h1 = compute_artifact_hash(
        summary="Test summary",
        evidence={"key": "value"},
        changed_files=["src/app.py"],
        tests_executed=["pytest"],
        validation_results={"passed": True},
    )
    h2 = compute_artifact_hash(
        summary="Test summary",
        evidence={"key": "value"},
        changed_files=["src/app.py"],
        tests_executed=["pytest"],
        validation_results={"passed": True},
    )
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string length


@pytest.mark.asyncio
async def test_artifact_creation_integrity_and_consume_once(db_manager) -> None:
    """Test V6-700 & V6-701: Artifact creation, integrity validation, and consume-once semantics."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.tasks is not None
        assert uow.typed_handoffs is not None

        proj = domain.Project(
            name="Handoff Test", root_path="E:/tmp/handoff_test", default_branch="main"
        )
        project = await uow.projects.create_project(proj)
        assert project.id is not None

        task = await uow.tasks.create_task(
            domain.Task(project_id=project.id, key="TH-1", title="Task 1", description="Desc 1")
        )
        assert task.id is not None
        task_run = await uow.tasks.create_task_run(domain.TaskRun(task_id=task.id, run_id=1))
        assert task_run.id is not None

        # Create TypedHandoffArtifact
        artifact = await uow.typed_handoffs.create_artifact(
            project_id=project.id,
            task_run_id=task_run.id,
            producer_agent_id="agent_producer",
            consumer_agent_id="agent_consumer",
            summary="Completed research on backend architecture",
            artifact_type=TypedArtifactType.RESEARCH,
            evidence_json={"findings": "Architecture is clean"},
            changed_files=["backend/localforge/services/typed_handoff.py"],
            tests_executed=["test_phase7_typed_handoffs.py"],
            risks=["Potential DB migration lock"],
            open_questions=["Should we support JSON Schema validation?"],
        )
        assert artifact.id is not None
        assert artifact.is_consumed is False

        # Validate integrity -> VERIFIED
        valid, msg = await uow.typed_handoffs.validate_artifact_integrity(artifact.id)
        assert valid is True
        assert msg is None

        # Consume artifact -> succeeds first time
        consumed_1 = await uow.typed_handoffs.consume_artifact(artifact.id)
        assert consumed_1.is_consumed is True

        # Re-consuming same artifact -> raises ValueError
        with pytest.raises(ValueError, match="already been consumed"):
            await uow.typed_handoffs.consume_artifact(artifact.id)


def test_markdown_rendering_and_secret_redaction() -> None:
    """Test V6-703: Human-readable markdown rendering with secret redaction."""
    from localforge.services.typed_handoff import TypedHandoffService

    art = domain.TypedHandoffArtifact(
        project_id=1,
        task_run_id=1,
        producer_agent_id="agent_prod",
        consumer_agent_id="agent_cons",
        artifact_type=TypedArtifactType.VERIFICATION,
        summary="Verification report with secret api_key='sk-123456789'",
        open_questions=["How to securely store password='supersecret'?"],
        risks=["Security risk token=abcxyz"],
        content_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )

    dummy_service = TypedHandoffService(None)  # type: ignore[arg-type]
    md = dummy_service.render_markdown_summary(art)

    assert "# Typed Handoff Artifact: VERIFICATION" in md
    assert "[REDACTED]" in md
    assert "sk-123456789" not in md
    assert "supersecret" not in md
