import json
import os
import networkx as nx
from typing import Dict, Any, List

from src.models.schema import (
    ModuleNode,
    DatasetNode,
    FunctionNode,
    TransformationNode,
)


class KnowledgeGraph:
    """
    Central data store for The Brownfield Cartographer.
    Wraps separate NetworkX Directed Graphs for Modules and Data Lineage.
    """

    def __init__(self, output_dir: str = ".cartography"):
        self.output_dir = output_dir

        # Separate graphs to match the required JSON outputs
        self.module_graph = nx.DiGraph()
        self.lineage_graph = nx.DiGraph()

        os.makedirs(self.output_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Module Graph Operations (Agent 1: Surveyor)
    # -------------------------------------------------------------------------

    def add_module_node(self, node: ModuleNode):
        """Adds a module to the architecture map."""
        self.module_graph.add_node(node.path, **node.model_dump())

    def add_import_edge(self, source_path: str, target_path: str, weight: int = 1):
        """Adds a directed edge representing an import dependency."""
        self.module_graph.add_edge(source_path, target_path, weight=weight, type="IMPORTS")

    def analyze_module_graph(self):
        """
        Runs PageRank, detects dead code candidates, and finds circular dependencies.
        Updates node attributes in-place.
        """
        if len(self.module_graph) == 0:
            return

        # 1. PageRank — identifies architectural hubs
        pagerank_scores = nx.pagerank(self.module_graph)
        nx.set_node_attributes(self.module_graph, pagerank_scores, "pagerank")

        # 2. Dead code candidates — modules with no incoming edges that are
        #    not entry points (we cross-reference with change_velocity_30d to
        #    avoid flagging active entry points as dead code)
        for node in self.module_graph.nodes():
            in_deg = self.module_graph.in_degree(node)
            velocity = self.module_graph.nodes[node].get("change_velocity_30d", 0) or 0
            # Flag as candidate only if no imports AND no recent git activity
            is_candidate = (in_deg == 0) and (velocity == 0)
            self.module_graph.nodes[node]["is_dead_code_candidate"] = is_candidate

        # 3. Circular dependency detection via strongly connected components
        cycles = self.detect_circular_dependencies()
        if cycles:
            print(f"⚠️  Circular dependencies detected in {len(cycles)} component(s):")
            for cycle in cycles:
                print(f"    → {' ↔ '.join(cycle)}")

    def detect_circular_dependencies(self) -> List[List[str]]:
        """
        Returns all non-trivial strongly connected components (i.e. cycles) in the
        module graph. Each entry is a list of node paths that form a cycle.
        """
        cycles = []
        for scc in nx.strongly_connected_components(self.module_graph):
            if len(scc) > 1:
                cycles.append(sorted(scc))
        return cycles

    # -------------------------------------------------------------------------
    # Lineage Graph Operations (Agent 2: Hydrologist)
    # -------------------------------------------------------------------------

    def add_dataset_node(self, node: DatasetNode):
        """Adds a table, file, or stream to the lineage graph (idempotent)."""
        if not self.lineage_graph.has_node(node.name):
            self.lineage_graph.add_node(node.name, node_type="dataset", **node.model_dump())

    def add_transformation_node(self, node: TransformationNode):
        """Adds a transformation and wires its CONSUMES/PRODUCES edges."""
        transform_id = f"{node.source_file}:{node.line_range}"
        self.lineage_graph.add_node(transform_id, node_type="transformation", **node.model_dump())

        for src in node.source_datasets:
            self.lineage_graph.add_edge(src, transform_id, type="CONSUMES")

        for tgt in node.target_datasets:
            self.lineage_graph.add_edge(transform_id, tgt, type="PRODUCES")

    def get_blast_radius(self, dataset_name: str) -> List[str]:
        """BFS downstream to find all nodes affected if dataset_name breaks."""
        if not self.lineage_graph.has_node(dataset_name):
            return []
        return list(nx.descendants(self.lineage_graph, dataset_name))

    def find_sources(self) -> List[str]:
        """
        Returns all dataset nodes that have no upstream producers —
        i.e. raw data sources / seeds that nothing writes to.
        """
        return [
            n for n, data in self.lineage_graph.nodes(data=True)
            if data.get("node_type") == "dataset"
            and self.lineage_graph.in_degree(n) == 0
        ]

    def find_sinks(self) -> List[str]:
        """
        Returns all dataset nodes with no downstream consumers —
        i.e. final output tables/marts that nothing reads from.
        """
        return [
            n for n, data in self.lineage_graph.nodes(data=True)
            if data.get("node_type") == "dataset"
            and self.lineage_graph.out_degree(n) == 0
        ]

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def save_to_disk(self):
        """Serializes both NetworkX graphs to JSON files in the output directory."""

        module_path = os.path.join(self.output_dir, "module_graph.json")
        with open(module_path, "w") as f:
            json.dump(nx.node_link_data(self.module_graph), f, indent=2)

        lineage_path = os.path.join(self.output_dir, "lineage_graph.json")
        with open(lineage_path, "w") as f:
            json.dump(nx.node_link_data(self.lineage_graph), f, indent=2)

        print(f"✅ Graphs saved to {self.output_dir}/")

        # Print lineage summary for quick sanity check
        sources = self.find_sources()
        sinks = self.find_sinks()
        n_edges = self.lineage_graph.number_of_edges()
        print(f"   Lineage: {self.lineage_graph.number_of_nodes()} nodes, {n_edges} edges")
        if sources:
            print(f"   Sources (raw inputs) : {sources}")
        if sinks:
            print(f"   Sinks   (final outputs): {sinks}")
