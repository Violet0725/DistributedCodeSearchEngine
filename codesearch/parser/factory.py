"""
Parser factory for automatic language detection and parser selection.
"""

from pathlib import Path
from typing import Dict, Optional, Type, List
import structlog

from .base import CodeParser
from .python_parser import PythonParser
from .javascript_parser import JavaScriptParser
from .go_parser import GoParser
from .rust_parser import RustParser
from ..models import Language, CodeEntity

logger = structlog.get_logger()


class ParserFactory:
    """Factory for creating and managing language-specific parsers."""
    
    # Map of file extensions to parser classes
    _parsers: Dict[str, Type[CodeParser]] = {}
    _instances: Dict[str, CodeParser] = {}
    
    @classmethod
    def register(cls, parser_class: Type[CodeParser]) -> None:
        """Register a parser class for its supported extensions."""
        for ext in parser_class.file_extensions:
            cls._parsers[ext.lower()] = parser_class
    
    @classmethod
    def get_parser(cls, file_path: Path) -> Optional[CodeParser]:
        """Get an appropriate parser for the given file."""
        ext = file_path.suffix.lower()
        
        if ext not in cls._parsers:
            return None
        
        # Use cached instance
        if ext not in cls._instances:
            cls._instances[ext] = cls._parsers[ext]()
        
        return cls._instances[ext]
    
    @classmethod
    def parse_file(cls, file_path: Path, repo_name: str) -> List[CodeEntity]:
        """Parse a file and return extracted entities."""
        parser = cls.get_parser(file_path)
        if not parser:
            logger.debug("No parser found for file", file=str(file_path))
            return []
        
        return parser.parse_file(file_path, repo_name)
    
    @classmethod
    def supported_extensions(cls) -> List[str]:
        """Get list of all supported file extensions."""
        return list(cls._parsers.keys())
    
    @classmethod
    def is_supported(cls, file_path: Path) -> bool:
        """Check if a file type is supported."""
        return file_path.suffix.lower() in cls._parsers


# Register built-in parsers
ParserFactory.register(PythonParser)
ParserFactory.register(JavaScriptParser)
ParserFactory.register(GoParser)
ParserFactory.register(RustParser)


def get_parser(file_path: Path) -> Optional[CodeParser]:
    """Convenience function to get a parser for a file."""
    return ParserFactory.get_parser(file_path)

