from __future__ import annotations

import pytest
from localforge.sandbox.local import LocalSandbox


@pytest.mark.asyncio
async def test_local_sandbox_records_process_tree_strategy(tmp_path):
    sandbox = LocalSandbox(str(tmp_path))
    await sandbox.create()
    command = 'python -c "import time; time.sleep(10)"'
    with pytest.raises(TimeoutError):
        await sandbox.execute(command, timeout=0.1)
    evidence = sandbox.process_tree_evidence()
    assert evidence is not None
    assert evidence["pid"] > 0
    assert evidence["reason"] == "timeout_or_cancel"
    assert evidence["strategy"]
    assert evidence["isolation"] in {"PROVEN", "NOT_PROVEN"}
    await sandbox.destroy()
