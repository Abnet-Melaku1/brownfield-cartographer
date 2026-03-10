import tree_sitter_python as tspython
import tree_sitter_sql as tssql
import tree_sitter_yaml as tsyaml
from tree_sitter import Language, Parser

class LanguageRouter:
    """Routes files to the appropriate tree-sitter parser based on extension."""

    def __init__(self):
        self.LANGUAGES = {
            ".py": Language(tspython.language()),
            ".sql": Language(tssql.language()),
            ".yml": Language(tsyaml.language()),
            ".yaml": Language(tsyaml.language())
        }
        
    def get_parser(self, file_path: str) -> Parser | None:
        """Returns a configured tree-sitter Parser for the given file extension, or None if unsupported."""
        ext = self._get_extension(file_path)
        lang = self.LANGUAGES.get(ext)
        if lang:
            parser = Parser()
            parser.set_language(lang)
            return parser
        return None
        
    def get_language(self, file_path: str) -> Language | None:
        """Returns the tree-sitter Language object for the given file extension."""
        ext = self._get_extension(file_path)
        return self.LANGUAGES.get(ext)
        
    def _get_extension(self, file_path: str) -> str:
        return "." + file_path.split('.')[-1].lower() if '.' in file_path else ""


class TreeSitterAnalyzer:
    """Language-agnostic AST parsing using tree-sitter."""

    def __init__(self):
        self.router = LanguageRouter()

    def parse_file(self, file_path: str):
        """Parses a file and returns the AST root node and source code."""
        parser = self.router.get_parser(file_path)
        if not parser:
            return None, None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
                
            tree = parser.parse(bytes(source_code, "utf8"))
            return tree.root_node, source_code
        except Exception as e:
            print(f"⚠️ Failed to parse {file_path}: {e}")
            return None, None

    def execute_query(self, file_path: str, query_string: str):
        """Executes an S-expression query against the AST of a file."""
        root_node, source_code = self.parse_file(file_path)
        if not root_node:
            return []
            
        lang = self.router.get_language(file_path)
        query = lang.query(query_string)
        captures = query.captures(root_node)
        
        results = []
        for node, capture_name in captures:
            text = source_code[node.start_byte:node.end_byte]
            results.append({
                "capture_name": capture_name,
                "text": text,
                "node_type": node.type,
                "line": node.start_point[0] + 1
            })
            
        return results
