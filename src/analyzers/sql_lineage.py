import re
import sqlglot
from sqlglot.expressions import Table, Create, Insert
from typing import List, Dict


class JinjaPreProcessor:
    """
    Strips dbt/Jinja2 templating syntax so sqlglot can parse the raw SQL.

    Handles the most common dbt patterns:
      {{ ref('model') }}            → model
      {{ source('schema', 'tbl') }} → schema__tbl
      {% set var = [...] %}         → removed
      {% for x in list %}           → removed (loop body kept)
      {% if / elif / else / endif %} → removed
      {# comment #}                 → removed
      {{ any_other_expr }}          → placeholder
    """

    @staticmethod
    def clean(sql: str) -> str:
        # {{ ref('model_name') }} → model_name
        sql = re.sub(
            r"\{\{\s*ref\(['\"](\w+)['\"]\)\s*\}\}",
            r"\1",
            sql
        )
        # {{ source('schema', 'table') }} → schema__table
        sql = re.sub(
            r"\{\{\s*source\(['\"](\w+)['\"],\s*['\"](\w+)['\"]\)\s*\}\}",
            r"\1__\2",
            sql
        )
        # {% set var = ... %} — may span multiple lines
        sql = re.sub(r"\{%-?\s*set\b.*?-?%\}", "", sql, flags=re.DOTALL)
        # {% for ... %} / {% endfor %}
        sql = re.sub(r"\{%-?\s*for\b[^%]*-?%\}", "", sql)
        sql = re.sub(r"\{%-?\s*endfor\s*-?%\}", "", sql)
        # {% if %} / {% elif %} / {% else %} / {% endif %}
        sql = re.sub(r"\{%-?\s*(if|elif|else|endif)\b[^%]*-?%\}", "", sql)
        # {# Jinja comments #}
        sql = re.sub(r"\{#.*?#\}", "", sql, flags=re.DOTALL)
        # Any remaining {{ expr }} expressions
        sql = re.sub(r"\{\{[^}]*\}\}", "placeholder", sql)
        return sql


class SQLLineageAnalyzer:
    """
    Uses sqlglot to extract table dependencies from SQL files and dbt models.
    Automatically strips Jinja templating via JinjaPreProcessor before parsing.
    """

    SUPPORTED_DIALECTS = {"postgres", "bigquery", "snowflake", "duckdb", "spark", "hive"}

    def __init__(self, default_dialect: str = "postgres"):
        self.default_dialect = default_dialect
        self.preprocessor = JinjaPreProcessor()

    def extract_lineage(self, sql_code: str, dialect: str = None) -> Dict[str, List[str]]:
        """
        Parses SQL and extracts source tables (consumed) and target tables (produced).
        Automatically pre-processes Jinja templating before parsing.
        Returns: {"sources": [...], "targets": [...]}
        """
        active_dialect = dialect if dialect in self.SUPPORTED_DIALECTS else self.default_dialect

        # Strip Jinja before handing to sqlglot
        cleaned_sql = self.preprocessor.clean(sql_code)

        sources = set()
        targets = set()

        try:
            parsed = sqlglot.parse(cleaned_sql, read=active_dialect, error_level=sqlglot.ErrorLevel.WARN)

            for statement in parsed:
                if not statement:
                    continue

                # Collect CTE names so we can exclude them from sources
                cte_names = self._collect_cte_names(statement)

                # Tables read from (SELECT … FROM, JOINs)
                for table in statement.find_all(Table):
                    table_name = table.name
                    if table_name and table_name not in cte_names:
                        sources.add(table_name)

                # Tables written to (CREATE TABLE … AS SELECT, INSERT INTO)
                if isinstance(statement, Create):
                    if hasattr(statement, "this") and isinstance(statement.this, Table):
                        targets.add(statement.this.name)

                elif isinstance(statement, Insert):
                    if hasattr(statement, "this") and isinstance(statement.this, Table):
                        targets.add(statement.this.name)

        except Exception as e:
            print(f"⚠️  Failed to parse SQL lineage: {e}")

        # Remove any target names that crept into sources (e.g. self-referential CTEs)
        sources -= targets

        return {
            "sources": list(sources),
            "targets": list(targets),
        }

    def _collect_cte_names(self, statement: sqlglot.Expression) -> set:
        """Returns the set of CTE alias names defined in a WITH clause."""
        cte_names = set()
        if not hasattr(statement, "args") or "with" not in statement.args:
            return cte_names
        with_clause = statement.args.get("with")
        if not with_clause:
            return cte_names
        for cte in with_clause.expressions:
            if cte.alias:
                cte_names.add(cte.alias)
        return cte_names
