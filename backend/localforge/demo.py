"""Deterministic CPU-only demo scenario and static evidence replay export."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from localforge.services.security_controls import redact_secrets_recursive
from localforge.version import VERSION


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return self.stdout + self.stderr


class DemoEvidenceRecord(BaseModel):
    """One replayable demo evidence record."""

    id: str
    kind: str
    title: str
    summary: str
    path: str | None = None
    sha256: str | None = None
    command: str | None = None
    exit_code: int | None = None


class DemoRun(BaseModel):
    """Schema-versioned deterministic demo export."""

    schema_version: str = "localforge.v6_2.demo_run.v1"
    localforge_version: str = VERSION
    scenario: str
    deterministic: bool = True
    model_calls: int = 0
    paid_api_calls: int = 0
    worker_output_mode: str = "deterministic_replay_not_live_model"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str
    event: dict[str, Any]
    timeline: list[DemoEvidenceRecord]
    checksums: dict[str, str]


def run_ci_regression_demo(output_dir: Path) -> DemoRun:
    """Run the deterministic CI-regression demo in a disposable local Git repo."""
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = output_dir / "repo"
    worktrees_dir = output_dir / "worktrees"
    artifacts_dir = output_dir / "artifacts"
    _reset_dir(repo_dir)
    _reset_dir(worktrees_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    _run(["git", "init"], cwd=repo_dir)
    _run(["git", "config", "user.email", "demo@localforge.local"], cwd=repo_dir)
    _run(["git", "config", "user.name", "LocalForge Demo"], cwd=repo_dir)
    (repo_dir / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
        newline="\n",
    )
    (repo_dir / "test_calculator.py").write_text(
        "from calculator import add\n\n\ndef test_addition() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
        newline="\n",
    )
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "seed failing calculator regression"], cwd=repo_dir)

    failing = _run([sys.executable, "-m", "pytest", "test_calculator.py", "-q"], cwd=repo_dir, check=False)
    worktree_dir = (worktrees_dir / "ci-regression-fix").resolve()
    _run(["git", "worktree", "add", "-b", "lf-demo-ci-regression", str(worktree_dir)], cwd=repo_dir)
    (worktree_dir / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
        newline="\n",
    )
    passing = _run(
        [sys.executable, "-m", "pytest", "test_calculator.py", "-q"],
        cwd=worktree_dir,
    )
    diff = _run(["git", "diff", "--", "calculator.py"], cwd=worktree_dir).stdout

    files = {
        "failing_test.log": failing.combined_output,
        "passing_test.log": passing.combined_output,
        "diff.patch": diff,
        "draft_pr.md": _draft_pr_body(passing.combined_output),
    }
    checksums: dict[str, str] = {}
    for relative_path, content in files.items():
        target = artifacts_dir / relative_path
        target.write_text(content, encoding="utf-8", newline="\n")
        checksums[f"artifacts/{relative_path}"] = _sha256_file(target)

    event = {
        "id": "DEMO-CI-REGRESSION-001",
        "kind": "ci-regression",
        "summary": "A deterministic test failure is repaired in an isolated Git worktree.",
        "source": "local CPU-only demo fixture",
    }
    timeline = [
        DemoEvidenceRecord(
            id="event",
            kind="event",
            title="CI regression event",
            summary=event["summary"],
        ),
        DemoEvidenceRecord(
            id="triage",
            kind="triage",
            title="Cheap triage",
            summary="Classified as AUTO_FIX without model inference.",
        ),
        DemoEvidenceRecord(
            id="worktree",
            kind="worktree",
            title="Isolated worktree",
            summary="Created branch lf-demo-ci-regression in a disposable local Git worktree.",
        ),
        DemoEvidenceRecord(
            id="failing-test",
            kind="test",
            title="Baseline failing test",
            summary="Initial repository state reproduces the CI regression.",
            path="artifacts/failing_test.log",
            sha256=checksums["artifacts/failing_test.log"],
            command="python -m pytest test_calculator.py -q",
            exit_code=failing.returncode,
        ),
        DemoEvidenceRecord(
            id="diff",
            kind="diff",
            title="Deterministic patch",
            summary="The worktree changes subtraction to addition.",
            path="artifacts/diff.patch",
            sha256=checksums["artifacts/diff.patch"],
        ),
        DemoEvidenceRecord(
            id="passing-test",
            kind="test",
            title="Verification gate",
            summary="The same test passes after the patch.",
            path="artifacts/passing_test.log",
            sha256=checksums["artifacts/passing_test.log"],
            command="python -m pytest test_calculator.py -q",
            exit_code=passing.returncode,
        ),
        DemoEvidenceRecord(
            id="draft-pr",
            kind="draft-pr",
            title="Draft PR artifact",
            summary="A reviewable PR note is generated without merging.",
            path="artifacts/draft_pr.md",
            sha256=checksums["artifacts/draft_pr.md"],
        ),
    ]
    demo = DemoRun(
        scenario="ci-regression",
        status="PR_READY" if passing.returncode == 0 and failing.returncode != 0 else "FAILED_SAFE",
        event=event,
        timeline=timeline,
        checksums=checksums,
    )
    sanitized = redact_secrets_recursive(demo.model_dump(mode="json"))
    demo_path = output_dir / "demo_run.json"
    demo_path.write_text(
        json.dumps(sanitized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _write_static_replay(output_dir / "demo_replay.html", sanitized)
    checksums["demo_run.json"] = _sha256_file(demo_path)
    _remove_tree(repo_dir)
    _remove_tree(worktrees_dir)
    return demo


def _draft_pr_body(test_output: str) -> str:
    return (
        "# Draft PR: Fix CI regression in calculator addition\n\n"
        "## Summary\n"
        "- Reproduced failing test in a disposable repository.\n"
        "- Applied deterministic patch in an isolated worktree.\n"
        "- Re-ran the acceptance test successfully.\n\n"
        "## Verification\n\n"
        "```text\n"
        f"{test_output.strip()}\n"
        "```\n"
    )


def _write_static_replay(path: Path, demo_payload: object) -> None:
    data = json.dumps(demo_payload, sort_keys=True)
    # Keep untrusted demo fields out of executable HTML and render them through
    # textContent instead of interpolating them into innerHTML.
    safe_json = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    path.write_text(
        "<!doctype html><meta charset=\"utf-8\"><title>LocalForge Demo Replay</title>"
        "<main id=\"app\"></main><script>"
        f"const demo=JSON.parse({json.dumps(safe_json)});"
        "const app=document.getElementById('app');"
        "const heading=document.createElement('h1'); heading.textContent=demo.scenario; app.append(heading);"
        "const status=document.createElement('p'); status.textContent='Status: '+demo.status; app.append(status);"
        "const mode=document.createElement('p'); mode.textContent='Mode: '+demo.worker_output_mode; app.append(mode);"
        "const timeline=document.createElement('ol');"
        "demo.timeline.forEach(e=>{const item=document.createElement('li');"
        "item.textContent=String(e.title)+': '+String(e.summary); timeline.append(item);});"
        "app.append(timeline);"
        "</script>",
        encoding="utf-8",
        newline="\n",
    )


def _reset_dir(path: Path) -> None:
    if path.exists():
        _remove_tree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_tree(path: Path) -> None:
    def on_readonly_error(
        function: Callable[[str], object],
        target: str,
        exc_info: object,
    ) -> None:
        del exc_info
        os.chmod(target, 0o700)
        function(target)

    shutil.rmtree(path, onerror=on_readonly_error)


def _run(command: list[str], cwd: Path, check: bool = True) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    command_result = CommandResult(
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{command_result.combined_output}")
    return command_result


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
