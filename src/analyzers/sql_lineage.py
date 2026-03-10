import sqlglot
from sqlglot.expressions import Table, Create, Insert
from typing import List, Dict

class SQLLineageAnalyzer:
    """Uses sqlglot to extract table dependencies from SQL files and dbt models."""

    def __init__(self, default_dialect: str = "postgres"):
        self.default_dialect = default_dialect

    def extract_lineage(self, sql_code: str, dialect: str = None) -> Dict[str, List[str]]:
        """
        Parses SQL and extracts source tables (consumed) and target tables (produced).
        Returns a dict: {"sources": [...], "targets": [...]}
        """
        active_dialect = dialect or self.default_dialect
        
        sources = set()
        targets = set()
        
        try:
            # Parse the SQL statement(s)
            parsed = sqlglot.parse(sql_code, read=active_dialect)
            
            for statement in parsed:
                if not statement:
                    continue
                    
                # Find all tables read from (SELECT, FROM, JOIN)
                # We filter out CTEs (Common Table Expressions) so we only get base tables
                for table in statement.find_all(Table):
                    table_name = table.name
                    # Ignore temporary CTE names if they exist in the WITH clause
                    if not self._is_cte(table, statement) and table_name:
                        sources.add(table_name)
                        
                # Find tables written to (CREATE TABLE, INSERT INTO)
                if isinstance(statement, Create):
                    if hasattr(statement, "this") and isinstance(statement.this, Table):
                        targets.add(statement.this.name)
                        
                elif isinstance(statement, Insert):
                    if hasattr(statement, "this") and isinstance(statement.this, Table):
                        targets.add(statement.this.name)

        except Exception as e:
            print(f"⚠️ Failed to parse SQL lineage: {e}")
            
        return {
            "sources": list(sources),
            "targets": list(targets)
        }
        
    def _is_cte(self, table: Table, statement: sqlglot.Expression) -> bool:
        """Helper to determine if a table name is actually just a CTE reference."""
        if not hasattr(statement, "args") or "with" not in statement.args:
            return False
            
        with_clause = statement.args.get("with")
        if not with_clause:
            return False
            
        for cte in with_clause.expressions:
            if cte.alias == table.name:
                return True
                
        return False
