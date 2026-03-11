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
        """Runs the full interim pipeline."""
        target_path = os.path.abspath(target_path)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Target path does not exist: {target_path}")
            
        print(f"\n🗺️  The Brownfield Cartographer starting on: {target_path}\n")
        
        # 1. Static Structure (Module Graph)
        print("▶️ Phase 1: Surveyor (Static Analysis)")
        self.surveyor.analyze_repository(target_path)
        
        # 2. Data Lineage (Dataset Graph)
        print("\n▶️ Phase 2: Hydrologist (Data Lineage)")
        self.hydrologist.analyze_repository(target_path)
        
        # 3. Serialization
        print("\n▶️ Phase 3: Archive (Serialization)")
        self.kg.save_to_disk()
        
        print(f"\n✅ Analysis complete. Artifacts saved to {self.output_dir}/\n")
