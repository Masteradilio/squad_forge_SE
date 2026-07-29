import subprocess
from pathlib import Path

from localforge.services.release_audit import ReleaseTreeAuditor


def test_release_tree_auditor_passes_clean_tracked_scope(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "report.md").write_text("# clean\n", encoding="utf-8")
    _git(tmp_path, "add", "docs/report.md")
    _git(tmp_path, "commit", "-m", "clean")

    report = ReleaseTreeAuditor(tmp_path).audit("docs")

    assert report.passed is True
    assert report.tracked_files == 1
    assert "docs/report.md" in report.checksums


def test_release_tree_auditor_flags_forbidden_tracked_content(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "token=super-secret-token-value C:\\Users\\Adilio\\secret\n",
        encoding="utf-8",
    )
    (tmp_path / "local.db").write_text("sqlite", encoding="utf-8")
    _git(tmp_path, "add", "notes.md", "local.db")
    _git(tmp_path, "commit", "-m", "bad")

    report = ReleaseTreeAuditor(tmp_path).audit(".")

    assert report.passed is False
    assert any("possible secret material" in finding for finding in report.findings)
    assert any("possible personal local path" in finding for finding in report.findings)
    assert any("forbidden tracked runtime" in finding for finding in report.findings)


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.local")
    _git(path, "config", "user.name", "Test User")


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
