# RECONNAISSANCE.md
## Manual Day-One Analysis: jaffle_shop (dbt-labs/jaffle_shop)

**Analyst:** Manual exploration, ~30 minutes
**Date:** 2026-03-11
**Target:** https://github.com/dbt-labs/jaffle_shop
**Type:** dbt project — SQL + YAML, no Python application code

---

## Codebase Overview

`jaffle_shop` is the canonical dbt example project by dbt Labs. It models a fictional e-commerce store ("Jaffle Shop") and demonstrates dbt's core patterns: raw seed data, staging models, and mart-level transformations.

**File inventory:**
- 5 SQL model files (`.sql`)
- 3 YAML schema/config files (`.yml`)
- 1 `dbt_project.yml` (project config)
- 3 CSV seed files (raw source data)
- 1 ERD diagram (`etc/jaffle_shop_erd.png`)

**Materialization strategy (from `dbt_project.yml`):**
- Staging models → `view`
- Mart models (root `models/`) → `table`

---

## The Five FDE Day-One Questions

### Q1. What is the primary data ingestion path?

Data enters the system via **dbt seeds** — three CSV files loaded directly into the database:

| Seed File | Columns |
|-----------|---------|
| `seeds/raw_customers.csv` | `id, first_name, last_name` |
| `seeds/raw_orders.csv` | `id, user_id, order_date, status` |
| `seeds/raw_payments.csv` | `id, order_id, payment_method, amount` |

These seed tables (`raw_customers`, `raw_orders`, `raw_payments`) act as the source of truth. There is no external ingestion pipeline, API connector, or streaming source in this repo — ingestion is entirely seed-based.

**Evidence:** `stg_customers.sql:7` — `select * from {{ ref('raw_customers') }}`; `stg_payments.sql:7` — note the comment: *"Normally we would select from the table here, but we are using seeds."*

---

### Q2. What are the 3-5 most critical output datasets/endpoints?

There are exactly **2 mart-level output tables** (materialized as `table`):

| Model | File | Purpose |
|-------|------|---------|
| `customers` | `models/customers.sql` | One row per customer with lifetime order stats and CLV |
| `orders` | `models/orders.sql` | One row per order with payment breakdown by method |

These are the final outputs consumed downstream (BI tools, analysts). The staging models (`stg_*`) are intermediate views, not outputs.

**Key columns in `customers`:** `customer_id`, `first_name`, `last_name`, `first_order`, `most_recent_order`, `number_of_orders`, `customer_lifetime_value`

**Key columns in `orders`:** `order_id`, `customer_id`, `order_date`, `status`, `credit_card_amount`, `coupon_amount`, `bank_transfer_amount`, `gift_card_amount`, `amount`

---

### Q3. What is the blast radius if the most critical module fails?

**Most critical model: `stg_payments`** (`models/staging/stg_payments.sql`)

If `stg_payments` fails or its schema changes:
- `orders.sql` breaks — it reads `stg_payments` directly and pivots payment methods using a Jinja `{% for %}` loop
- `customers.sql` breaks — it reads `stg_orders` which joins payments; customer lifetime value (`total_amount`) becomes NULL or wrong

Full blast radius:
```
raw_payments (seed)
  └── stg_payments (view)
        ├── orders (table)         [BREAKS]
        └── customers (table)     [BREAKS — CLV calculation]
```

Changing the `amount` column (currently stored in cents, divided by 100 in `stg_payments.sql:19`) would silently corrupt all monetary values in both output tables.

---

### Q4. Where is the business logic concentrated vs. distributed?

**Concentrated in two files:**

- **`models/orders.sql`** — Contains the most complex logic: a Jinja macro loop that dynamically pivots payment methods into columns (`credit_card_amount`, `coupon_amount`, etc.). This is the only file using Jinja templating for logic (not just refs). Any new payment method requires updating the seed data — the code handles it automatically via the `payment_methods` list variable at line 1.

- **`models/customers.sql`** — Aggregates customer-level facts via CTEs: `customer_orders` (order counts and dates) and `customer_payments` (total spend). The CLV calculation lives entirely here.

**Distributed/thin:**
- Staging models (`stg_*.sql`) contain only renaming and light type casting (e.g., `amount / 100`). No business rules.
- YAML schema files contain data contracts (column tests: `unique`, `not_null`, `accepted_values`) — a distributed quality layer.

---

### Q5. What has changed most frequently in the last 90 days (git velocity)?

**No commits in the last 90 days.** The repository is officially deprecated — the README states it is no longer maintained.

**Most recent commits (all-time):**
1. `fd7bfac` — README typo fix
2. `81ddf7b` — Added deprecation disclaimer
3. `b0b77aa` / `b1680f3` — dbt version config compliance updates
4. `ec36ae1` — Deprecated path names updated

**Implication for FDE:** This is a stable, frozen reference codebase. There is no active development risk, but also no recent context from commit messages. All understanding must come from the code itself.

---

## What Was Hardest to Figure Out Manually

1. **The Jinja `{{ ref() }}` syntax obscures lineage.** Reading `customers.sql`, you see `ref('stg_customers')` — you must mentally resolve this to `models/staging/stg_customers.sql`. A static grep for table names yields nothing. This is the #1 manual challenge in any dbt codebase.

2. **The `orders.sql` Jinja loop** (`{% for payment_method in payment_methods %}`) makes the schema of the `orders` output non-obvious from reading the SQL. You must mentally evaluate the loop to understand the output columns.

3. **No Python code exists** — this is pure SQL + YAML. Any FDE expecting Python application logic will be disoriented. The "application" is entirely declarative SQL transformations.

4. **Seed data as ingestion** is non-obvious. In production dbt projects, sources are external tables. The seed pattern here is tutorial-specific and would not appear in a real client engagement.

---

## Difficulty Analysis (for Cartographer Architecture Priorities)

| Challenge | Difficulty | Cartographer Priority |
|-----------|-----------|----------------------|
| Resolving `{{ ref() }}` to actual file paths | High | Must handle dbt Jinja pre-processing |
| Understanding Jinja loop output schema | High | LLM synthesis (Semanticist agent) |
| Identifying final output tables vs. staging views | Medium | Use `dbt_project.yml` materialization config |
| Reading blast radius from model dependencies | Medium | Hydrologist graph traversal |
| Finding business logic concentration | Low-Medium | PageRank on lineage graph |
| Git velocity analysis | Low (frozen repo) | Works for active repos |

**Key insight:** The single biggest gap between manual analysis and automated analysis for dbt codebases is **Jinja template resolution**. A Cartographer that cannot strip or pre-process `{{ ref('x') }}` into actual table names will produce an empty lineage graph — which is exactly what happened in our Phase 1 run.
