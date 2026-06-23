import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from localforge.models.enums import FailureClass


@dataclass(frozen=True)
class ContractFinding:
    failure_class: FailureClass
    message: str
    file_path: str | None = None


@dataclass(frozen=True)
class ContractVerifierResult:
    passed: bool
    findings: list[ContractFinding] = field(default_factory=list)


class ContractVerifier:
    def verify(
        self,
        *,
        worktree_path: str,
        task_contract: dict[str, Any],
        changed_files: list[str],
    ) -> ContractVerifierResult:
        findings: list[ContractFinding] = []
        allowed = _string_set(task_contract.get("allowed_files"))
        required_apis = _string_set(task_contract.get("required_public_apis"))
        forbidden_deps = _string_set(task_contract.get("forbidden_dependencies"))

        if allowed:
            for rel_path in changed_files:
                normalized = _normalize(rel_path)
                if normalized not in allowed:
                    findings.append(
                        ContractFinding(
                            FailureClass.CONTRACT_DRIFT,
                            f"Changed file is outside task contract: {normalized}",
                            normalized,
                        )
                    )

        exported_symbols: set[str] = set()
        for rel_path in changed_files:
            if not rel_path.endswith(".py"):
                continue
            path = Path(worktree_path) / rel_path
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text, filename=rel_path)
            except SyntaxError as exc:
                findings.append(
                    ContractFinding(
                        FailureClass.SYNTAX_ERROR,
                        f"{exc.msg} at line {exc.lineno}",
                        _normalize(rel_path),
                    )
                )
                continue
            exported_symbols.update(_exports(tree))
            imported = _imports(tree)
            for dependency in sorted(imported & forbidden_deps):
                findings.append(
                    ContractFinding(
                        FailureClass.FORBIDDEN_DEPENDENCY,
                        f"Forbidden dependency imported: {dependency}",
                        _normalize(rel_path),
                    )
                )

        for symbol in sorted(required_apis - exported_symbols):
            findings.append(
                ContractFinding(
                    FailureClass.PUBLIC_API_MISMATCH,
                    f"Required public API is missing: {symbol}",
                )
            )
        return ContractVerifierResult(passed=not findings, findings=findings)


def _exports(tree: ast.AST) -> set[str]:
    exports: set[str] = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            exports.add(node.name)
    return exports


def _imports(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    return imported


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {_normalize(item) for item in value if isinstance(item, str)}


def _normalize(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/").lstrip("/")
