import os
import csv
import yaml
from typing import Dict, List, Any


class DagConfigParser:
    """Parses DAG configuration files (Airflow YAMLs, dbt schema.yml, dbt seeds) for topology."""

    # -------------------------------------------------------------------------
    # dbt schema.yml / sources.yml
    # -------------------------------------------------------------------------

    def parse_dbt_schema(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parses a dbt schema.yml or sources.yml file.
        Returns a list of dataset metadata dicts with keys: name, type, description.
        """
        datasets = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config:
                return datasets

            # dbt models (transformed outputs)
            for model in config.get("models", []):
                datasets.append({
                    "name": model.get("name"),
                    "type": "model",
                    "description": model.get("description", ""),
                    "meta": model.get("meta", {}),
                })

            # dbt sources (raw external tables)
            for source in config.get("sources", []):
                source_name = source.get("name", "")
                for table in source.get("tables", []):
                    datasets.append({
                        "name": f"{source_name}__{table.get('name')}",
                        "type": "source",
                        "description": table.get("description", ""),
                        "freshness": table.get("freshness", {}),
                    })

        except Exception as e:
            print(f"⚠️  Failed to parse dbt schema {file_path}: {e}")

        return datasets

    # -------------------------------------------------------------------------
    # dbt project.yml
    # -------------------------------------------------------------------------

    def parse_dbt_project(self, file_path: str) -> Dict[str, Any]:
        """
        Parses dbt_project.yml to extract materialization strategy and seed paths.
        Returns a dict with keys: project_name, model_paths, seed_paths, materializations.
        """
        result: Dict[str, Any] = {
            "project_name": "",
            "model_paths": [],
            "seed_paths": [],
            "materializations": {},
        }
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config:
                return result

            result["project_name"] = config.get("name", "")
            result["model_paths"] = config.get("model-paths", config.get("source-paths", ["models"]))
            result["seed_paths"] = config.get("seed-paths", ["seeds"])

            # Flatten materialization config per directory
            for model_key, model_cfg in config.get("models", {}).items():
                if isinstance(model_cfg, dict) and "+materialized" in model_cfg:
                    result["materializations"][model_key] = model_cfg["+materialized"]

        except Exception as e:
            print(f"⚠️  Failed to parse dbt_project.yml {file_path}: {e}")

        return result

    # -------------------------------------------------------------------------
    # dbt Seeds (CSV files → raw source datasets)
    # -------------------------------------------------------------------------

    def parse_seed_files(self, seeds_dir: str) -> List[Dict[str, Any]]:
        """
        Scans a dbt seeds/ directory for CSV files and registers each as a raw
        source dataset. Returns a list of seed metadata dicts.
        """
        seeds = []
        if not os.path.isdir(seeds_dir):
            return seeds

        for file in os.listdir(seeds_dir):
            if not file.endswith(".csv"):
                continue

            table_name = file.replace(".csv", "")
            seed_path = os.path.join(seeds_dir, file)
            columns = []

            try:
                with open(seed_path, "r", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    header = next(reader, [])
                    columns = header
            except Exception:
                pass

            seeds.append({
                "name": table_name,
                "type": "seed",
                "file": seed_path,
                "columns": columns,
            })

        return seeds
