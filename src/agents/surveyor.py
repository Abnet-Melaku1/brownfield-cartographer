import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict

from src.models.schema import ModuleNode
from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph

class Surveyor:
    """Agent 1: Static Structure Analyst determining module dependencies and velocity."""
    
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self.ts_analyzer = TreeSitterAnalyzer()
        
    def analyze_repository(self, repo_path: str):
        """Walks the repository and analyzes structural files."""
        print(f"🕵️ Surveyor starting analysis on: {repo_path}")
        
        # 1. First pass: find all relevant files and compute git velocity
        velocity_map = self._compute_git_velocity(repo_path, days=30)
        
        for root, dirs, files in os.walk(repo_path):
            # Skip hidden and typical venv/build directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '.venv', '__pycache__', 'node_modules', 'target')]
            
            for file in files:
                if not file.endswith(('.py', '.sql', '.yaml', '.yml')):
                    continue
                    
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                # 2. Extract module structural details
                # Very basic complexity heuristic for MVP: lines of code
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = len(f.readlines())
                except Exception:
                    lines = 0
                    
                language = "python" if file.endswith(".py") else "sql" if file.endswith(".sql") else "yaml"
                
                node = ModuleNode(
                    path=rel_path,
                    language=language,
                    complexity_score=lines,
                    change_velocity_30d=velocity_map.get(rel_path, 0)
                )
                
                self.kg.add_module_node(node)
                
                # 3. Extract Imports (Python specific for MVP)
                if language == "python":
                    self._extract_python_imports(file_path, rel_path, repo_path)
                    
        # 4. Run graph analysis (PageRank, Dead Code detection)
        self.kg.analyze_module_graph()
        print("✅ Surveyor completed static analysis pass.")

    def _extract_python_imports(self, abs_path: str, rel_path: str, repo_root: str):
        """Uses tree-sitter to find import statements and add graph edges."""
        # Query for 'import X' and 'from X import Y'
        query = "(import_statement name: (dotted_name) @import)"
        query_from = "(import_from_statement module_name: (dotted_name) @from_import)"
        
        results = self.ts_analyzer.execute_query(abs_path, query)
        results.extend(self.ts_analyzer.execute_query(abs_path, query_from))
        
        for res in results:
            imported_module = res["text"]
            # To properly map to target nodes, we'd need module resolution (jedi/rope)
            # For the interim milestone, we assume top-level package matching or exact strings
            # In a real FDE scenario, we would resolve "app.core.models" to "app/core/models.py"
            
            # Add the edge to the Knowledge Graph
            self.kg.add_import_edge(rel_path, imported_module)
            

    def _compute_git_velocity(self, repo_path: str, days: int = 30) -> Dict[str, int]:
        """Runs git log --follow to compute file change frequency."""
        velocity_map = {}
        since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            # git log --name-only format to count occurrences of files
            cmd = ["git", "log", f"--since={since_date}", "--name-only", "--pretty=format:"]
            result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                velocity_map[line] = velocity_map.get(line, 0) + 1
                
        except Exception as e:
            print(f"⚠️ Could not compute git velocity: {e}. Is this a git repository?")
            
        return velocity_map
