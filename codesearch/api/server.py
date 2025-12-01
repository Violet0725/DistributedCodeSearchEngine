"""
FastAPI server for CodeSearch REST API.
"""

from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..models import SearchQuery, SearchResult, Language, CodeEntityType
from ..search.engine import HybridSearchEngine
from ..indexer import RepoIndexer
from ..queue import JobPublisher

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"


# Request/Response models
class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    language: Optional[str] = None
    entity_type: Optional[str] = None
    repo_filter: Optional[str] = None
    use_hybrid: bool = True
    semantic_weight: float = 0.7


class SearchResponse(BaseModel):
    results: List[dict]
    total: int
    query: str


class IndexRequest(BaseModel):
    repo_url: str
    repo_name: Optional[str] = None
    branch: str = "main"
    priority: int = 5


class IndexResponse(BaseModel):
    success: bool
    job_id: Optional[str] = None
    message: str


class StatsResponse(BaseModel):
    total_vectors: int
    bm25_documents: int
    status: str


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="CodeSearch API",
        description="Semantic Code Search Engine - Find code by what it does",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize search engine (lazy loaded)
    _search_engine = None
    
    def get_search_engine() -> HybridSearchEngine:
        nonlocal _search_engine
        if _search_engine is None:
            _search_engine = HybridSearchEngine()
        return _search_engine
    
    @app.get("/")
    async def serve_gui():
        """Serve the web GUI."""
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        # Fallback to JSON API info if no GUI
        return {
            "name": "CodeSearch API",
            "version": "0.1.0",
            "docs": "/docs",
            "gui": "GUI not found. Static files missing."
        }
    
    @app.get("/api")
    async def api_info():
        """API info endpoint."""
        return {
            "name": "CodeSearch API",
            "version": "0.1.0",
            "docs": "/docs"
        }
    
    @app.post("/search", response_model=SearchResponse)
    async def search(request: SearchRequest):
        """
        Search for code using natural language.
        
        The search combines semantic understanding with keyword matching
        for accurate results.
        """
        try:
            engine = get_search_engine()
            
            # Parse filters
            language = None
            if request.language:
                try:
                    language = Language(request.language.lower())
                except ValueError:
                    pass
            
            entity_type = None
            if request.entity_type:
                try:
                    entity_type = CodeEntityType(request.entity_type.lower())
                except ValueError:
                    pass
            
            results = engine.search(
                query=request.query,
                limit=request.limit,
                language=language,
                entity_type=entity_type,
                repo_filter=request.repo_filter,
                use_hybrid=request.use_hybrid,
                semantic_weight=request.semantic_weight
            )
            
            # Convert to response format
            result_dicts = []
            for r in results:
                result_dicts.append({
                    "name": r.entity.name,
                    "entity_type": r.entity.entity_type.value,
                    "language": r.entity.language.value,
                    "file_path": r.entity.file_path,
                    "repo_name": r.entity.repo_name,
                    "start_line": r.entity.start_line,
                    "end_line": r.entity.end_line,
                    "signature": r.entity.signature,
                    "docstring": r.entity.docstring,
                    "source_code": r.entity.source_code[:2000] if r.entity.source_code else None,
                    "score": r.score,
                    "semantic_score": r.semantic_score,
                    "bm25_score": r.bm25_score
                })
            
            return SearchResponse(
                results=result_dicts,
                total=len(result_dicts),
                query=request.query
            )
        except Exception as e:
            # Return empty results with error info instead of crashing
            return SearchResponse(
                results=[],
                total=0,
                query=request.query
            )
    
    @app.get("/search")
    async def search_get(
        q: str = Query(..., description="Search query"),
        limit: int = Query(20, ge=1, le=100),
        language: Optional[str] = None,
        entity_type: Optional[str] = None,
        repo: Optional[str] = None
    ):
        """GET endpoint for search (convenience)."""
        request = SearchRequest(
            query=q,
            limit=limit,
            language=language,
            entity_type=entity_type,
            repo_filter=repo
        )
        return await search(request)
    
    @app.post("/index", response_model=IndexResponse)
    async def queue_index(request: IndexRequest):
        """
        Queue a repository for indexing.
        
        The job will be processed by background workers.
        """
        try:
            with JobPublisher() as publisher:
                job = publisher.publish_repo(
                    repo_url=request.repo_url,
                    repo_name=request.repo_name,
                    branch=request.branch,
                    priority=request.priority
                )
                
                return IndexResponse(
                    success=True,
                    job_id=job.id,
                    message=f"Repository queued for indexing: {job.repo_name}"
                )
        except Exception as e:
            return IndexResponse(
                success=False,
                message=f"Failed to queue: {str(e)}"
            )
    
    @app.post("/index/sync", response_model=dict)
    async def index_sync(request: IndexRequest):
        """
        Index a repository synchronously (blocking).
        
        Use this for small repos or when you need immediate results.
        For large repos, use /index to queue the job.
        """
        indexer = RepoIndexer()
        
        result = indexer.index_repo(
            repo_url=request.repo_url,
            repo_name=request.repo_name,
            branch=request.branch,
            show_progress=False
        )
        
        return {
            "success": result.success,
            "repo_name": result.repo_name,
            "entities_indexed": result.entities_indexed,
            "files_processed": result.files_processed,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
            "languages": result.languages
        }
    
    @app.get("/stats", response_model=StatsResponse)
    async def get_stats():
        """Get index statistics."""
        try:
            from ..storage import QdrantStore, BM25Index
            
            vector_store = QdrantStore()
            bm25_index = BM25Index()
            bm25_index.load()
            
            stats = vector_store.get_stats()
            
            return StatsResponse(
                total_vectors=stats.get("total_points", 0),
                bm25_documents=bm25_index.count(),
                status=stats.get("status", "unknown")
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    # Local search engine (no Qdrant needed)
    _local_engine = None
    _indexed_path = None
    
    @app.post("/search/local")
    async def search_local(
        query: str = Query(..., description="Search query"),
        path: str = Query("./codesearch", description="Local directory path to search"),
        limit: int = Query(20, ge=1, le=100)
    ):
        """
        Search a local directory without requiring Qdrant.
        Works offline with no Docker needed!
        """
        nonlocal _local_engine, _indexed_path
        
        from ..search.engine import LocalSearchEngine
        
        try:
            # Re-index if path changed or first time
            if _local_engine is None or _indexed_path != path:
                _local_engine = LocalSearchEngine()
                entity_count = _local_engine.index_directory(path)
                _indexed_path = path
            
            results = _local_engine.search(query, limit=limit)
            
            result_dicts = []
            for r in results:
                result_dicts.append({
                    "name": r.entity.name,
                    "entity_type": r.entity.entity_type.value,
                    "language": r.entity.language.value,
                    "file_path": r.entity.file_path,
                    "repo_name": r.entity.repo_name,
                    "start_line": r.entity.start_line,
                    "end_line": r.entity.end_line,
                    "signature": r.entity.signature,
                    "docstring": r.entity.docstring,
                    "source_code": r.entity.source_code[:2000] if r.entity.source_code else None,
                    "score": r.score,
                    "semantic_score": 0,
                    "bm25_score": r.bm25_score
                })
            
            return {
                "results": result_dicts,
                "total": len(result_dicts),
                "query": query,
                "indexed_path": path,
                "mode": "local"
            }
        except FileNotFoundError:
            return {
                "results": [],
                "total": 0,
                "query": query,
                "error": f"Directory not found: {path}"
            }
        except Exception as e:
            return {
                "results": [],
                "total": 0,
                "query": query,
                "error": str(e)
            }
    
    # Mount static files if directory exists
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    
    return app

