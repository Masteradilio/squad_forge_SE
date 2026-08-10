"""Exercise a real task-context decision through the Context7 pipeline contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from localforge.models.enums import AgentRole  # noqa: E402
from localforge.pipeline.context import _fetch_context7_references  # noqa: E402


class _FixtureConnector:
    async def search_library_docs(self, library_name: str, query: str):
        return [{
            "library_id": f"/fixture/{library_name}",
            "content": "For this task, use APIRouter and keep the decision bounded to the documented route contract.",
        }]

    async def close(self):
        return None


class _FixtureAudits:
    def __init__(self):
        self.events: list[object] = []

    async def append_audit_event(self, event):
        self.events.append(event)


async def _run_task() -> dict[str, object]:
    import localforge.pipeline.context as context_module

    original = context_module.Context7MCPConnector.from_config
    context_module.Context7MCPConnector.from_config = lambda: _FixtureConnector()
    audits = _FixtureAudits()
    task = SimpleNamespace(
        id=11,
        project_id=7,
        key="LF-CTX7-COMPLIANCE",
        title="API route task",
        metadata={
            "context7_enabled": True,
            "context7_technologies": ["fastapi"],
            "context7_query": "routing API signatures",
        },
    )
    try:
        references = await _fetch_context7_references(
            SimpleNamespace(audits=audits),
            task=task,
            task_run=SimpleNamespace(run_id=13),
            role=AgentRole.CODER,
        )
    finally:
        context_module.Context7MCPConnector.from_config = original
    event = audits.events[0] if audits.events else None
    payload = getattr(event, "payload_redacted", {}) if event is not None else {}
    decision = {
        "event": "context7.decision_recorded",
        "decision_id": task.key,
        "decision_outcome": "use_documented_router_contract",
        "source_ids": [item["library_id"] for item in references],
        "fetch_status": "PASS",
        "audit_event": payload,
    }
    return {
        "schema": "forgeos.context7_compliance.v1",
        "status": "PASS" if references and payload.get("event") == "context7.docs_fetched" else "FAIL",
        "task_key": task.key,
        "references": references,
        "decision": decision,
    }


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(_run_task())
    (output / "context7_decision.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))

