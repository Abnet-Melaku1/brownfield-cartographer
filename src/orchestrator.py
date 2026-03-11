import os
from src.graph.knowledge_graph import KnowledgeGraph
from src.agents.surveyor import Surveyor
from src.agents.hydrologist import Hydrologist


class Orchestrator:
    """Wires together the multi-agent pipeline and serialization."""

    def __init__(self, output_dir: str = ".cartography"):
        self.output_dir = output_dir
        self.kg = KnowledgeGraph(output_dir=self.output_dir)
        self.surveyor = Surveyor(self.kg)
        self.hydrologist = Hydrologist(self.kg)

    def run_analysis(self, target_path: str):
        """Runs the full analysis pipeline: Surveyor → Hydrologist → Serialize."""
        target_path = os.path.abspath(target_path)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Target path does not exist: {target_path}")

        print(f"\n🗺️  The Brownfield Cartographer starting on: {target_path}\n")

        # Phase 1: Static Structure (Module Graph)
        print("▶️  Phase 1: Surveyor (Static Analysis)")
        self.surveyor.analyze_repository(target_path)
        self._print_module_summary()

        # Phase 2: Data Lineage (Lineage Graph)
        print("\n▶️  Phase 2: Hydrologist (Data Lineage)")
        self.hydrologist.analyze_repository(target_path)

        # Phase 3: Serialize to disk
        print("\n▶️  Phase 3: Archivist (Serialization)")
        self.kg.save_to_disk()

        print(f"\n✅ Analysis complete. Artifacts in: {self.output_dir}/\n")

    def _print_module_summary(self):
        """Prints a quick module graph summary after Surveyor finishes."""
        g = self.kg.module_graph
        n_nodes = g.number_of_nodes()
        n_edges = g.number_of_edges()
        dead = [n for n, d in g.nodes(data=True) if d.get("is_dead_code_candidate")]
        top_hubs = sorted(
            g.nodes(data=True),
            key=lambda x: x[1].get("pagerank", 0),
            reverse=True,
        )[:3]

        print(f"\n   📦 Module graph: {n_nodes} modules, {n_edges} import edges")
        if dead:
            print(f"   💀 Dead code candidates: {dead}")
        if top_hubs:
            hub_names = [os.path.basename(h[0]) for h in top_hubs]
            print(f"   🏆 Top hubs by PageRank : {hub_names}")
