"""Best-effort process-tree ownership and termination for local sandboxes."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProcessTreeEvidence:
    pid: int
    strategy: str
    reason: str
    result: str
    isolation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "strategy": self.strategy,
            "reason": self.reason,
            "result": self.result,
            "isolation": self.isolation,
        }


class ProcessTreeController:
    """Own a child process tree and report honestly how it was cleaned up.

    Windows uses ``taskkill /T`` as the available tree-termination equivalent
    for this local runner.  It is recorded as PROVEN only when the OS command
    succeeds; all fallback paths are explicitly NOT_PROVEN.
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._evidence: ProcessTreeEvidence | None = None

    def attach(self, proc: asyncio.subprocess.Process) -> None:
        self._process = proc

    @property
    def evidence(self) -> ProcessTreeEvidence | None:
        return self._evidence

    async def terminate(self, proc: asyncio.subprocess.Process, reason: str) -> ProcessTreeEvidence:
        if proc.returncode is not None:
            self._evidence = ProcessTreeEvidence(proc.pid, "already-exited", reason, "NOOP", "PROVEN")
            return self._evidence
        if os.name == "nt":
            result = await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                strategy, outcome, isolation = "windows-taskkill-tree", "TERMINATED", "PROVEN"
            else:
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except (OSError, ProcessLookupError):
                    pass
                strategy, outcome, isolation = "windows-process-group-fallback", "FALLBACK", "NOT_PROVEN"
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                strategy, outcome, isolation = "posix-process-group", "TERMINATED", "PROVEN"
            except (OSError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                strategy, outcome, isolation = "posix-process-fallback", "FALLBACK", "NOT_PROVEN"
        self._evidence = ProcessTreeEvidence(proc.pid, strategy, reason, outcome, isolation)
        try:
            await asyncio.wait_for(asyncio.shield(proc.wait()), timeout=5.0)
        except (TimeoutError, ProcessLookupError):
            pass
        return self._evidence
