"""
BM25 index for lexical/keyword search to complement semantic search.
"""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
import structlog
from rank_bm25 import BM25Okapi

from ..models import CodeEntity
from ..config import settings

logger = structlog.get_logger()


class BM25Index:
    """
    BM25 index for traditional keyword-based code search.
    
    Used in hybrid search to complement semantic search with
    exact keyword matching capabilities.
    """
    
    def __init__(self, index_path: Optional[Path] = None):
        """
        Initialize BM25 index.
        
        Args:
            index_path: Path to store the index files
        """
        self.index_path = index_path or settings.index_path
        self.index_path = Path(self.index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        self._bm25: Optional[BM25Okapi] = None
        self._entities: List[CodeEntity] = []
        self._entity_ids: Dict[str, int] = {}  # entity_id -> index
        self._corpus: List[List[str]] = []
    
    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text for BM25.
        
        Handles code-specific tokenization including:
        - CamelCase splitting
        - snake_case splitting
        - Preserving important code patterns
        """
        import re
        
        # Split CamelCase BEFORE converting to lowercase
        # Handle: parseJSON -> parse JSON
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # Handle: JSONData -> JSON Data (uppercase followed by lowercase)
        text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)
        
        # Convert to lowercase
        text = text.lower()
        
        # Split snake_case and other separators
        text = re.sub(r'[_\-./\\]', ' ', text)
        
        # Remove special characters but keep alphanumeric
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Split and filter
        tokens = text.split()
        tokens = [t for t in tokens if len(t) >= 2]  # Min length 2
        
        return tokens
    
    def _entity_to_document(self, entity: CodeEntity) -> str:
        """Convert a code entity to a searchable document."""
        parts = [
            entity.name,
            entity.signature or "",
            entity.docstring or "",
            " ".join(entity.parameters),
            entity.parent_class or "",
            entity.return_type or "",
        ]
        return " ".join(filter(None, parts))
    
    def add_entities(self, entities: List[CodeEntity]) -> int:
        """Add entities to the BM25 index."""
        added = 0
        
        for entity in entities:
            if entity.id in self._entity_ids:
                continue  # Skip duplicates
            
            doc = self._entity_to_document(entity)
            tokens = self._tokenize(doc)
            
            self._entity_ids[entity.id] = len(self._entities)
            self._entities.append(entity)
            self._corpus.append(tokens)
            added += 1
        
        # Rebuild BM25 index
        if added > 0:
            self._rebuild_index()
        
        logger.debug("Added entities to BM25 index", count=added)
        return added
    
    def _rebuild_index(self) -> None:
        """Rebuild the BM25 index from corpus."""
        if not self._corpus:
            self._bm25 = None
            return
        
        self._bm25 = BM25Okapi(self._corpus)
    
    def search(
        self,
        query: str,
        limit: int = 20,
        filters: Optional[Dict[str, str]] = None
    ) -> List[Tuple[CodeEntity, float]]:
        """
        Search the BM25 index.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            filters: Optional filters (language, entity_type, repo_name)
            
        Returns:
            List of (entity, score) tuples sorted by relevance
        """
        if not self._bm25 or not self._entities:
            return []
        
        # Tokenize query
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        # Get BM25 scores
        scores = self._bm25.get_scores(query_tokens)
        
        # Create (index, score) pairs and filter
        # Note: BM25 can return negative scores when IDF is negative (few documents)
        # We use a threshold instead of strictly positive to handle edge cases
        min_score = max(scores) * 0.01 if len(scores) > 0 and max(scores) > 0 else float('-inf')
        results = []
        for idx, score in enumerate(scores):
            if score < min_score:
                continue
            
            entity = self._entities[idx]
            
            # Apply filters
            if filters:
                if "language" in filters and entity.language.value != filters["language"]:
                    continue
                if "entity_type" in filters and entity.entity_type.value != filters["entity_type"]:
                    continue
                if "repo_name" in filters and entity.repo_name != filters["repo_name"]:
                    continue
            
            results.append((entity, score))
        
        # Sort by score and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    def remove_by_repo(self, repo_name: str) -> int:
        """Remove all entities from a specific repository."""
        # Find indices to remove
        to_remove: Set[int] = set()
        for entity_id, idx in self._entity_ids.items():
            if self._entities[idx].repo_name == repo_name:
                to_remove.add(idx)
        
        if not to_remove:
            return 0
        
        # Rebuild without removed entities
        new_entities = []
        new_corpus = []
        new_ids = {}
        
        for idx, (entity, tokens) in enumerate(zip(self._entities, self._corpus)):
            if idx not in to_remove:
                new_ids[entity.id] = len(new_entities)
                new_entities.append(entity)
                new_corpus.append(tokens)
        
        removed_count = len(to_remove)
        
        self._entities = new_entities
        self._corpus = new_corpus
        self._entity_ids = new_ids
        self._rebuild_index()
        
        logger.info("Removed entities from BM25", repo=repo_name, count=removed_count)
        return removed_count
    
    def save(self) -> None:
        """Save the index to disk."""
        index_file = self.index_path / "bm25_index.pkl"
        
        data = {
            "entities": [e.model_dump() for e in self._entities],
            "corpus": self._corpus,
            "entity_ids": self._entity_ids,
        }
        
        with open(index_file, 'wb') as f:
            pickle.dump(data, f)
        
        logger.info("Saved BM25 index", path=str(index_file), count=len(self._entities))
    
    def load(self) -> bool:
        """Load the index from disk."""
        index_file = self.index_path / "bm25_index.pkl"
        
        if not index_file.exists():
            logger.debug("No BM25 index file found")
            return False
        
        try:
            with open(index_file, 'rb') as f:
                data = pickle.load(f)
            
            self._entities = [CodeEntity(**e) for e in data["entities"]]
            self._corpus = data["corpus"]
            self._entity_ids = data["entity_ids"]
            self._rebuild_index()
            
            logger.info("Loaded BM25 index", count=len(self._entities))
            return True
            
        except Exception as e:
            logger.error("Failed to load BM25 index", error=str(e))
            return False
    
    def count(self) -> int:
        """Get number of indexed entities."""
        return len(self._entities)
    
    def clear(self) -> None:
        """Clear all indexed data."""
        self._bm25 = None
        self._entities = []
        self._entity_ids = {}
        self._corpus = []

