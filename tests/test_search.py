"""
Tests for the search engine.
"""

import pytest
from codesearch.models import CodeEntity, CodeEntityType, Language
from codesearch.storage.bm25_index import BM25Index
from codesearch.search.engine import LocalSearchEngine


class TestBM25Index:
    """Tests for BM25 index."""
    
    def setup_method(self):
        self.index = BM25Index()
    
    def create_entity(self, name: str, docstring: str = None, **kwargs) -> CodeEntity:
        """Helper to create test entities."""
        return CodeEntity(
            name=name,
            entity_type=kwargs.get('entity_type', CodeEntityType.FUNCTION),
            language=kwargs.get('language', Language.PYTHON),
            file_path=kwargs.get('file_path', 'test.py'),
            repo_name=kwargs.get('repo_name', 'test-repo'),
            start_line=1,
            end_line=10,
            source_code=f"def {name}(): pass",
            docstring=docstring,
            signature=f"def {name}()",
            parameters=kwargs.get('parameters', []),
        )
    
    def test_add_and_search(self):
        """Test adding entities and searching."""
        entities = [
            self.create_entity("parse_json", "Parse a JSON string into a dictionary"),
            self.create_entity("serialize_json", "Convert object to JSON string"),
            self.create_entity("validate_email", "Validate an email address"),
        ]
        
        self.index.add_entities(entities)
        
        # Search for JSON-related functions
        results = self.index.search("JSON parsing")
        
        assert len(results) > 0
        # parse_json should rank higher for this query
        names = [r[0].name for r in results]
        assert "parse_json" in names[:2]
    
    def test_search_with_filters(self):
        """Test search with language filter."""
        entities = [
            self.create_entity("parse_json", language=Language.PYTHON),
            self.create_entity("parseJson", language=Language.JAVASCRIPT),
        ]
        
        self.index.add_entities(entities)
        
        # Search with Python filter
        results = self.index.search("parse json", filters={"language": "python"})
        
        assert len(results) == 1
        assert results[0][0].language == Language.PYTHON
    
    def test_remove_by_repo(self):
        """Test removing entities by repository."""
        entities = [
            self.create_entity("func1", repo_name="repo-a"),
            self.create_entity("func2", repo_name="repo-a"),
            self.create_entity("func3", repo_name="repo-b"),
        ]
        
        self.index.add_entities(entities)
        assert self.index.count() == 3
        
        # Remove repo-a
        removed = self.index.remove_by_repo("repo-a")
        
        assert removed == 2
        assert self.index.count() == 1
    
    def test_tokenization(self):
        """Test code-specific tokenization."""
        # Test camelCase splitting
        tokens = self.index._tokenize("parseJSONData")
        assert "parse" in tokens
        assert "json" in tokens
        assert "data" in tokens
        
        # Test snake_case splitting
        tokens = self.index._tokenize("parse_json_data")
        assert "parse" in tokens
        assert "json" in tokens
        assert "data" in tokens


class TestLocalSearchEngine:
    """Tests for local search engine."""
    
    def test_search_empty(self):
        """Test searching empty index."""
        engine = LocalSearchEngine()
        results = engine.search("any query")
        
        assert len(results) == 0

