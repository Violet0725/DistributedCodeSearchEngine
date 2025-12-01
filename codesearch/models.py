"""
Data models for CodeSearch engine.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid


class Language(str, Enum):
    """Supported programming languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    UNKNOWN = "unknown"


class CodeEntityType(str, Enum):
    """Types of code entities we index."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    MODULE = "module"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"


class CodeEntity(BaseModel):
    """Represents a parsed code entity (function, class, etc.)."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    entity_type: CodeEntityType
    language: Language
    
    # Location info
    file_path: str
    repo_name: str
    start_line: int
    end_line: int
    
    # Code content
    source_code: str
    docstring: Optional[str] = None
    signature: Optional[str] = None
    
    # Semantic info
    parameters: List[str] = Field(default_factory=list)
    return_type: Optional[str] = None
    decorators: List[str] = Field(default_factory=list)
    parent_class: Optional[str] = None
    
    # Metadata
    complexity: Optional[int] = None  # Cyclomatic complexity
    loc: int = 0  # Lines of code
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_searchable_text(self) -> str:
        """Generate text representation for embedding/search."""
        parts = []
        
        # Start with function/class name
        parts.append(self.name)
        
        # Add entity type context
        if self.entity_type.value in ['function', 'method']:
            parts.append("function")
        elif self.entity_type.value == 'class':
            parts.append("class")
        
        # Add signature with full context
        if self.signature:
            parts.append(self.signature)
        
        # Include parameter names for context
        if self.parameters:
            parts.append("parameters: " + " ".join(self.parameters))
        
        # Docstring is most important for semantic understanding
        if self.docstring:
            # Clean up docstring - remove markdown/rst formatting
            doc = self.docstring
            # Remove common docstring markers
            doc = doc.replace('"""', '').replace("'''", '').strip()
            parts.append(doc)
        
        # Add return type if available
        if self.return_type:
            parts.append(f"returns {self.return_type}")
        
        # Add parent class context for methods
        if self.parent_class:
            parts.append(f"method of {self.parent_class}")
        
        return " ".join(parts)


class IndexedCode(BaseModel):
    """Code entity with its embedding, ready for storage."""
    
    entity: CodeEntity
    embedding: List[float]
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class Repository(BaseModel):
    """Represents a Git repository to index."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    url: str
    branch: str = "main"
    local_path: Optional[str] = None
    
    # Stats
    stars: int = 0
    language: Optional[str] = None
    last_indexed: Optional[datetime] = None
    entity_count: int = 0
    
    # Status
    is_indexed: bool = False
    indexing_error: Optional[str] = None


class SearchResult(BaseModel):
    """A single search result."""
    
    entity: CodeEntity
    score: float
    semantic_score: float = 0.0
    bm25_score: float = 0.0
    highlights: List[str] = Field(default_factory=list)


class SearchQuery(BaseModel):
    """Search query parameters."""
    
    query: str
    language: Optional[Language] = None
    entity_type: Optional[CodeEntityType] = None
    repo_filter: Optional[str] = None
    limit: int = 20
    use_hybrid: bool = True  # Combine semantic + BM25
    semantic_weight: float = 0.7  # Weight for semantic vs BM25


class IndexingJob(BaseModel):
    """A job to index a repository."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repo_url: str
    repo_name: str
    branch: str = "main"
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

