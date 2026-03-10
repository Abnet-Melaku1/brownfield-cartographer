import json
import os
import networkx as nx
from typing import Dict, Any

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
        
        # We separate the graphs to match the required JSON outputs
        self.module_graph = nx.DiGraph()
        self.lineage_graph = nx.DiGraph()
        
        # Ensure output directory exists
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    # -------------------------------------------------------------------------
    # Module Graph Operations (Agent 1: Surveyor)
    # -------------------------------------------------------------------------

    def add_module_node(self, node: ModuleNode):
        """Adds a module to the architecture map."""
        self.module_graph.add_node(node.path, **node.model_dump())

    def add_import_edge(self, source_path: str, target_path: str, weight: int = 1):
        """Adds a directed edge representing an import."""
        self.module_graph.add_edge(source_path, target_path, weight=weight, type="IMPORTS")

    def analyze_module_graph(self):
        """
        Runs PageRank and identifies dead code based on graph topology.
        Updates the node attributes directly in the graph.
        """
        if len(self.module_graph) == 0:
            return

        # 1. PageRank for architectural hubs
        pagerank_scores = nx.pagerank(self.module_graph)
        nx.set_node_attributes(self.module_graph, pagerank_scores, "pagerank")
        
        # 2. Dead code candidates (public modules with no incoming edges)
        # Note: True dead code identification requires function-level graphs, 
        # but module-level in-degree=0 is a strong signal.
        for node in self.module_graph.nodes():
            in_degree = self.module_graph.in_degree(node)
            is_candidate = (in_degree == 0)
            self.module_graph.nodes[node]["is_dead_code_candidate"] = is_candidate

    # -------------------------------------------------------------------------
    # Lineage Graph Operations (Agent 2: Hydrologist)
    # -------------------------------------------------------------------------

    def add_dataset_node(self, node: DatasetNode):
        """Adds a table, file, or stream to the lineage."""
        self.lineage_graph.add_node(node.name, node_type="dataset", **node.model_dump())

    def add_transformation_node(self, node: TransformationNode):
        """Adds a transformation operation to the lineage."""
        # We use a composite key for transformations since they might not have unique names
        transform_id = f"{node.source_file}:{node.line_range}"
        self.lineage_graph.add_node(transform_id, node_type="transformation", **node.model_dump())
        
        # Connect sources to this transformation (CONSUMES)
        for src in node.source_datasets:
            self.lineage_graph.add_edge(src, transform_id, type="CONSUMES")
            
        # Connect this transformation to its targets (PRODUCES)
        for tgt in node.target_datasets:
            self.lineage_graph.add_edge(transform_id, tgt, type="PRODUCES")

    def get_blast_radius(self, dataset_name: str) -> list[str]:
        """BFS downstream to find all dependents of a dataset."""
        if not self.lineage_graph.has_node(dataset_name):
            return []
        
        descendants = nx.descendants(self.lineage_graph, dataset_name)
        return list(descendants)

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def save_to_disk(self):
        """Serializes the NetworkX graphs to JSON files in the output dir."""
        
        module_path = os.path.join(self.output_dir, "module_graph.json")
        module_data = nx.node_link_data(self.module_graph)
        with open(module_path, 'w') as f:
            json.dump(module_data, f, indent=2)
            
        lineage_path = os.path.join(self.output_dir, "lineage_graph.json")
        lineage_data = nx.node_link_data(self.lineage_graph)
        with open(lineage_path, 'w') as f:
            json.dump(lineage_data, f, indent=2)
            
        print(f"✅ Graphs saved to {self.output_dir}")
