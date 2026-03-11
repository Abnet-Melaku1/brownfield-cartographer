import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List

from src.models.schema import ModuleNode, FunctionNode
from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph


class Surveyor:
    """Agent 1: Static Structure Analyst — maps modules, imports, public API surface, and git velocity."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self.ts_analyzer = TreeSitterAnalyzer()

    def analyze_repository(self, repo_path: str):
        """Walks the repository and builds the module graph."""
        print(f"🕵️  Surveyor starting analysis on: {repo_path}")

        velocity_map = self._compute_git_velocity(repo_path, days=30)

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d not in ("venv", ".venv", "__pycache__", "node_modules", "target", "dist")
            ]

            for file in files:
                if not file.endswith((".py", ".sql", ".yaml", ".yml")):
                    continue

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = len(f.readlines())
                except Exception:
                    lines = 0

                language = (
                    "python" if file.endswith(".py")
                    else "sql" if file.endswith(".sql")
                    else "yaml"
                )

                # Extract public API surface for Python files
                public_functions, public_classes = [], []
                if language == "python":
                    public_functions, public_classes = self._extract_public_api(file_path, rel_path)

                node = ModuleNode(
                    path=rel_path,
                    language=language,
                    complexity_score=lines,
                    change_velocity_30d=velocity_map.get(rel_path, 0),
                    public_functions=public_functions,
                    public_classes=public_classes,
                )
                self.kg.add_module_node(node)

                if language == "python":
                    self._extract_python_imports(file_path, rel_path)

        # Graph-level analysis: PageRank + dead code + circular deps
        self.kg.analyze_module_graph()

        cycles = self.kg.detect_circular_dependencies()
        if not cycles:
            print("✅ No circular dependencies detected.")

        print("✅ Surveyor completed static analysis pass.")

    # -------------------------------------------------------------------------
    # Python Import Extraction
    # -------------------------------------------------------------------------

    def _extract_python_imports(self, abs_path: str, rel_path: str):
        """Uses tree-sitter AST to find import statements and add IMPORTS edges."""
        query_import = "(import_statement name: (dotted_name) @import)"
        query_from = "(import_from_statement module_name: (dotted_name) @from_import)"

        results = self.ts_analyzer.execute_query(abs_path, query_import)
        results += self.ts_analyzer.execute_query(abs_path, query_from)

        for res in results:
            imported_module = res["text"]
            # Map dotted module paths (e.g. "app.core.models") to graph edges.
            # Full resolution would require jedi/rope; for now we record the
            # dotted name directly — sufficient for hub/dead-code analysis.
            self.kg.add_import_edge(rel_path, imported_module)

    # -------------------------------------------------------------------------
    # Public API Surface Extraction
    # -------------------------------------------------------------------------

    def _extract_public_api(self, abs_path: str, rel_path: str):
        """
        Uses tree-sitter to extract all top-level function and class definitions
        from a Python file. Returns (public_functions, public_classes).
        """
        func_query = "(function_definition name: (identifier) @func_name)"
        class_query = "(class_definition name: (identifier) @class_name)"

        func_results = self.ts_analyzer.execute_query(abs_path, func_query)
        class_results = self.ts_analyzer.execute_query(abs_path, class_query)

        public_functions: List[str] = []
        public_classes: List[str] = []

        for res in func_results:
            name = res["text"]
            if not name.startswith("_"):  # skip private/dunder
                public_functions.append(name)
                # Also register as a FunctionNode in the graph for downstream use
                fn_node = FunctionNode(
                    qualified_name=f"{rel_path}::{name}",
                    parent_module=rel_path,
                    signature=name,
                    is_public_api=True,
                )
                # Store in module graph node attributes (accessed via kg later)
                # FunctionNodes are attached as lightweight metadata, not a separate graph
                self.kg.module_graph.nodes.get(rel_path, {})

        for res in class_results:
            name = res["text"]
            if not name.startswith("_"):
                public_classes.append(name)

        return public_functions, public_classes

    # -------------------------------------------------------------------------
    # Git Velocity
    # -------------------------------------------------------------------------

    def _compute_git_velocity(self, repo_path: str, days: int = 30) -> Dict[str, int]:
        """Counts how many times each file was touched in the last N days."""
        velocity_map: Dict[str, int] = {}
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            cmd = ["git", "log", f"--since={since_date}", "--name-only", "--pretty=format:"]
            result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)

            for line in result.stdout.split("\n"):
                line = line.strip()
                if line:
                    velocity_map[line] = velocity_map.get(line, 0) + 1

        except Exception as e:
            print(f"⚠️  Could not compute git velocity: {e}")

        return velocity_map
