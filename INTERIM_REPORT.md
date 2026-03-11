# The Brownfield Cartographer — Interim Submission Report
**TRP 1 Week 4 | Ten Academy Forward Deployment Engineering**
**Submission Deadline:** Thursday, March 12, 2026 — 03:00 UTC
**Target Codebase:** dbt-labs/jaffle_shop

---

## Table of Contents

1. [Reconnaissance: Manual Day-One Analysis](#1-reconnaissance-manual-day-one-analysis)
2. [Architecture Diagram: Four-Agent Pipeline](#2-architecture-diagram-four-agent-pipeline)
3. [Progress Summary: Component Status](#3-progress-summary-component-status)
4. [Early Accuracy Observations](#4-early-accuracy-observations)
5. [Completion Plan for Final Submission](#5-completion-plan-for-final-submission)

---

## 1. Reconnaissance: Manual Day-One Analysis

**Target Repository:** `dbt-labs/jaffle_shop`
**Exploration Time:** ~30 minutes
**Codebase Type:** Pure dbt project (SQL + YAML, no Python application logic)

### Codebase Inventory

| Category | Files |
|----------|-------|
| SQL Models | `models/customers.sql`, `models/orders.sql`, `models/staging/stg_customers.sql`, `models/staging/stg_orders.sql`, `models/staging/stg_payments.sql` |
| YAML Schemas | `models/schema.yml`, `models/staging/schema.yml`, `dbt_project.yml` |
| Seed Data | `seeds/raw_customers.csv`, `seeds/raw_orders.csv`, `seeds/raw_payments.csv` |

**Materialization strategy** (from `dbt_project.yml`):
- `models/staging/` → materialized as **views**
- `models/` (root) → materialized as **tables**

---

### The Five FDE Day-One Questions

#### Q1. What is the primary data ingestion path?

Data enters the system via **dbt seeds** — three CSV files loaded directly into the database:

| Seed | Schema |
|------|--------|
| `raw_customers.csv` | `id, first_name, last_name` |
| `raw_orders.csv` | `id, user_id, order_date, status` |
| `raw_payments.csv` | `id, order_id, payment_method, amount` |

These seeds act as the source of truth. There is no external ingestion pipeline, streaming source, or API connector. The staging layer reads directly from them via `{{ ref('raw_customers') }}` etc.

**Evidence:** `stg_customers.sql:7`, `stg_payments.sql:7` — both carry the comment: *"Normally we would select from the table here, but we are using seeds to load our data in this project."*

---

#### Q2. What are the 3–5 most critical output datasets?

There are exactly **2 mart-level output tables**:

| Output Table | Source File | Purpose |
|-------------|-------------|---------|
| `customers` | `models/customers.sql` | One row per customer: name, order history, customer lifetime value (CLV) |
| `orders` | `models/orders.sql` | One row per order: status, total amount, breakdown by all payment methods |

The three staging models (`stg_customers`, `stg_orders`, `stg_payments`) are intermediate **views** — not final outputs.

**Key business metric at risk:** `customer_lifetime_value` in the `customers` table — derived by summing all payment amounts per customer across a join of `stg_orders` and `stg_payments`.

---

#### Q3. What is the blast radius if the most critical module fails?

**Most critical model: `models/staging/stg_payments.sql`**

This file is the single most dangerous point of failure. It performs a unit conversion (`amount / 100` — stored in cents, exposed in dollars at line 19) and feeds both output tables:

```
raw_payments (seed)
  └── stg_payments (view)             [CRITICAL]
        ├── orders (table)            [BREAKS — payment pivot]
        └── customers (table)        [BREAKS — CLV = 0 or NULL]
```

A schema change to `raw_payments.csv` (e.g. renaming `amount` to `amount_cents`) would silently corrupt all monetary values downstream with no runtime error — it would produce incorrect numbers, not a crash. This is the highest-risk silent failure mode in the system.

---

#### Q4. Where is the business logic concentrated vs. distributed?

**Concentrated (high-complexity):**

- **`models/orders.sql`** — Contains the most complex transformation: a Jinja macro loop (`{% for payment_method in payment_methods %}`) that dynamically pivots payment methods into columns at query time. New payment methods are handled automatically via the variable defined at line 1. This is the only file with Jinja *logic* (not just `ref()`).
- **`models/customers.sql`** — Aggregates customer lifetime value using two CTEs (`customer_orders` and `customer_payments`) joined back to the customer base. All CLV business logic lives here.

**Distributed/thin:**

- Staging models (`stg_*.sql`) contain only column renaming and the unit conversion in `stg_payments`. No business rules.
- YAML schema files (`schema.yml`) form a **distributed data contract layer** — column-level tests (`unique`, `not_null`, `accepted_values`) spread across both staging and mart schemas.

---

#### Q5. What has changed most frequently in the last 90 days?

**No commits in the last 90 days.** The repository is officially deprecated — the README states it is no longer actively maintained.

**Most recent all-time commits:**

| Commit | Message |
|--------|---------|
| `fd7bfac` | README typo fix |
| `81ddf7b` | Added deprecation disclaimer |
| `b0b77aa` | Merge: update deprecated config field |
| `b1680f3` | Added `require-dbt-version`, reordered profile |
| `ec36ae1` | Updated deprecated path names |

**FDE implication:** This is a frozen reference codebase. There is no active development risk, but also no recent commit context to guide analysis. All understanding must be derived from static code inspection alone — which makes it an ideal test case for the Cartographer.

---

### What Was Hardest to Figure Out Manually

| Challenge | Difficulty | Why It Was Hard |
|-----------|-----------|----------------|
| Resolving `{{ ref('stg_customers') }}` to actual file paths | High | Standard grep yields nothing; requires mental dbt ref resolution |
| Understanding output schema of `orders.sql` Jinja loop | High | Must mentally evaluate `{% for %}` to know final column list |
| Distinguishing outputs (tables) from intermediates (views) | Medium | Requires reading `dbt_project.yml` materialization config |
| Identifying the `amount / 100` silent corruption risk | Medium | Only visible by reading `stg_payments.sql:19` carefully |
| Git velocity analysis | Low | Frozen repo — no recent commits to analyze |

**Key architectural finding from reconnaissance:** The single biggest gap between manual and automated analysis in dbt codebases is **Jinja template resolution**. A Cartographer that cannot strip or pre-process `{{ ref('x') }}` Jinja syntax will produce an empty lineage graph — which is precisely what occurred in our Phase 1 run (see Section 4).

---

## 2. Architecture Diagram: Four-Agent Pipeline

```
INPUT
  └── Local Repository Path (or GitHub URL — future)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                             │
│   src/orchestrator.py — wires agents in sequence               │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│   AGENT 1: THE SURVEYOR (Static Structure Analyst)             │
│   src/agents/surveyor.py                                        │
│                                                                 │
│   Inputs:  All .py, .sql, .yaml/.yml files in target repo      │
│   Tools:   TreeSitterAnalyzer (LanguageRouter: Python/SQL/YAML) │
│            git log — change velocity per file (30-day window)   │
│                                                                 │
│   Outputs → KnowledgeGraph.module_graph (NetworkX DiGraph)     │
│     - ModuleNode per file (path, language, complexity, velocity)│
│     - IMPORTS edges (Python import statements via tree-sitter)  │
│     - PageRank scores (architectural hub identification)        │
│     - Dead code candidates (nodes with in_degree = 0)          │
└──────┬──────────────────────────────────────────────────────────┘
       │ module_graph populated
       ▼
┌─────────────────────────────────────────────────────────────────┐
│   AGENT 2: THE HYDROLOGIST (Data Flow & Lineage Analyst)       │
│   src/agents/hydrologist.py                                     │
│                                                                 │
│   Inputs:  .sql files, .py files, schema.yml / sources.yml     │
│   Tools:                                                        │
│     SQLLineageAnalyzer (sqlglot) — SELECT/FROM/JOIN/CTE deps   │
│     TreeSitterAnalyzer — Python pandas/PySpark read/write calls │
│     DagConfigParser (PyYAML) — dbt schema.yml model extraction  │
│                                                                 │
│   Outputs → KnowledgeGraph.lineage_graph (NetworkX DiGraph)    │
│     - DatasetNode per table/file discovered                     │
│     - TransformationNode per SQL file / Python data call        │
│     - CONSUMES edges (dataset → transformation)                 │
│     - PRODUCES edges (transformation → dataset)                 │
│     - blast_radius(node): BFS downstream dependency traversal  │
└──────┬──────────────────────────────────────────────────────────┘
       │ lineage_graph populated
       ▼
┌─────────────────────────────────────────────────────────────────┐
│   AGENT 3: THE SEMANTICIST (LLM-Powered Purpose Analyst)       │
│   src/agents/semanticist.py  [PLANNED — Final Submission]      │
│                                                                 │
│   Inputs:  module_graph + lineage_graph + raw file content     │
│   Tools:   LLM API (cheap model for bulk, strong for synthesis) │
│            Vector embeddings — k-means domain clustering        │
│                                                                 │
│   Outputs:                                                      │
│     - Purpose Statement per module (code-grounded, not docstr) │
│     - Documentation Drift flags (docstring vs. implementation) │
│     - Domain Architecture Map (inferred cluster labels)        │
│     - Five FDE Day-One Answers with file:line citations        │
└──────┬──────────────────────────────────────────────────────────┘
       │ semantic layer added to KnowledgeGraph
       ▼
┌─────────────────────────────────────────────────────────────────┐
│   AGENT 4: THE ARCHIVIST (Living Context Maintainer)           │
│   src/agents/archivist.py  [PLANNED — Final Submission]        │
│                                                                 │
│   Inputs:  Fully populated KnowledgeGraph                      │
│                                                                 │
│   Outputs:                                                      │
│     - .cartography/CODEBASE.md (living context for AI agents)  │
│     - .cartography/onboarding_brief.md (FDE Day-One Brief)     │
│     - .cartography/lineage_graph.json (serialized DAG)         │
│     - .cartography/module_graph.json (serialized structure)    │
│     - .cartography/cartography_trace.jsonl (audit log)         │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│   NAVIGATOR AGENT (Query Interface)                            │
│   src/agents/navigator.py  [PLANNED — Final Submission]        │
│                                                                 │
│   LangGraph agent with 4 tools:                                │
│     find_implementation(concept)  — semantic vector search     │
│     trace_lineage(dataset, dir)   — graph traversal            │
│     blast_radius(module_path)     — downstream BFS             │
│     explain_module(path)          — LLM generative answer      │
└─────────────────────────────────────────────────────────────────┘

KNOWLEDGE GRAPH (Central Data Store)
  src/graph/knowledge_graph.py
  ├── module_graph   (NetworkX DiGraph)  → .cartography/module_graph.json
  └── lineage_graph  (NetworkX DiGraph)  → .cartography/lineage_graph.json

DATA MODELS (Pydantic schemas)
  src/models/schema.py
  ├── Nodes:  ModuleNode, DatasetNode, FunctionNode, TransformationNode
  └── Edges:  ImportsEdge, ProducesEdge, ConsumesEdge, CallsEdge, ConfiguresEdge
```

---

### Data Flow Summary

```
CLI (src/cli.py)
  └─► Orchestrator
        ├─► Surveyor ──────────────────► module_graph
        │     ├── TreeSitterAnalyzer       (IMPORTS edges)
        │     └── git log                  (velocity scores)
        │
        ├─► Hydrologist ───────────────► lineage_graph
        │     ├── SQLLineageAnalyzer        (CONSUMES/PRODUCES edges)
        │     ├── TreeSitterAnalyzer        (Python data calls)
        │     └── DagConfigParser          (YAML dataset nodes)
        │
        └─► KnowledgeGraph.save_to_disk()
              ├── .cartography/module_graph.json
              └── .cartography/lineage_graph.json
```

---

## 3. Progress Summary: Component Status

### Implemented and Working

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| CLI entry point | `src/cli.py` | Complete | `analyze` subcommand with `--output` flag |
| Orchestrator | `src/orchestrator.py` | Complete | Sequences Surveyor → Hydrologist → serialization |
| Pydantic schemas | `src/models/schema.py` | Complete | All 4 node types, all 5 edge types defined |
| LanguageRouter | `src/analyzers/tree_sitter_analyzer.py` | Complete | Routes `.py`, `.sql`, `.yml`, `.yaml` to correct grammar |
| TreeSitterAnalyzer | `src/analyzers/tree_sitter_analyzer.py` | Complete | `parse_file()` + `execute_query()` S-expression interface |
| SQLLineageAnalyzer | `src/analyzers/sql_lineage.py` | Complete | sqlglot-based SELECT/FROM/JOIN/CTE extraction with CTE filter |
| DagConfigParser | `src/analyzers/dag_config_parser.py` | Complete | dbt `schema.yml` model + source extraction |
| KnowledgeGraph | `src/graph/knowledge_graph.py` | Complete | Dual NetworkX DiGraph, PageRank, dead code detection, JSON serialization |
| Surveyor Agent | `src/agents/surveyor.py` | Complete | Module graph, git velocity (30d), Python import edges, PageRank |
| Hydrologist Agent | `src/agents/hydrologist.py` | Complete | SQL lineage, Python data flow (stub), YAML dataset nodes |
| Dependency management | `pyproject.toml` + `uv.lock` | Complete | All deps locked with uv |
| README | `README.md` | Complete | Install and `analyze` command documented |
| Cartography artifacts | `.cartography/` | Complete | `module_graph.json` + `lineage_graph.json` generated on jaffle_shop |
| RECONNAISSANCE.md | `RECONNAISSANCE.md` | Complete | Manual Day-One analysis of jaffle_shop |

### In Progress / Planned for Final Submission

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Semanticist Agent | `src/agents/semanticist.py` | Not started | LLM purpose statements, doc drift, domain clustering, Day-One Q&A |
| Archivist Agent | `src/agents/archivist.py` | Not started | CODEBASE.md, onboarding_brief.md, cartography_trace.jsonl |
| Navigator Agent | `src/agents/navigator.py` | Not started | LangGraph agent with 4 query tools |
| `query` CLI subcommand | `src/cli.py` | Partial | `analyze` done; `query` (interactive Navigator) not yet wired |
| dbt Jinja pre-processor | `src/analyzers/` | Not started | Required to resolve `{{ ref() }}` before sqlglot parsing |
| Incremental update mode | `src/orchestrator.py` | Not started | Re-analyze only git-changed files |
| Second target codebase | — | Not started | Apache Airflow examples (final requirement) |

---

## 4. Early Accuracy Observations

### Module Graph — jaffle_shop

**Result:** `module_graph.json` — 8 nodes (files), import edges captured where applicable.

| Observation | Assessment |
|-------------|-----------|
| All 8 `.py`, `.sql`, `.yml` files correctly discovered and registered as `ModuleNode` objects | Correct |
| Complexity score (lines of code) computed per file | Correct — basic heuristic |
| Git velocity shows 0 for all files | Expected — frozen repo, no commits in 30 days |
| Python import edges extracted via tree-sitter | Correct — jaffle_shop has no Python files, so no edges expected |
| PageRank applied — all nodes equal rank | Expected — no edges in a pure SQL/YAML repo |
| Dead code candidates flagged — all nodes flagged (in_degree=0) | Partially correct — true for this repo (no Python imports), but would be misleading in a mixed codebase |

**Accuracy verdict:** High for this target. The module graph correctly maps the structural skeleton of jaffle_shop.

---

### Lineage Graph — jaffle_shop

**Result:** `lineage_graph.json` — 5 dataset nodes, **0 edges**.

| Observation | Assessment |
|-------------|-----------|
| 5 dataset nodes extracted: `customers`, `orders`, `stg_customers`, `stg_orders`, `stg_payments` | Correct — sourced from `schema.yml` via DagConfigParser |
| All SQL lineage edges missing (0 CONSUMES / 0 PRODUCES edges) | **Root cause identified — see below** |
| `raw_customers`, `raw_orders`, `raw_payments` (seed tables) absent from lineage graph | Gap — seeds not yet parsed as source nodes |

**Root cause of missing edges:**

All 5 SQL model files in jaffle_shop use dbt's Jinja templating syntax:
```sql
select * from {{ ref('stg_customers') }}
```
`sqlglot` operates on raw SQL and cannot parse Jinja expressions. When it encounters `{{`, it throws:
```
Expected table name but got <Token token_type: TokenType.L_BRACE ...>
```
The parser gracefully catches and logs the error, but produces no lineage edges.

**This is the #1 accuracy gap.** The fix requires a **Jinja pre-processing step** before handing SQL to sqlglot — replacing `{{ ref('model_name') }}` with the bare table name `model_name`.

**Expected lineage graph after Jinja pre-processing:**
```
raw_customers ──► stg_customers ──► customers
raw_orders    ──► stg_orders    ──► orders
                                ──► customers
raw_payments  ──► stg_payments  ──► orders
                                ──► customers
```
This matches dbt's own built-in lineage visualization exactly.

---

### Does the Module Graph "Look Right"?

Comparing the generated `module_graph.json` against manual inspection:

| Expected Node | Present in Graph | Correct Language Tag |
|---------------|-----------------|----------------------|
| `models/customers.sql` | Yes | `sql` |
| `models/orders.sql` | Yes | `sql` |
| `models/staging/stg_customers.sql` | Yes | `sql` |
| `models/staging/stg_orders.sql` | Yes | `sql` |
| `models/staging/stg_payments.sql` | Yes | `sql` |
| `models/schema.yml` | Yes | `yaml` |
| `models/staging/schema.yml` | Yes | `yaml` |
| `dbt_project.yml` | Yes | `yaml` |

**All files correctly discovered. Zero false positives. Zero false negatives.**

---

## 5. Completion Plan for Final Submission

**Final Deadline:** Sunday, March 15, 2026 — 03:00 UTC

### Priority 1 — Fix Lineage Accuracy (Jinja Pre-Processor)

The highest-value remaining work is making the lineage graph accurate for dbt codebases.

**Task:** Add a `JinjaPreProcessor` step in `src/analyzers/` that:
1. Detects dbt Jinja syntax (`{{ ref('x') }}`, `{{ source('schema', 'table') }}`)
2. Replaces `{{ ref('model') }}` with the bare identifier `model`
3. Strips Jinja block tags (`{% set ... %}`, `{% for ... %}`, `{# ... #}`) before passing to sqlglot
4. Passes the cleaned SQL to `SQLLineageAnalyzer`

This single fix will transform the lineage graph from 0 edges to a complete, accurate DAG.

---

### Priority 2 — Semanticist Agent

**File:** `src/agents/semanticist.py`

Implementation tasks:
- `ContextWindowBudget` — token estimation and cumulative cost tracking
- `generate_purpose_statement(module)` — LLM prompt against raw code (not docstring), 2–3 sentence output
- Documentation drift detection — compare docstring vs. LLM-inferred purpose, flag mismatches
- `cluster_into_domains()` — embed all purpose statements, k-means clustering (k=5–8), infer domain labels
- `answer_day_one_questions()` — synthesis prompt over full Surveyor + Hydrologist output with file:line citations

**Model strategy:** Use a cheap/fast model (e.g. Gemini Flash or claude-haiku) for bulk module summaries; reserve claude-sonnet for the Day-One synthesis prompt.

---

### Priority 3 — Archivist Agent

**File:** `src/agents/archivist.py`

Implementation tasks:
- `generate_CODEBASE_md()` — structured living context: Architecture Overview, Critical Path (top 5 by PageRank), Data Sources & Sinks, Known Debt, High-Velocity Files
- `generate_onboarding_brief()` — the five FDE Day-One answers as a structured markdown document with evidence citations
- `cartography_trace.jsonl` — audit log: agent name, action, evidence source, confidence level, timestamp

---

### Priority 4 — Navigator Agent (Query Interface)

**File:** `src/agents/navigator.py`

Implementation tasks:
- LangGraph agent with 4 tools: `find_implementation`, `trace_lineage`, `blast_radius`, `explain_module`
- Every answer must cite evidence: source file, line range, analysis method (static vs. LLM)
- Wire `query` subcommand into `src/cli.py`

---

### Priority 5 — Second Target Codebase

**Target:** Apache Airflow example DAGs (`apache/airflow` — `examples/` directory)

Required artifacts for each target:
- `.cartography/CODEBASE.md`
- `.cartography/onboarding_brief.md`
- `.cartography/module_graph.json`
- `.cartography/lineage_graph.json`
- `.cartography/cartography_trace.jsonl`

---

### Priority 6 — Incremental Update Mode

**File:** `src/orchestrator.py`

Add `run_incremental(target_path)`:
1. Read last-run timestamp from `.cartography/last_run`
2. `git diff --name-only HEAD@{last_run}..HEAD` to get changed files
3. Re-analyze only changed files, merge results into existing KnowledgeGraph
4. Re-run PageRank on updated graph

---

### Delivery Timeline

| Day | Target |
|-----|--------|
| Thu Mar 12 | Interim submission (current state) |
| Fri Mar 13 | Jinja pre-processor + accurate lineage graph; Semanticist agent skeleton |
| Sat Mar 14 | Archivist agent + CODEBASE.md/onboarding_brief; Navigator agent + query CLI |
| Sun Mar 15 03:00 UTC | Final submission: all agents complete, 2 target codebases, video demo |

---

## Appendix: Known Limitations

| Limitation | Impact | Mitigation Plan |
|-----------|--------|----------------|
| Jinja templates break sqlglot parsing | High — lineage graph empty for dbt codebases | Jinja pre-processor (Priority 1) |
| Python data flow analysis is a stub | Medium — pandas/PySpark lineage not captured | Full tree-sitter query implementation for Final |
| Module dead code detection uses in_degree=0 heuristic | Medium — false positives for entry points | Cross-reference with git velocity to de-flag high-activity files |
| No GitHub URL ingestion (local paths only) | Low for interim | Add `gitpython` clone step for Final submission |
| Single target codebase analyzed | Acceptable for interim | Second target (Airflow) for Final |
