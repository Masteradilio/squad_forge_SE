import asyncio

from fastapi.testclient import TestClient
from localforge.api.app import create_app
from localforge.llm.fake import FakeLLMProvider
from localforge.models import domain
from localforge.models.enums import (
    ActionKind,
    AgentRole,
    ArtifactType,
    DocumentKind,
    RunMode,
    RunStatus,
    TaskStatus,
)
from localforge.storage import UnitOfWork
from localforge.storage.bootstrap import bootstrap_database
from localforge.storage.database import DatabaseManager
from localforge.storage.orm import ArtifactORM


def test_api_health_and_openapi_available(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        client = TestClient(create_app(db_manager=manager))
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/openapi.json").status_code == 200
    finally:
        close_manager(manager)


def test_api_exposes_core_state_endpoints(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        client = TestClient(
            create_app(db_manager=manager, llm_provider=FakeLLMProvider())
        )

        assert client.get("/projects").json()[0]["id"] == ids["project_id"]
        assert client.get(f"/projects/{ids['project_id']}/tasks").json()[0]["key"] == "LF-1401"
        assert client.get(f"/projects/{ids['project_id']}/runs").json()[0]["id"] == ids["run_id"]
        assert client.get("/agents").json()[0]["name"] == "tester"
        assert client.get(f"/tasks/{ids['task_id']}/artifacts").json()[0]["type"] == "TestArtifact"
        assert (
            client.get(f"/projects/{ids['project_id']}/policies/default").json()["name"]
            == "default"
        )
        assert client.get("/models").json()["provider"] == "ollama"
        assert client.get(f"/projects/{ids['project_id']}/prs").json()[0]["key"] == "LF-1401"
    finally:
        close_manager(manager)


def test_api_comments_runtimes_and_task_ancestry(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)

        async def seed_doc_epic_link() -> None:
            async with UnitOfWork(manager) as uow:
                assert uow.projects is not None
                assert uow.tasks is not None
                doc = await uow.projects.create_document(
                    domain.ProductDocument(
                        project_id=ids["project_id"],
                        kind=DocumentKind.PRD,
                        path="PRD.md",
                        content_hash="prdhash",
                    )
                )
                assert doc.id is not None
                epic = await uow.tasks.create_epic(
                    domain.Epic(
                        project_id=ids["project_id"],
                        title="Traceability",
                        summary="Trace PRD to PR",
                        source_document_id=doc.id,
                    )
                )
                assert epic.id is not None
                task = await uow.tasks.get_task(ids["task_id"])
                assert task is not None
                task.epic_id = epic.id
                await uow.tasks.update_task(task)

        asyncio.run(seed_doc_epic_link())
        client = TestClient(create_app(db_manager=manager))

        comment = client.post(
            f"/tasks/{ids['task_id']}/comments",
            json={"author": "reviewer", "body": "Check edge cases", "thread_id": "t1"},
        )
        assert comment.status_code == 200
        assert comment.json()["body"] == "Check edge cases"
        comments = client.get(f"/tasks/{ids['task_id']}/comments").json()
        assert comments[0]["thread_id"] == "t1"

        runtime = client.post(
            f"/projects/{ids['project_id']}/runtimes",
            json={
                "runtime_id": "daemon-1",
                "name": "Local Daemon",
                "capabilities": ["scheduler", "sandbox"],
            },
        )
        assert runtime.status_code == 200
        assert runtime.json()["status"] == "ONLINE"
        heartbeat = client.post(
            "/runtimes/daemon-1/heartbeat",
            json={"status": "DEGRADED", "metadata": {"reason": "ollama offline"}},
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["metadata"]["reason"] == "ollama offline"
        assert client.get(f"/projects/{ids['project_id']}/runtimes").json()[0]["runtime_id"] == "daemon-1"

        squad = client.post(
            f"/projects/{ids['project_id']}/squads",
            json={"name": "Review Squad", "purpose": "High risk review", "roles": ["Reviewer"]},
        )
        assert squad.status_code == 200
        assert squad.json()["roles"] == ["Reviewer"]
        assert client.get(f"/projects/{ids['project_id']}/squads").json()[0]["name"] == "Review Squad"

        ancestry = client.get(f"/tasks/{ids['task_id']}/ancestry")
        assert ancestry.status_code == 200
        payload = ancestry.json()
        assert payload["document"]["path"] == "PRD.md"
        assert payload["epic"]["title"] == "Traceability"
        assert payload["task"]["key"] == "LF-1401"
        assert payload["task_runs"][0]["artifacts"][0]["type"] == "TestArtifact"
    finally:
        close_manager(manager)


def test_api_dashboard_completion_endpoints(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        worktree = tmp_path / ".localforge" / "worktrees" / "lf-1401"
        worktree.mkdir(parents=True)

        async def seed_worktree_path() -> None:
            async with await manager.get_session() as session:
                from localforge.storage.orm import TaskRunORM
                result = await session.get(TaskRunORM, ids["task_run_id"])
                assert result is not None
                result.worktree_path = str(worktree)
                result.branch_name = "localforge/lf-1401-api"
                await session.commit()

        asyncio.run(seed_worktree_path())
        client = TestClient(create_app(db_manager=manager))

        settings = client.get(f"/projects/{ids['project_id']}/settings")
        assert settings.status_code == 200
        assert settings.json()["project_path"] == str(tmp_path)
        assert "resource_limits" in settings.json()

        skill = client.put(
            f"/projects/{ids['project_id']}/skills/custom-skill",
            json={
                "name": "ignored",
                "purpose": "Custom local skill",
                "triggers": ["custom"],
                "allowed_actions": ["read"],
                "expected_artifacts": ["review.md"],
                "failure_modes": [],
                "examples": [],
                "enabled": False,
            },
        )
        assert skill.status_code == 200
        assert skill.json()["enabled"] is False
        assert client.get(f"/projects/{ids['project_id']}/skills").json()[0]["name"]

        metrics = client.get(f"/projects/{ids['project_id']}/models/metrics")
        assert metrics.status_code == 200

        worktrees = client.get(f"/projects/{ids['project_id']}/worktrees")
        assert worktrees.status_code == 200
        assert worktrees.json()[0]["task_key"] == "LF-1401"
        assert worktrees.json()[0]["branch"] == "localforge/lf-1401-api"

        export = client.get(f"/projects/{ids['project_id']}/audit-events/export")
        assert export.status_code == 200
        assert export.headers["content-type"].startswith("application/json")
    finally:
        close_manager(manager)


def test_api_command_bridge_updates_runs_and_audits(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        response = client.post(f"/runs/{ids['run_id']}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "PAUSED"
        events = client.get(f"/projects/{ids['project_id']}/audit-events").json()
        assert any(event["payload_redacted"]["action"] == "run_pause" for event in events)
    finally:
        close_manager(manager)


def test_api_artifact_content_redacts_secrets_and_blocks_traversal(tmp_path, monkeypatch):
    manager = make_db_manager(tmp_path)
    try:
        monkeypatch.setenv("LOCALFORGE_GITHUB_TOKEN", "secret-token")
        ids = seed_api_state(manager, tmp_path, content="token=secret-token\n")
        client = TestClient(create_app(db_manager=manager))

        response = client.get(f"/artifacts/{ids['artifact_id']}/content")

        assert response.status_code == 200
        assert "secret-token" not in response.json()["content"]
        assert "[REDACTED]" in response.json()["content"]

        poison_artifact_path(manager, ids["artifact_id"])
        blocked = client.get(f"/artifacts/{ids['artifact_id']}/content")
        assert blocked.status_code == 403
    finally:
        close_manager(manager)


def make_db_manager(tmp_path) -> DatabaseManager:
    db_file = (tmp_path / "api.db").as_posix()
    manager = DatabaseManager(f"sqlite+aiosqlite:///{db_file}")
    asyncio.run(bootstrap_database(manager))
    return manager


def close_manager(manager: DatabaseManager) -> None:
    asyncio.run(manager.close())


def seed_api_state(
    db_manager: DatabaseManager, tmp_path, content: str = "tests passed\n"
) -> dict[str, int]:
    async def seed() -> dict[str, int]:
        async with UnitOfWork(db_manager) as uow:
            assert uow.projects is not None
            assert uow.tasks is not None
            assert uow.executions is not None
            assert uow.audits is not None
            project = await uow.projects.create_project(
                domain.Project(name="API", root_path=str(tmp_path), default_branch="main")
            )
            assert project.id is not None
            await uow.audits.create_policy(
                domain.Policy(project_id=project.id, name="default", rules={"protected_paths": []})
            )
            task = await uow.tasks.create_task(
                domain.Task(
                    project_id=project.id,
                    key="LF-1401",
                    title="API",
                    description="Expose state",
                    status=TaskStatus.PR_READY,
                )
            )
            assert task.id is not None
            run = await uow.executions.create_run(
                domain.Run(
                    project_id=project.id,
                    mode=RunMode.INTERACTIVE,
                    status=RunStatus.RUNNING,
                    initiated_by="test",
                )
            )
            assert run.id is not None
            agent = await uow.executions.register_agent(
                domain.Agent(name="tester", role=AgentRole.TESTER, model_profile_id="fake")
            )
            assert agent.id is not None
            task_run = await uow.tasks.create_task_run(
                domain.TaskRun(run_id=run.id, task_id=task.id)
            )
            assert task_run.id is not None
            artifact_dir = tmp_path / ".localforge" / "artifacts"
            artifact_dir.mkdir(parents=True)
            artifact_file = artifact_dir / "tests.md"
            artifact_file.write_text(content, encoding="utf-8")
            artifact = await uow.audits.create_artifact(
                domain.Artifact(
                    task_run_id=task_run.id,
                    type=ArtifactType.TEST,
                    path=".localforge/artifacts/tests.md",
                    content_hash="hash",
                    summary="tests",
                )
            )
            assert artifact.id is not None
            return {
                "project_id": project.id,
                "task_id": task.id,
                "run_id": run.id,
                "task_run_id": task_run.id,
                "artifact_id": artifact.id,
            }

    return asyncio.run(seed())


def poison_artifact_path(db_manager: DatabaseManager, artifact_id: int) -> None:
    async def poison() -> None:
        async with await db_manager.get_session() as session:
            artifact = await session.get(ArtifactORM, artifact_id)
            assert artifact is not None
            artifact.path = "../outside.txt"
            await session.commit()

    asyncio.run(poison())


def test_api_cors_and_gzip_middlewares_and_safety_endpoints(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        
        # Seed a pending safety approval
        async def seed_approval():
            async with UnitOfWork(manager) as uow:
                assert uow.safety is not None
                await uow.safety.create_approval(
                    domain.ActionApproval(
                        project_id=ids["project_id"],
                        run_id=ids["run_id"],
                        action_kind=ActionKind.RUN_COMMAND,
                        payload={"cmd": "rm -rf /"},
                        purpose="test purpose",
                        risk_level="high",
                        status=domain.ActionApprovalStatus.PENDING,
                    )
                )
        asyncio.run(seed_approval())

        client = TestClient(create_app(db_manager=manager))

        # 1. Test CORS Middleware
        cors_res = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert cors_res.headers.get("access-control-allow-origin") == "http://localhost:5173"

        # 2. Test Gzip Middleware
        gzip_res = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
        assert gzip_res.headers.get("content-encoding") == "gzip"

        # 3. Test GET pending safety approvals
        pending = client.get(f"/projects/{ids['project_id']}/safety/pending").json()
        assert len(pending) == 1
        assert pending[0]["payload"]["cmd"] == "rm -rf /"
        app_id = pending[0]["id"]

        # 4. Test POST approve safety approval
        approved = client.post(f"/safety/approvals/{app_id}/approve").json()
        assert approved["status"] == "APPROVED"

        # 5. Verify it's no longer pending
        pending_after = client.get(f"/projects/{ids['project_id']}/safety/pending").json()
        assert len(pending_after) == 0

    finally:
        close_manager(manager)


def test_api_prd_and_backlog_studio_endpoints(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        # 1. Test GET epics (empty initially)
        epics = client.get(f"/projects/{ids['project_id']}/epics").json()
        assert len(epics) == 0

        # 2. Write mock PRD
        prd_file = tmp_path / "PRD.md"
        prd_file.write_text(
            "# App\n\n## Authentication\n- Add login\n- Add logout\n",
            encoding="utf-8",
        )

        # 3. Test import-prd (dry_run=True)
        import_res = client.post(
            f"/projects/{ids['project_id']}/import-prd",
            json={"path": str(prd_file), "dry_run": True},
        ).json()
        assert import_res["persisted"] is False
        assert import_res["tasks_created"] == 2

        # 4. Test import-prd (dry_run=False)
        import_res2 = client.post(
            f"/projects/{ids['project_id']}/import-prd",
            json={"path": str(prd_file), "dry_run": False},
        ).json()
        assert import_res2["persisted"] is True
        assert import_res2["tasks_created"] == 2

        # 5. Verify epics and tasks loaded
        epics = client.get(f"/projects/{ids['project_id']}/epics").json()
        assert len(epics) == 1
        assert epics[0]["title"] == "Authentication"

        tasks = client.get(f"/projects/{ids['project_id']}/tasks").json()
        backlog_tasks = [t for t in tasks if t["status"] == "BACKLOG"]
        assert len(backlog_tasks) >= 2
        login_task = next(t for t in backlog_tasks if "login" in t["title"])
        assert login_task["risk_level"] == "low"

        # 6. Test PUT /tasks/{task_id} update details
        updated_task = client.put(
            f"/tasks/{login_task['id']}",
            json={
                "epic_id": login_task["epic_id"],
                "title": "Add secure login",
                "description": "Secure login implementation",
                "acceptance_criteria": ["Username exists", "Password checks"],
                "dependency_task_ids": [],
                "risk_level": "medium",
                "status": "BACKLOG",
            },
        ).json()
        assert updated_task["title"] == "Add secure login"
        assert updated_task["risk_level"] == "medium"

        # 7. Test POST /tasks/{task_id}/approve
        approved_task = client.post(
            f"/tasks/{login_task['id']}/approve"
        ).json()
        assert approved_task["status"] == "READY"

    finally:
        close_manager(manager)


def test_api_pr_review_center_and_policy_updates(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)
        client = TestClient(create_app(db_manager=manager))

        # 1. Test PUT policy rules
        policy_url = f"/projects/{ids['project_id']}/policies/default"
        rules_payload = {
            "name": "default",
            "allowed_commands": ["npm test", "python -m pytest"],
            "blocked_commands": ["rm -rf"],
            "protected_paths": ["config/"],
            "approval_required_patterns": [],
            "max_repair_attempts": 3,
            "max_files_touched": 5,
            "max_run_duration": 10,
            "allowed_directories": []
        }
        policy_res = client.put(policy_url, json=rules_payload)
        assert policy_res.status_code == 200
        assert policy_res.json()["rules"]["blocked_commands"] == ["rm -rf"]

        # 2. Test GET task pr-details
        pr_details_res = client.get(f"/tasks/{ids['task_id']}/pr-details")
        assert pr_details_res.status_code == 200
        details = pr_details_res.json()
        assert "tests_content" in details
        assert details["tests_content"] == "tests passed\n"

        # 3. Test POST open path
        open_res = client.post(f"/tasks/{ids['task_id']}/open-path")
        assert open_res.status_code == 200
        assert open_res.json()["status"] == "ok"

        # 4. Test POST rerun tests
        rerun_res = client.post(f"/tasks/{ids['task_id']}/rerun-tests")
        assert rerun_res.status_code == 200
        assert "exit_code" in rerun_res.json()

        # 5. Test POST PR reviews: reject
        review_reject_res = client.post(
            f"/tasks/{ids['task_id']}/pr-review/reject"
        )
        assert review_reject_res.status_code == 200
        assert review_reject_res.json()["status"] == "FAILED_SAFE"

        # Reset status back to PR_READY to test request_adjustment
        async def reset_status():
            async with await manager.get_session() as session:
                from localforge.storage.orm import TaskORM
                task = await session.get(TaskORM, ids["task_id"])
                task.status = "PR_READY"
                await session.commit()
        asyncio.run(reset_status())

        # Test POST PR reviews: request_adjustment
        review_adj_res = client.post(
            f"/tasks/{ids['task_id']}/pr-review/request_adjustment"
        )
        assert review_adj_res.status_code == 200
        assert review_adj_res.json()["status"] == "READY"

        # Reset status back to PR_READY to test accept
        asyncio.run(reset_status())

        # Test POST PR reviews: accept
        review_accept_res = client.post(
            f"/tasks/{ids['task_id']}/pr-review/accept"
        )
        assert review_accept_res.status_code == 200
        assert review_accept_res.json()["status"] == "DONE"

        async def assign_agent():
            async with await manager.get_session() as session:
                from localforge.storage.orm import TaskORM
                task = await session.get(TaskORM, ids["task_id"])
                task.assigned_agent_id = 1
                task.status = "READY"
                await session.commit()
        asyncio.run(assign_agent())

        agent_details_res = client.get("/agents/1/details")
        assert agent_details_res.status_code == 200
        details = agent_details_res.json()
        assert details["agent"]["id"] == 1
        assert len(details["artifacts"]) > 0

        # 7. Test POST tasks control block
        control_res = client.post(f"/tasks/{ids['task_id']}/control/block")
        assert control_res.status_code == 200
        assert control_res.json()["status"] == "BLOCKED"

        # 8. Test POST restore policy version
        client.put(policy_url, json=rules_payload)
        restore_res = client.post(
            f"/projects/{ids['project_id']}/policies/default/restore/1"
        )
        assert restore_res.status_code == 200

    finally:
        close_manager(manager)


def test_api_v3_endpoints(tmp_path):
    manager = make_db_manager(tmp_path)
    try:
        ids = seed_api_state(manager, tmp_path)

        async def seed_v3_data() -> None:
            async with UnitOfWork(manager) as uow:
                assert uow.session is not None
                from localforge.storage.orm import PricingSourceORM, ModelPricingSnapshotORM, ModelCallLedgerORM
                from localforge.models.enums import ChiefEngineerCallReason

                # Pricing Source
                source = PricingSourceORM(
                    provider="OpenAI",
                    url="https://openai.com/api/pricing/",
                    notes="Test notes"
                )
                uow.session.add(source)
                await uow.session.flush()

                # Snapshots
                uow.session.add(ModelPricingSnapshotORM(
                    pricing_source_id=source.id,
                    model_name="gpt-5.5-large",
                    input_price_per_million=5.0,
                    output_price_per_million=30.0,
                    cached_input_price_per_million=2.5,
                ))
                uow.session.add(ModelPricingSnapshotORM(
                    pricing_source_id=source.id,
                    model_name="gpt-5.4-medium",
                    input_price_per_million=2.5,
                    output_price_per_million=15.0,
                    cached_input_price_per_million=1.25,
                ))
                uow.session.add(ModelPricingSnapshotORM(
                    pricing_source_id=source.id,
                    model_name="gpt-5.4-mini",
                    input_price_per_million=0.75,
                    output_price_per_million=4.5,
                ))

                # Model Call Ledger (to populate reports)
                uow.session.add(ModelCallLedgerORM(
                    project_id=ids["project_id"],
                    run_id=ids["run_id"],
                    task_id=ids["task_id"],
                    provider="openrouter",
                    model="gpt-5.5-large",
                    reason=ChiefEngineerCallReason.SEMANTIC_REPAIR_PLAN.value,
                    input_tokens=1000,
                    output_tokens=500,
                    estimated_cost_usd=0.02,
                    status="success"
                ))
                await uow.session.commit()

        asyncio.run(seed_v3_data())

        client = TestClient(create_app(db_manager=manager))

        # 1. Test GET /projects/{project_id}/squad-composition
        squad_res = client.get(f"/projects/{ids['project_id']}/squad-composition")
        assert squad_res.status_code == 200
        squad = squad_res.json()
        assert len(squad) > 0
        assert squad[0]["role"] is not None
        assert squad[0]["seniority_class"] is not None

        # 2. Test GET /projects/{project_id}/costs/report
        report_res = client.get(f"/projects/{ids['project_id']}/costs/report")
        assert report_res.status_code == 200
        report = report_res.json()
        assert "benchmarks" in report
        assert "by_role" in report
        assert "by_task" in report
        assert "snapshots" in report
        assert report["benchmarks"]["actual_paid_usd"] > 0.0

        # 3. Test GET /projects/{project_id}/costs/simulate
        sim_res = client.get(f"/projects/{ids['project_id']}/costs/simulate")
        assert sim_res.status_code == 200
        sim = sim_res.json()
        assert "openai_simulated_usd" in sim
        assert "anthropic_simulated_usd" in sim
        assert "google_simulated_usd" in sim

        # 4. Test GET /projects/{project_id}/costs/sources
        sources_res = client.get(f"/projects/{ids['project_id']}/costs/sources")
        assert sources_res.status_code == 200
        sources = sources_res.json()
        assert len(sources) > 0
        assert any(s["provider"] == "OpenAI" for s in sources)

        # 5. Test GET /projects/{project_id}/benchmark/rollup
        rollup_res = client.get(f"/projects/{ids['project_id']}/benchmark/rollup")
        assert rollup_res.status_code == 200
        rollup = rollup_res.json()
        assert rollup["actual_paid_usd"] > 0.0

        # 6. Test POST /projects/{project_id}/costs/sources
        new_source_res = client.post(
            f"/projects/{ids['project_id']}/costs/sources",
            json={"provider": "Anthropic", "url": "https://anthropic.com/pricing", "notes": "notes"}
        )
        assert new_source_res.status_code == 200
        new_source = new_source_res.json()
        assert new_source["provider"] == "Anthropic"
        assert new_source["id"] is not None

        # 7. Test PUT /projects/{project_id}/costs/snapshots
        new_snap_res = client.put(
            f"/projects/{ids['project_id']}/costs/snapshots",
            json={
                "pricing_source_id": new_source["id"],
                "model_name": "claude-opus-4.8",
                "input_price_per_million": 15.0,
                "output_price_per_million": 75.0,
            }
        )
        assert new_snap_res.status_code == 200
        new_snap = new_snap_res.json()
        assert new_snap["model_name"] == "claude-opus-4.8"
        assert new_snap["input_price_per_million"] == 15.0

    finally:
        close_manager(manager)
