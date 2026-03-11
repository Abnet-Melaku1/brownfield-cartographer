from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Node Types
# -----------------------------------------------------------------------------

class ModuleNode(BaseModel):
    """Represents a module (file) in the codebase."""
    path: str
    language: str
    purpose_statement: Optional[str] = None
    domain_cluster: Optional[str] = None
    complexity_score: Optional[int] = None
    change_velocity_30d: Optional[int] = None
    is_dead_code_candidate: bool = False
    last_modified: Optional[str] = None
    public_functions: List[str] = Field(default_factory=list)
    public_classes: List[str] = Field(default_factory=list)

class DatasetNode(BaseModel):
    """Represents a dataset, table, or stream."""
    name: str
    storage_type: Literal["table", "file", "stream", "api"]
    schema_snapshot: Optional[Dict] = None
    freshness_sla: Optional[str] = None
    owner: Optional[str] = None
    is_source_of_truth: bool = False

class FunctionNode(BaseModel):
    """Represents a function or class method in the codebase."""
    qualified_name: str
    parent_module: str
    signature: str
    purpose_statement: Optional[str] = None
    call_count_within_repo: int = 0
    is_public_api: bool = False

class TransformationNode(BaseModel):
    """Represents a data transformation operation."""
    source_datasets: List[str]
    target_datasets: List[str]
    transformation_type: str
    source_file: str
    line_range: str
    sql_query_if_applicable: Optional[str] = None

# -----------------------------------------------------------------------------
# Edge Types
# -----------------------------------------------------------------------------

class ImportsEdge(BaseModel):
    """source_module -> target_module"""
    source_module: str
    target_module: str
    weight: int = 1

class ProducesEdge(BaseModel):
    """transformation -> dataset"""
    transformation: str
    dataset: str

class ConsumesEdge(BaseModel):
    """dataset -> transformation"""
    dataset: str
    transformation: str

class CallsEdge(BaseModel):
    """function -> function"""
    source_function: str
    target_function: str

class ConfiguresEdge(BaseModel):
    """config_file -> module/pipeline"""
    config_file: str
    target: str
