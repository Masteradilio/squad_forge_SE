"""Release tree inventory, checksum, and sanitization helpers."""

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./:=+]{12,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
)
PERSONAL_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\Projetos\\[^\\\s]+", re.IGNORECASE),
)
FORBIDDEN_TRACKED_SUFFIXES = (
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-journal",
    ".gguf",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
)


class ReleaseTreeReport(BaseModel):
    """Serializable release-tree audit report."""

    schema_version: str = "localforge.v6_2.release_tree_report.v1"
    scope: str
    tracked_files: int
    checksums: dict[str, str] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


@dataclass(frozen=True)
class ReleaseTreeAuditor:
    repo_root: Path
    max_text_bytes: int = 750_000
    excluded_dirs: set[str] = field(
        default_factory=lambda: {
            ".git",
            ".localforge",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            ".codex_venv",
            "node_modules",
            "dist",
            "build",
        }
    )

    def audit(self, scope: Path | str = ".", exclude_paths: set[str] | None = None) -> ReleaseTreeReport:
        scope_path = (self.repo_root / scope).resolve()
        excluded_relatives = exclude_paths or set()
        files = self._tracked_files(scope_path)
        checksums: dict[str, str] = {}
        findings: list[str] = []
        audited_files = 0
        for file_path in files:
            relative = file_path.relative_to(self.repo_root).as_posix()
            if relative in excluded_relatives:
                continue
            audited_files += 1
            suffix = file_path.suffix.lower()
            if suffix in FORBIDDEN_TRACKED_SUFFIXES:
                findings.append(f"forbidden tracked runtime/binary artifact: {relative}")
                continue
            content = file_path.read_bytes()
            checksums[relative] = hashlib.sha256(content).hexdigest()
            if len(content) <= self.max_text_bytes and _looks_text(file_path):
                text = content.decode("utf-8", errors="ignore")
                if any(pattern.search(text) for pattern in SECRET_TEXT_PATTERNS):
                    findings.append(f"possible secret material in tracked file: {relative}")
                if any(pattern.search(text) for pattern in PERSONAL_PATH_PATTERNS):
                    findings.append(f"possible personal local path in tracked file: {relative}")
        return ReleaseTreeReport(
            scope=scope_path.relative_to(self.repo_root).as_posix(),
            tracked_files=audited_files,
            checksums=checksums,
            findings=sorted(set(findings)),
        )

    def _tracked_files(self, scope_path: Path) -> list[Path]:
        try:
            result = subprocess.run(
                ["git", "ls-files", "--", str(scope_path.relative_to(self.repo_root))],
                cwd=self.repo_root,
                check=True,
                text=True,
                capture_output=True,
            )
            raw_paths = [line for line in result.stdout.splitlines() if line.strip()]
        except (subprocess.CalledProcessError, ValueError):
            raw_paths = [
                path.relative_to(self.repo_root).as_posix()
                for path in scope_path.rglob("*")
                if path.is_file() and not self._is_excluded(path)
            ]
        return [self.repo_root / raw_path for raw_path in raw_paths if (self.repo_root / raw_path).is_file()]

    def _is_excluded(self, path: Path) -> bool:
        return any(part in self.excluded_dirs for part in path.parts)


def _looks_text(path: Path) -> bool:
    return path.suffix.lower() in {
        ".css",
        ".html",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
