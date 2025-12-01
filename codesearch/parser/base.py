"""
Base parser interface for code entity extraction.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
import structlog

from ..models import CodeEntity, Language

logger = structlog.get_logger()


class CodeParser(ABC):
    """Abstract base class for language-specific code parsers."""
    
    language: Language = Language.UNKNOWN
    file_extensions: List[str] = []
    
    def __init__(self):
        self._init_parser()
    
    @abstractmethod
    def _init_parser(self) -> None:
        """Initialize the tree-sitter parser for this language."""
        pass
    
    @abstractmethod
    def parse_file(self, file_path: Path, repo_name: str) -> List[CodeEntity]:
        """
        Parse a source file and extract code entities.
        
        Args:
            file_path: Path to the source file
            repo_name: Name of the repository containing this file
            
        Returns:
            List of extracted CodeEntity objects
        """
        pass
    
    def parse_content(self, content: str, file_path: str, repo_name: str) -> List[CodeEntity]:
        """
        Parse source code content directly.
        
        Args:
            content: Source code as string
            file_path: Virtual file path for reference
            repo_name: Name of the repository
            
        Returns:
            List of extracted CodeEntity objects
        """
        raise NotImplementedError("Direct content parsing not implemented")
    
    @classmethod
    def supports_file(cls, file_path: Path) -> bool:
        """Check if this parser supports the given file."""
        return file_path.suffix.lower() in cls.file_extensions
    
    @staticmethod
    def _extract_docstring(node, source_bytes: bytes) -> Optional[str]:
        """Extract docstring from a function/class node if present."""
        # Override in subclasses for language-specific docstring extraction
        return None
    
    @staticmethod
    def _calculate_complexity(node) -> int:
        """Calculate cyclomatic complexity of a code block."""
        # Simple approximation: count branches
        complexity = 1
        branch_types = {
            'if_statement', 'elif_clause', 'for_statement', 
            'while_statement', 'except_clause', 'with_statement',
            'conditional_expression', 'and', 'or'
        }
        
        def count_branches(n):
            nonlocal complexity
            if hasattr(n, 'type') and n.type in branch_types:
                complexity += 1
            if hasattr(n, 'children'):
                for child in n.children:
                    count_branches(child)
        
        count_branches(node)
        return complexity
    
    def _get_node_text(self, node, source_bytes: bytes) -> str:
        """Extract text content from a tree-sitter node."""
        return source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

