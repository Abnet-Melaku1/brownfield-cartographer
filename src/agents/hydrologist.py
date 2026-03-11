import os
from typing import List

from src.models.schema import DatasetNode, TransformationNode
from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer
from src.analyzers.sql_lineage import SQLLineageAnalyzer
from src.analyzers.dag_config_parser import DagConfigParser
from src.graph.knowledge_graph import KnowledgeGraph

class Hydrologist:
    """Agent 2: Data Flow & Lineage Analyst tracking data sources and transformations."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self.ts_analyzer = TreeSitterAnalyzer()
        self.sql_analyzer = SQLLineageAnalyzer()
        self.dag_parser = DagConfigParser()

    def analyze_repository(self, repo_path: str):
        """Walks the repository specifically searching for data transformations."""
        print(f"🌊 Hydrologist starting lineage tracing on: {repo_path}")

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', 'node_modules', 'target')]
            
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                
                # 1. SQL / dbt Models
                if file.endswith('.sql'):
                    self._process_sql_file(file_path, rel_path)
                    
                # 2. Python Data Flow (Pandas, PySpark, SQLAlchemy)
                elif file.endswith('.py'):
                    self._process_python_data_flow(file_path, rel_path)
                    
                # 3. YAML DAG definitions (Airflow / dbt schemas)
                elif file.endswith(('.yml', '.yaml')):
                    self._process_yaml_config(file_path, rel_path)
                    
        print("✅ Hydrologist completed lineage DAG construction.")

    def _process_sql_file(self, abs_path: str, rel_path: str):
        """Extract table reads/writes from SQL blocks."""
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
                
            lineage = self.sql_analyzer.extract_lineage(sql_content)
            sources = lineage.get("sources", [])
            targets = lineage.get("targets", [])
            
            # If no targets found and this is just a regular SELECT, infer target from filename
            # This is standard for tools like dbt where file=model=target_table
            if not targets and sources:
                base_name = os.path.basename(rel_path).replace(".sql", "")
                targets = [base_name]

            if not sources and not targets:
                return

            self._register_transformation(
                sources=sources,
                targets=targets,
                transform_type="sql",
                source_file=rel_path,
                line_range="1-*",
                sql_query=sql_content
            )
        except Exception as e:
            print(f"⚠️ SQL Lineage Failed on {rel_path}: {e}")

    def _process_python_data_flow(self, abs_path: str, rel_path: str):
        """Uses tree-sitter AST queries to hunt for pandas and spark data calls."""
        # Query: find pd.read_csv("file.csv") or spark.read.json(...) etc
        query_read = "(call function: (attribute object: (identifier) attribute: (identifier) @method) arguments: (argument_list (string (string_content) @arg)))"
        
        reads = self.ts_analyzer.execute_query(abs_path, query_read)
        
        for res in reads:
            if "read" in res["text"]:
                arg = "" # TODO: Properly map sibling captures
                # For interim, this acts as a placeholder pattern structure
                
        # Full Python AST data flow mapping requires symbol resolving.
        # For this interim phase, we rely predominantly on SQL and YAML.

    def _process_yaml_config(self, abs_path: str, rel_path: str):
        """Extract metadata and lineage hints from schema.yml files."""
        if "schema.yml" in abs_path or "sources.yml" in abs_path:
            datasets = self.dag_parser.parse_dbt_schema(abs_path)
            
            for ds in datasets:
                node = DatasetNode(
                    name=ds["name"],
                    storage_type="table",
                    is_source_of_truth=(ds["type"] == "source")
                )
                self.kg.add_dataset_node(node)

    def _register_transformation(self, sources: List[str], targets: List[str], transform_type: str, source_file: str, line_range: str, sql_query: str = None):
        """Helper to create transformation node and associated dataset nodes."""
        # Make dataset nodes exist if they don't already
        for src in sources:
            self.kg.add_dataset_node(DatasetNode(name=src, storage_type="table"))
        for tgt in targets:
            self.kg.add_dataset_node(DatasetNode(name=tgt, storage_type="table"))
            
        t_node = TransformationNode(
            source_datasets=sources,
            target_datasets=targets,
            transformation_type=transform_type,
            source_file=source_file,
            line_range=line_range,
            sql_query_if_applicable=sql_query
        )
        self.kg.add_transformation_node(t_node)
