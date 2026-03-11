import os
from typing import List

from src.models.schema import DatasetNode, TransformationNode
from src.analyzers.tree_sitter_analyzer import TreeSitterAnalyzer
from src.analyzers.sql_lineage import SQLLineageAnalyzer, JinjaPreProcessor
from src.analyzers.dag_config_parser import DagConfigParser
from src.graph.knowledge_graph import KnowledgeGraph


class Hydrologist:
    """Agent 2: Data Flow & Lineage Analyst — traces data from raw sources to final outputs."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self.ts_analyzer = TreeSitterAnalyzer()
        self.sql_analyzer = SQLLineageAnalyzer()
        self.dag_parser = DagConfigParser()
        self.preprocessor = JinjaPreProcessor()

    def analyze_repository(self, repo_path: str):
        """Walks the repository searching for data transformations and lineage signals."""
        print(f"🌊 Hydrologist starting lineage tracing on: {repo_path}")

        # 0. Register dbt seed files as raw source datasets BEFORE processing SQL
        self._register_seed_sources(repo_path)

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d not in ("venv", "node_modules", "target", "dist", "__pycache__")
            ]

            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)

                if file.endswith(".sql"):
                    self._process_sql_file(file_path, rel_path)

                elif file.endswith(".py"):
                    self._process_python_data_flow(file_path, rel_path)

                elif file.endswith((".yml", ".yaml")):
                    self._process_yaml_config(file_path, rel_path)

        self._print_lineage_summary()
        print("✅ Hydrologist completed lineage DAG construction.")

    # -------------------------------------------------------------------------
    # SQL / dbt Models
    # -------------------------------------------------------------------------

    def _process_sql_file(self, abs_path: str, rel_path: str):
        """Extract table reads/writes from SQL, with Jinja pre-processing for dbt."""
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

            lineage = self.sql_analyzer.extract_lineage(sql_content)
            sources = lineage.get("sources", [])
            targets = lineage.get("targets", [])

            # dbt convention: file name = target table name when no explicit CREATE/INSERT
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
                sql_query=sql_content,
            )
        except Exception as e:
            print(f"⚠️  SQL Lineage failed on {rel_path}: {e}")

    # -------------------------------------------------------------------------
    # Python Data Flow (Pandas / PySpark / SQLAlchemy)
    # -------------------------------------------------------------------------

    def _process_python_data_flow(self, abs_path: str, rel_path: str):
        """
        Uses tree-sitter AST queries to detect pandas/spark read and write calls.
        Extracts source and target dataset names where the path is a string literal.
        """
        # Match: pd.read_csv("path"), spark.read.parquet("path"), df.to_csv("path"), etc.
        read_query = """
        (call
          function: (attribute
            object: (_) @obj
            attribute: (identifier) @method)
          arguments: (argument_list
            (string (string_content) @path)))
        """

        results = self.ts_analyzer.execute_query(abs_path, read_query)

        read_sources: List[str] = []
        write_targets: List[str] = []

        i = 0
        while i < len(results) - 2:
            method = results[i + 1].get("text", "")
            path_val = results[i + 2].get("text", "")

            if method in ("read_csv", "read_parquet", "read_json", "read_sql", "read_table",
                          "read_feather", "read_excel", "load", "read"):
                if path_val:
                    read_sources.append(os.path.basename(path_val).split(".")[0])
            elif method in ("to_csv", "to_parquet", "to_json", "to_sql", "write",
                            "saveAsTable", "save"):
                if path_val:
                    write_targets.append(os.path.basename(path_val).split(".")[0])
            i += 3

        if read_sources or write_targets:
            self._register_transformation(
                sources=read_sources,
                targets=write_targets,
                transform_type="python",
                source_file=rel_path,
                line_range="1-*",
            )

    # -------------------------------------------------------------------------
    # YAML DAG Definitions (dbt schema.yml / sources.yml)
    # -------------------------------------------------------------------------

    def _process_yaml_config(self, abs_path: str, rel_path: str):
        """Extract dataset metadata from dbt schema.yml / sources.yml files."""
        basename = os.path.basename(abs_path)
        if basename in ("schema.yml", "sources.yml"):
            datasets = self.dag_parser.parse_dbt_schema(abs_path)
            for ds in datasets:
                node = DatasetNode(
                    name=ds["name"],
                    storage_type="table",
                    is_source_of_truth=(ds["type"] == "source"),
                )
                self.kg.add_dataset_node(node)

    # -------------------------------------------------------------------------
    # dbt Seeds → raw source datasets
    # -------------------------------------------------------------------------

    def _register_seed_sources(self, repo_path: str):
        """
        Scans for a seeds/ directory and registers each CSV as a raw DatasetNode
        (is_source_of_truth=True) before SQL lineage extraction runs.
        """
        seeds_dir = os.path.join(repo_path, "seeds")
        seeds = self.dag_parser.parse_seed_files(seeds_dir)
        for seed in seeds:
            node = DatasetNode(
                name=seed["name"],
                storage_type="file",
                is_source_of_truth=True,
                schema_snapshot={"columns": seed.get("columns", [])},
            )
            self.kg.add_dataset_node(node)
            if seed["columns"]:
                print(f"   🌱 Seed registered: {seed['name']} {seed['columns']}")

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _register_transformation(
        self,
        sources: List[str],
        targets: List[str],
        transform_type: str,
        source_file: str,
        line_range: str,
        sql_query: str = None,
    ):
        """Creates dataset nodes + transformation node and wires all edges."""
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
            sql_query_if_applicable=sql_query,
        )
        self.kg.add_transformation_node(t_node)

    def _print_lineage_summary(self):
        """Prints a quick summary of sources, sinks, and edge count."""
        n_nodes = self.kg.lineage_graph.number_of_nodes()
        n_edges = self.kg.lineage_graph.number_of_edges()
        sources = self.kg.find_sources()
        sinks = self.kg.find_sinks()

        print(f"\n   📊 Lineage graph: {n_nodes} nodes, {n_edges} edges")
        print(f"   ⬆️  Sources : {sources or 'none detected'}")
        print(f"   ⬇️  Sinks   : {sinks or 'none detected'}")
