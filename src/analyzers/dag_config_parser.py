import yaml
from typing import Dict, List, Any

class DagConfigParser:
    """Parses DAG configuration files (Airflow YAMLs or dbt schema.yml) for topology."""

    def parse_dbt_schema(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parses a dbt schema.yml file to extract dataset documentation and test dependencies.
        Returns a list of dataset metadata configs.
        """
        datasets = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                
            if not config:
                return datasets
                
            # Parse models (targets)
            if "models" in config:
                for model in config.get("models", []):
                    datasets.append({
                        "name": model.get("name"),
                        "type": "model",
                        "description": model.get("description", ""),
                        "meta": model.get("meta", {})
                    })
            
            # Parse sources
            if "sources" in config:
                for source in config.get("sources", []):
                    source_name = source.get("name")
                    for table in source.get("tables", []):
                        datasets.append({
                            "name": f"{source_name}.{table.get('name')}",
                            "type": "source",
                            "description": table.get("description", ""),
                            "freshness": table.get("freshness", {})
                        })
                        
        except Exception as e:
            print(f"⚠️ Failed to parse dbt schema {file_path}: {e}")
            
        return datasets
