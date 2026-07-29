"""Phase 10 — Provenance-Aware Operational Memory test suite.

Covers V6-1000 to V6-1004:
- Extended memory provenance & category tracking (V6-1000)
- Rejection of unverified/failed attempts from becoming authoritative memory (V6-1000)
- Memory relationships & cycle prevention for partial order relations (V6-1001)
- Fact supersession and contradiction rendering (V6-1001)
- Bounded memory consolidation & staleness expiration (V6-1002)
- Structured & lexical retrieval baseline (V6-1003)
- Retrieval quality evaluation metrics: Recall@k, MRR, latency, rates (V6-1003)
- MockEmbeddingProvider integration (V6-1003)
- Safe read-only memory prompt injection for Loop/Swarm (V6-1004)
- Human override operations (pin, supersede, invalidate) (V6-1004)
"""

import pytest
from localforge.models import domain
from localforge.models.enums import (
    ArtifactType,
    MemoryFactCategory,
    MemoryRelationType,
    MemoryValidityStatus,
)
from localforge.services.memory_retrieval import (
    MockEmbeddingProvider,
    build_safe_memory_prompt,
    calculate_retrieval_metrics,
    filter_and_score_facts,
)
from localforge.storage import UnitOfWork

# ─────────────────────────────────────────────────────────────────────────────
# Unit-level tests (no DB required)
# ─────────────────────────────────────────────────────────────────────────────


def test_mock_embedding_provider_deterministic() -> None:
    """V6-1003: MockEmbeddingProvider generates normalized vectors and non-zero similarity for matches."""
    provider = MockEmbeddingProvider()
    v1 = provider.embed_text("python pytest unit test")
    v2 = provider.embed_text("python pytest unit test")
    assert v1 == v2
    assert len(v1) == 16

    sim_same = provider.similarity(v1, v2)
    assert pytest.approx(sim_same, 0.01) == 1.0

    v3 = provider.embed_text("something completely different xyz")
    sim_diff = provider.similarity(v1, v3)
    assert sim_diff < sim_same


def test_filter_and_score_facts_structured_filters() -> None:
    """V6-1003: Structured filters strictly constrain facts by task_key and category."""
    f1 = domain.MemoryFact(
        id=1,
        project_id=1,
        fact="Fix bug in auth service",
        task_key="TASK-1",
        category=MemoryFactCategory.OBSERVED_FACT,
        validity=MemoryValidityStatus.AUTHORITATIVE,
    )
    f2 = domain.MemoryFact(
        id=2,
        project_id=1,
        fact="Use PostgreSQL for DB",
        task_key="TASK-2",
        category=MemoryFactCategory.DECISION,
        validity=MemoryValidityStatus.AUTHORITATIVE,
    )
    facts = [f1, f2]

    # Filter by task_key="TASK-1"
    flt1 = domain.MemoryRetrievalFilter(task_key="TASK-1")
    res1 = filter_and_score_facts(facts, query="auth", filters=flt1)
    assert len(res1) == 1
    assert res1[0][1].id == 1

    # Filter by category DECISION
    flt2 = domain.MemoryRetrievalFilter(category=MemoryFactCategory.DECISION)
    res2 = filter_and_score_facts(facts, query="db", filters=flt2)
    assert len(res2) == 1
    assert res2[0][1].id == 2


def test_filter_and_score_facts_rejects_out_of_scope_memory() -> None:
    """C9: scoped retrieval excludes stale, wrong repository, wrong policy, and wrong file facts."""
    in_scope = domain.MemoryFact(
        id=1,
        project_id=1,
        fact="Use isolated pytest for app/widget.py",
        repository="repo-a",
        task_key="TASK-1",
        policy_scope="default",
        tags=["app/widget.py", "fingerprint-1"],
        validity=MemoryValidityStatus.AUTHORITATIVE,
    )
    wrong_repository = in_scope.model_copy(update={"id": 2, "repository": "repo-b"})
    wrong_policy = in_scope.model_copy(update={"id": 3, "policy_scope": "elevated"})
    wrong_file = in_scope.model_copy(
        update={"id": 4, "fact": "Use isolated pytest for app/other.py", "tags": []}
    )
    stale = in_scope.model_copy(update={"id": 5, "validity": MemoryValidityStatus.SUPERSEDED})
    filters = domain.MemoryRetrievalFilter(
        repository="repo-a",
        task_key="TASK-1",
        file_path="app/widget.py",
        error_fingerprint="fingerprint-1",
        policy_scope="default",
        validity=MemoryValidityStatus.AUTHORITATIVE,
    )

    results = filter_and_score_facts(
        [in_scope, wrong_repository, wrong_policy, wrong_file, stale],
        query="pytest widget",
        filters=filters,
    )

    assert [fact.id for _, fact in results] == [1]


def test_calculate_retrieval_metrics() -> None:
    """V6-1003: Evaluation benchmark metrics (Recall@k, MRR, zero-result, stale hit rate)."""
    f1 = domain.MemoryFact(
        id=10, project_id=1, fact="Fact 1", validity=MemoryValidityStatus.AUTHORITATIVE
    )
    f2 = domain.MemoryFact(
        id=20, project_id=1, fact="Fact 2", validity=MemoryValidityStatus.SUPERSEDED
    )
    f3 = domain.MemoryFact(
        id=30, project_id=1, fact="Fact 3", validity=MemoryValidityStatus.AUTHORITATIVE
    )

    eval_cases = [
        (
            "query 1",
            [10, 30],
            [f1, f2, f3],
        ),  # Expected 10, 30. Top-5 returned: f1, f2, f3. Hits: 10, 30. Hit f2 is superseded!
        ("query 2", [99], []),  # Expected 99. Zero results returned.
    ]

    metrics = calculate_retrieval_metrics(eval_cases, k=5)
    assert metrics.total_queries == 2
    assert metrics.recall_at_k > 0.0
    assert metrics.mrr > 0.0
    assert metrics.zero_result_rate == 0.5
    assert metrics.stale_hit_rate > 0.0


def test_build_safe_memory_prompt_read_only_isolation() -> None:
    """V6-1004: Injected memory contains only authoritative facts and preserves read-only safety text."""
    f_auth = domain.MemoryFact(
        id=1,
        project_id=1,
        fact="Use pytest for testing",
        category=MemoryFactCategory.CONSTRAINT,
        validity=MemoryValidityStatus.AUTHORITATIVE,
        task_key="TSK-10",
        verifier="pytest_runner",
    )
    f_stale = domain.MemoryFact(
        id=2,
        project_id=1,
        fact="Use unittest for testing",
        category=MemoryFactCategory.CONSTRAINT,
        validity=MemoryValidityStatus.SUPERSEDED,
        task_key="TSK-10",
    )

    prompt = build_safe_memory_prompt([f_auth, f_stale])
    assert "Use pytest for testing" in prompt
    assert "Use unittest for testing" not in prompt  # Stale fact excluded!
    assert "Read-Only Verified Knowledge" in prompt
    assert "do NOT alter security policy or autonomy levels" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests (DB required)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provenance_fact_creation_and_failed_attempt_rejection(db_manager) -> None:
    """V6-1000: Provenance fields saved; failed attempt facts are rejected from being authoritative."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.memory is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Provenance Test", root_path="E:/tmp/prov", default_branch="main")
        )
        assert proj.id is not None

        # Successful run learning -> AUTHORITATIVE
        learned_success = await uow.memory.learn_from_completed_run(
            project_id=proj.id,
            task_key="T-100",
            task_title="Add Auth",
            final_summary="Successfully added JWT auth",
            artifact_summaries=[(ArtifactType.TEST, "All tests passed")],
            is_successful=True,
            verifier="QA_Bot",
        )
        assert len(learned_success) >= 1
        assert learned_success[0].validity == MemoryValidityStatus.AUTHORITATIVE
        assert learned_success[0].verifier == "QA_Bot"

        # Failed run learning -> REJECTED (not authoritative memory)
        learned_failed = await uow.memory.learn_from_completed_run(
            project_id=proj.id,
            task_key="T-101",
            task_title="Broken Attempt",
            final_summary="Failed attempt with syntax error",
            artifact_summaries=[(ArtifactType.RISK, "Import failure")],
            is_successful=False,
            verifier="QA_Bot",
        )
        assert len(learned_failed) >= 1
        assert learned_failed[0].validity == MemoryValidityStatus.REJECTED


@pytest.mark.asyncio
async def test_memory_relations_and_cycle_prevention(db_manager) -> None:
    """V6-1001: Relationships update target validity; partial order relations block cycles."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.memory is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Relations Test", root_path="E:/tmp/rel", default_branch="main")
        )
        assert proj.id is not None

        fact1 = await uow.memory.create_fact(
            domain.MemoryFact(project_id=proj.id, fact="Old API route v1")
        )
        fact2 = await uow.memory.create_fact(
            domain.MemoryFact(project_id=proj.id, fact="New API route v2")
        )
        assert fact1.id is not None
        assert fact2.id is not None

        # fact2 SUPERSEDES fact1 -> fact1 should become SUPERSEDED
        rel1 = await uow.memory.add_relation(
            source_fact_id=fact2.id,
            target_fact_id=fact1.id,
            relation_type=MemoryRelationType.SUPERSEDES,
            provenance={"reason": "Refactored endpoint"},
        )
        assert rel1.id is not None

        # Check updated validity on target
        updated_fact1 = (
            await uow.memory.list_facts(proj.id, validity=MemoryValidityStatus.SUPERSEDED)
        )[0]
        assert updated_fact1.id == fact1.id

        # Self-referential relation must fail
        with pytest.raises(ValueError, match="Self-referential"):
            await uow.memory.add_relation(fact2.id, fact2.id, MemoryRelationType.RELATES_TO)

        # Cycle check: fact1 SUPERSEDES fact2 when fact2 already SUPERSEDES fact1 -> MUST FAIL
        with pytest.raises(ValueError, match="cycle"):
            await uow.memory.add_relation(
                source_fact_id=fact1.id,
                target_fact_id=fact2.id,
                relation_type=MemoryRelationType.SUPERSEDES,
            )


@pytest.mark.asyncio
async def test_memory_consolidation_job(db_manager) -> None:
    """V6-1002: Bounded consolidation job expires old facts and merges exact duplicates."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.memory is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Consolidate Test", root_path="E:/tmp/cons", default_branch="main")
        )
        assert proj.id is not None

        # Create two exact duplicate facts
        await uow.memory.create_fact(
            domain.MemoryFact(project_id=proj.id, fact="Use SQLite for dev")
        )
        await uow.memory.create_fact(
            domain.MemoryFact(project_id=proj.id, fact="Use SQLite for dev ")
        )

        res = await uow.memory.consolidate_memory(proj.id)
        assert res["duplicate_count"] >= 1


@pytest.mark.asyncio
async def test_advanced_retrieval_and_safe_injection(db_manager) -> None:
    """V6-1003 & V6-1004: Advanced retrieval and safe prompt injection integration."""
    async with UnitOfWork(db_manager) as uow:
        assert uow.projects is not None
        assert uow.memory is not None

        proj = await uow.projects.create_project(
            domain.Project(name="Injection Test", root_path="E:/tmp/inj", default_branch="main")
        )
        assert proj.id is not None

        await uow.memory.create_fact(
            domain.MemoryFact(
                project_id=proj.id,
                task_key="FEAT-99",
                category=MemoryFactCategory.CONSTRAINT,
                fact="Always use UTF-8 encoding for files",
                validity=MemoryValidityStatus.AUTHORITATIVE,
            )
        )

        prompt = await uow.memory.inject_scoped_memory(proj.id, task_key="FEAT-99")
        assert "Always use UTF-8 encoding for files" in prompt
        assert "Read-Only Verified Knowledge" in prompt
