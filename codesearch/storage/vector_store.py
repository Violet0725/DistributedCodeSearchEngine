"""
Vector database integration for storing and querying code embeddings.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import CodeEntity, SearchResult
from ..config import settings

logger = structlog.get_logger()


class VectorStore(ABC):
    """Abstract base class for vector storage backends."""
    
    @abstractmethod
    def create_collection(self, recreate: bool = False) -> None:
        """Create the vector collection/index."""
        pass
    
    @abstractmethod
    def insert(
        self, 
        entities: List[CodeEntity], 
        embeddings: List[List[float]]
    ) -> int:
        """Insert code entities with their embeddings."""
        pass
    
    @abstractmethod
    def search(
        self,
        query_embedding: List[float],
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[CodeEntity, float]]:
        """Search for similar code entities."""
        pass
    
    @abstractmethod
    def delete_by_repo(self, repo_name: str) -> int:
        """Delete all entities from a specific repository."""
        pass
    
    @abstractmethod
    def count(self) -> int:
        """Get total count of indexed entities."""
        pass


class QdrantStore(VectorStore):
    """
    Qdrant vector database backend.
    
    Supports both local (in-memory/disk) and remote Qdrant instances.
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection_name: Optional[str] = None,
        embedding_dimension: int = 768,
        use_memory: bool = False
    ):
        """
        Initialize Qdrant connection.
        
        Args:
            host: Qdrant server host
            port: Qdrant server port
            collection_name: Name of the collection
            embedding_dimension: Dimension of embeddings
            use_memory: Use in-memory storage (for testing)
        """
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.collection_name = collection_name or settings.qdrant_collection
        self.embedding_dimension = embedding_dimension
        self.use_memory = use_memory
        
        self._client = None
        self._connect()
    
    def _connect(self) -> None:
        """Establish connection to Qdrant."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams
            
            if self.use_memory:
                self._client = QdrantClient(":memory:")
                logger.info("Connected to in-memory Qdrant")
            else:
                self._client = QdrantClient(host=self.host, port=self.port)
                logger.info("Connected to Qdrant", host=self.host, port=self.port)
                
        except ImportError:
            raise RuntimeError("Please install: pip install qdrant-client")
        except Exception as e:
            logger.error("Failed to connect to Qdrant", error=str(e))
            raise
    
    def create_collection(self, recreate: bool = False) -> None:
        """Create the code embeddings collection."""
        from qdrant_client.http.models import Distance, VectorParams, PayloadSchemaType
        
        try:
            collections = self._client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if exists:
                if recreate:
                    logger.info("Deleting existing collection", collection=self.collection_name)
                    self._client.delete_collection(self.collection_name)
                else:
                    logger.info("Collection already exists", collection=self.collection_name)
                    return
            
            # Create collection with optimal settings for code search
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_dimension,
                    distance=Distance.COSINE
                ),
                # Enable payload indexing for filtering
                on_disk_payload=True
            )
            
            # Create payload indexes for common filters
            self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="language",
                field_schema=PayloadSchemaType.KEYWORD
            )
            self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="entity_type",
                field_schema=PayloadSchemaType.KEYWORD
            )
            self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name="repo_name",
                field_schema=PayloadSchemaType.KEYWORD
            )
            
            logger.info("Created collection", collection=self.collection_name)
            
        except Exception as e:
            logger.error("Failed to create collection", error=str(e))
            raise
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def insert(
        self, 
        entities: List[CodeEntity], 
        embeddings: List[List[float]]
    ) -> int:
        """Insert code entities with their embeddings."""
        from qdrant_client.http.models import PointStruct
        
        if len(entities) != len(embeddings):
            raise ValueError("Number of entities must match number of embeddings")
        
        if not entities:
            return 0
        
        points = []
        for entity, embedding in zip(entities, embeddings):
            # Convert entity to payload
            payload = {
                "name": entity.name,
                "entity_type": entity.entity_type.value,
                "language": entity.language.value,
                "file_path": entity.file_path,
                "repo_name": entity.repo_name,
                "start_line": entity.start_line,
                "end_line": entity.end_line,
                "source_code": entity.source_code[:10000],  # Limit size
                "docstring": entity.docstring,
                "signature": entity.signature,
                "parameters": entity.parameters,
                "return_type": entity.return_type,
                "decorators": entity.decorators,
                "parent_class": entity.parent_class,
                "complexity": entity.complexity,
                "loc": entity.loc,
            }
            
            points.append(PointStruct(
                id=entity.id,
                vector=embedding,
                payload=payload
            ))
        
        # Batch upsert
        self._client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True
        )
        
        logger.debug("Inserted entities", count=len(entities))
        return len(entities)
    
    def search(
        self,
        query_embedding: List[float],
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[CodeEntity, float]]:
        """Search for similar code entities."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        # Check if collection exists
        try:
            collections = self._client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                logger.warning("Collection does not exist", collection=self.collection_name)
                return []
        except Exception as e:
            logger.error("Failed to check collection", error=str(e))
            return []
        
        # Build filter conditions
        query_filter = None
        if filters:
            conditions = []
            
            if "language" in filters:
                conditions.append(FieldCondition(
                    key="language",
                    match=MatchValue(value=filters["language"])
                ))
            
            if "entity_type" in filters:
                conditions.append(FieldCondition(
                    key="entity_type",
                    match=MatchValue(value=filters["entity_type"])
                ))
            
            if "repo_name" in filters:
                conditions.append(FieldCondition(
                    key="repo_name",
                    match=MatchValue(value=filters["repo_name"])
                ))
            
            if conditions:
                query_filter = Filter(must=conditions)
        
        # Execute search - try new API first, fallback to old API
        try:
            # New Qdrant API (v1.7+)
            search_results = self._client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                score_threshold=0.0  # Get all results, let ranking handle it
            )
            results = search_results
        except (AttributeError, TypeError) as e:
            # Fallback: try query_points API
            try:
                response = self._client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                )
                results = response.points
            except Exception:
                # Last resort: old search API
                results = self._client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                )
        
        # Convert results to CodeEntity objects
        entities_with_scores = []
        for result in results:
            # Handle different result formats
            if hasattr(result, 'payload'):
                payload = result.payload
                result_id = result.id
                # Score might be in different attributes
                score = getattr(result, 'score', getattr(result, 'distance', 0.0))
                # For cosine similarity, higher is better. If it's distance, convert.
                if hasattr(result, 'distance'):
                    score = 1.0 - result.distance  # Convert distance to similarity
            else:
                # Old format
                payload = result.get('payload', {}) if isinstance(result, dict) else {}
                result_id = result.get('id', '')
                score = result.get('score', 0.0)
            
            entity = CodeEntity(
                id=result_id,
                name=payload.get("name", ""),
                entity_type=payload.get("entity_type", "function"),
                language=payload.get("language", "unknown"),
                file_path=payload.get("file_path", ""),
                repo_name=payload.get("repo_name", ""),
                start_line=payload.get("start_line", 0),
                end_line=payload.get("end_line", 0),
                source_code=payload.get("source_code", ""),
                docstring=payload.get("docstring"),
                signature=payload.get("signature"),
                parameters=payload.get("parameters", []),
                return_type=payload.get("return_type"),
                decorators=payload.get("decorators", []),
                parent_class=payload.get("parent_class"),
                complexity=payload.get("complexity"),
                loc=payload.get("loc", 0),
            )
            
            entities_with_scores.append((entity, float(score)))
        
        return entities_with_scores
    
    def delete_by_repo(self, repo_name: str) -> int:
        """Delete all entities from a specific repository."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        # Get count before deletion
        count_before = self._count_by_filter({"repo_name": repo_name})
        
        # Delete with filter
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(
                    key="repo_name",
                    match=MatchValue(value=repo_name)
                )]
            ),
            wait=True
        )
        
        logger.info("Deleted entities", repo=repo_name, count=count_before)
        return count_before
    
    def count(self) -> int:
        """Get total count of indexed entities."""
        info = self._client.get_collection(self.collection_name)
        return info.points_count
    
    def _count_by_filter(self, filters: Dict[str, Any]) -> int:
        """Count entities matching a filter."""
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        conditions = []
        for key, value in filters.items():
            conditions.append(FieldCondition(
                key=key,
                match=MatchValue(value=value)
            ))
        
        result = self._client.count(
            collection_name=self.collection_name,
            count_filter=Filter(must=conditions),
            exact=True
        )
        
        return result.count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        info = self._client.get_collection(self.collection_name)
        
        return {
            "total_points": info.points_count,
            "indexed_vectors": info.indexed_vectors_count,
            "segments": info.segments_count,
            "status": info.status,
        }

