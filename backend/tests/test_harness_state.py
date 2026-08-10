import json

import pytest

from localforge.runtime.harness_state import HarnessEntry, HarnessState


def test_harness_state_survives_fresh_instance_and_snapshots_before_mutation(tmp_path):
    state = HarnessState(tmp_path)
    entry = HarnessEntry(
        id="memory-1",
        kind="memory",
        scope="project",
        content="Use targeted validation.",
    )

    state.upsert(entry)

    assert state.state_path == tmp_path / ".localforge" / "harness" / "harness_state.json"
    assert state.snapshot_path.is_file()
    assert len(state.list_snapshots()) == 1
    snapshot_payload = json.loads(state.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot_payload["entries"] == []

    fresh_state = HarnessState(tmp_path)
    assert fresh_state.get("memory-1").content == "Use targeted validation."
    assert json.loads(fresh_state.state_path.read_text(encoding="utf-8"))["revision"] == 1

    fresh_state.upsert(entry.model_copy(update={"content": "Use focused validation."}))
    assert len(fresh_state.list_snapshots()) == 2
    previous_payload = json.loads(fresh_state.list_snapshots()[1].read_text(encoding="utf-8"))
    assert previous_payload["entries"][0]["content"] == "Use targeted validation."


def test_refine_records_evidence_and_protects_base_and_system_entries(tmp_path):
    state = HarnessState(tmp_path)
    supplemental = state.upsert(
        HarnessEntry(
            id="supplement-1",
            kind="memory",
            scope="local",
            content="initial",
        )
    )

    event = state.refine(
        supplemental.id,
        {"test": "focused", "passed": True},
        {"content": "refined"},
        metadata={"confidence": 0.9},
    )

    assert event.entry_id == supplemental.id
    assert event.evidence["passed"] is True
    assert state.get(supplemental.id).content == "refined"
    assert state.get(supplemental.id).metadata["confidence"] == 0.9
    assert state.list_refinements(supplemental.id)[0].evidence["test"] == "focused"

    state.upsert(
        HarnessEntry(
            id="system-1",
            kind="prompt",
            scope="global",
            content="Never change this base prompt.",
            is_system_prompt=True,
        )
    )
    with pytest.raises(ValueError, match="only supplemental"):
        state.refine("system-1", {"attempt": "blocked"}, {"content": "changed"})
    assert state.get("system-1").content == "Never change this base prompt."

