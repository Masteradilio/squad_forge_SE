"""Graphify Engine — AST Tree-Sitter Knowledge Graph & GRAPH_REPORT.md Generator."""

import ast
import json
import logging
from pathlib import Path
from typing import Any

from localforge.services.semantic_cache import SemanticCacheManager

logger = logging.getLogger(__name__)


class GraphifyEngine:
    """Build a deterministic code graph with dependency-free Python AST parsing.

    Python files use the stdlib AST today; other supported files are indexed as
    file nodes. The report therefore remains truthful when optional Tree-Sitter
    packages are not installed.
    """

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.cache = SemanticCacheManager()

    def build_codebase_graph(self) -> dict[str, Any]:
        """Parse source code files deterministically and build structural AST call graph."""
        cached_graph = self.cache.get_ast_graph(self.workspace_path)
        if cached_graph:
            return cached_graph

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []

        for ext in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.html", "*.css"]:
            for filepath in self.workspace_path.glob(f"**/{ext}"):
                if any(ignored in str(filepath) for ignored in [".git", "node_modules", ".venv", "dist", ".localforge"]):
                    continue

                rel_path = str(filepath.relative_to(self.workspace_path))
                nodes.append({
                    "id": rel_path,
                    "type": "file",
                    "extension": filepath.suffix,
                    "size_bytes": filepath.stat().st_size
                })
                if filepath.suffix == ".py":
                    self._append_python_edges(filepath, rel_path, edges)

        graph_data = {
            "version": "1.0.0",
            "nodes_count": len(nodes),
            "nodes": nodes,
            "edges": edges
        }

        # Save graph.json
        graph_json_path = self.workspace_path / ".localforge" / "graph.json"
        graph_json_path.parent.mkdir(parents=True, exist_ok=True)
        graph_json_path.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")

        # Save GRAPH_REPORT.md (0 LLM tokens)
        graph_report_path = self.workspace_path / ".localforge" / "GRAPH_REPORT.md"
        report_content = "# 🕸️ Graphify Codebase Architecture Report\n\n"
        report_content += f"- **Total Index Files**: {len(nodes)}\n"
        report_content += "- **AST Parsing Engine**: Python stdlib AST (0 API Tokens)\n\n"
        report_content += "## 📁 Indexed Components\n"
        for n in nodes[:20]:
            report_content += f"- `{n['id']}` ({n['size_bytes']} bytes)\n"
        if len(nodes) > 20:
            report_content += f"- ... and {len(nodes) - 20} more files.\n"

        graph_report_path.write_text(report_content, encoding="utf-8")
        self.cache.set_ast_graph(self.workspace_path, graph_data)
        logger.info(f"Graphify built AST graph with {len(nodes)} nodes cleanly.")

        return graph_data

    @staticmethod
    def _append_python_edges(
        filepath: Path, source_id: str, edges: list[dict[str, str]]
    ) -> None:
        """Extract deterministic import and call edges without LLM tokens."""
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append({"source": source_id, "target": alias.name, "kind": "import"})
            elif isinstance(node, ast.ImportFrom) and node.module:
                edges.append({"source": source_id, "target": node.module, "kind": "import"})
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    name = function.id
                elif isinstance(function, ast.Attribute):
                    name = function.attr
                else:
                    continue
                edges.append({"source": source_id, "target": name, "kind": "call"})
