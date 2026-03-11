# The Brownfield Cartographer

Engineering Codebase Intelligence Systems for Rapid FDE Onboarding in Production Environments.

## Overview

The Brownfield Cartographer is a multi-agent system designed to ingest complex, mixed-language repositories (Python, SQL, YAML) and produce a queryable knowledge graph of the system's architecture and data lineage.

## Installation

This project uses `uv` for dependency management.

```bash
# Initialize sync
uv sync
```

## Usage

Run the analysis pipeline against a local repository:

```bash
python -m src.cli analyze <path/to/repository>
```

**Example:**

```bash
python -m src.cli analyze ../jaffle_shop
```

This command will output two artifacts in the `.cartography/` folder:

1. `module_graph.json` - Static structure from Python imports
2. `lineage_graph.json` - Data dependency DAG from SQL and YAML

## Agents

- **Surveyor:** Analyzes static structure (Python ASTs via `tree-sitter`) and Git history velocity.
- **Hydrologist:** Extracts table-level lineage from SQL queries (via `sqlglot`) and YAML Dags (dbt).
