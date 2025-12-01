"""
Repository indexer for cloning, parsing, and indexing code.
"""

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import structlog
from tqdm import tqdm

from ..models import CodeEntity, Repository
from ..parser import ParserFactory
from ..embeddings import EmbeddingGenerator, CodeBERTEmbedder
from ..storage import VectorStore, QdrantStore, BM25Index
from ..config import settings

logger = structlog.get_logger()


@dataclass
class IndexResult:
    """Result of an indexing operation."""
    success: bool
    repo_name: str
    entities_found: int = 0
    entities_indexed: int = 0
    files_processed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    languages: Dict[str, int] = field(default_factory=dict)


class RepoIndexer:
    """
    Indexes Git repositories for semantic code search.
    
    Pipeline:
    1. Clone/update repository
    2. Parse all supported source files
    3. Extract code entities (functions, classes, etc.)
    4. Generate embeddings for each entity
    5. Store in vector database
    6. Update BM25 index
    """
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        bm25_index: Optional[BM25Index] = None,
        embedder: Optional[EmbeddingGenerator] = None,
        repos_path: Optional[Path] = None
    ):
        """
        Initialize the indexer.
        
        Args:
            vector_store: Vector database backend
            bm25_index: BM25 lexical index
            embedder: Embedding generator
            repos_path: Directory to store cloned repos
        """
        self.repos_path = repos_path or settings.repos_path
        self.repos_path = Path(self.repos_path)
        self.repos_path.mkdir(parents=True, exist_ok=True)
        
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        self._embedder = embedder
        
        # Lazy initialization flags
        self._storage_initialized = False
        self._embedder_initialized = False
    
    def _ensure_storage(self) -> None:
        """Lazy-load storage backends."""
        if not self._storage_initialized:
            if self._vector_store is None:
                self._vector_store = QdrantStore()
                self._vector_store.create_collection()
            if self._bm25_index is None:
                self._bm25_index = BM25Index()
                self._bm25_index.load()
            self._storage_initialized = True
    
    def _ensure_embedder(self) -> None:
        """Lazy-load the embedder."""
        if not self._embedder_initialized:
            if self._embedder is None:
                self._embedder = CodeBERTEmbedder()
            self._embedder_initialized = True
    
    def index_repo(
        self,
        repo_url: str,
        repo_name: Optional[str] = None,
        branch: str = "main",
        force_reclone: bool = False,
        show_progress: bool = True
    ) -> IndexResult:
        """
        Index a Git repository.
        
        Args:
            repo_url: Git clone URL
            repo_name: Name for the repo (extracted from URL if not provided)
            branch: Git branch to index
            force_reclone: Force re-clone even if exists
            show_progress: Show progress bars
            
        Returns:
            IndexResult with statistics
        """
        import time
        start_time = time.time()
        
        # Extract repo name from URL if not provided
        if not repo_name:
            repo_name = self._extract_repo_name(repo_url)
        
        logger.info("Starting repo indexing", repo=repo_name, url=repo_url)
        
        try:
            # Step 1: Clone/update repository
            repo_path = self._clone_or_update(repo_url, repo_name, branch, force_reclone)
            
            # Step 2: Parse all files
            entities, files_processed, languages = self._parse_repo(
                repo_path, repo_name, show_progress
            )
            
            if not entities:
                return IndexResult(
                    success=True,
                    repo_name=repo_name,
                    entities_found=0,
                    entities_indexed=0,
                    files_processed=files_processed,
                    duration_seconds=time.time() - start_time,
                    languages=languages
                )
            
            # Step 3: Initialize storage and embedder
            self._ensure_storage()
            self._ensure_embedder()
            
            # Step 4: Delete existing entries for this repo
            self._vector_store.delete_by_repo(repo_name)
            self._bm25_index.remove_by_repo(repo_name)
            
            # Step 5: Generate embeddings
            logger.info("Generating embeddings", count=len(entities))
            embeddings = self._embedder.embed_entities(entities, show_progress)
            
            # Step 6: Store in vector database
            logger.info("Storing in vector database")
            indexed_count = self._vector_store.insert(entities, embeddings)
            
            # Step 7: Update BM25 index
            self._bm25_index.add_entities(entities)
            self._bm25_index.save()
            
            duration = time.time() - start_time
            
            logger.info(
                "Repo indexed successfully",
                repo=repo_name,
                entities=indexed_count,
                duration=f"{duration:.1f}s"
            )
            
            return IndexResult(
                success=True,
                repo_name=repo_name,
                entities_found=len(entities),
                entities_indexed=indexed_count,
                files_processed=files_processed,
                duration_seconds=duration,
                languages=languages
            )
            
        except Exception as e:
            logger.error("Indexing failed", repo=repo_name, error=str(e))
            return IndexResult(
                success=False,
                repo_name=repo_name,
                duration_seconds=time.time() - start_time,
                error=str(e)
            )
    
    def index_directory(
        self,
        directory: str,
        repo_name: str = "local",
        show_progress: bool = True
    ) -> IndexResult:
        """
        Index a local directory (without Git operations).
        
        Args:
            directory: Path to directory
            repo_name: Name to assign to indexed files
            show_progress: Show progress bars
            
        Returns:
            IndexResult with statistics
        """
        import time
        start_time = time.time()
        
        dir_path = Path(directory)
        if not dir_path.exists():
            return IndexResult(
                success=False,
                repo_name=repo_name,
                error=f"Directory not found: {directory}"
            )
        
        try:
            # Parse all files
            entities, files_processed, languages = self._parse_repo(
                dir_path, repo_name, show_progress
            )
            
            if not entities:
                return IndexResult(
                    success=True,
                    repo_name=repo_name,
                    entities_found=0,
                    entities_indexed=0,
                    files_processed=files_processed,
                    duration_seconds=time.time() - start_time,
                    languages=languages
                )
            
            # Initialize storage and embedder
            self._ensure_storage()
            self._ensure_embedder()
            
            # Delete existing entries
            self._vector_store.delete_by_repo(repo_name)
            self._bm25_index.remove_by_repo(repo_name)
            
            # Generate embeddings and store
            embeddings = self._embedder.embed_entities(entities, show_progress)
            indexed_count = self._vector_store.insert(entities, embeddings)
            
            self._bm25_index.add_entities(entities)
            self._bm25_index.save()
            
            duration = time.time() - start_time
            
            return IndexResult(
                success=True,
                repo_name=repo_name,
                entities_found=len(entities),
                entities_indexed=indexed_count,
                files_processed=files_processed,
                duration_seconds=duration,
                languages=languages
            )
            
        except Exception as e:
            return IndexResult(
                success=False,
                repo_name=repo_name,
                duration_seconds=time.time() - start_time,
                error=str(e)
            )
    
    def _extract_repo_name(self, url: str) -> str:
        """Extract repository name from Git URL."""
        name = url.rstrip('/').split('/')[-1]
        if name.endswith('.git'):
            name = name[:-4]
        return name
    
    def _clone_or_update(
        self,
        repo_url: str,
        repo_name: str,
        branch: str,
        force_reclone: bool
    ) -> Path:
        """Clone or update a Git repository."""
        import git
        
        repo_path = self.repos_path / repo_name
        
        if repo_path.exists():
            if force_reclone:
                logger.info("Removing existing repo for reclone", path=str(repo_path))
                shutil.rmtree(repo_path)
            else:
                # Try to update existing repo
                try:
                    repo = git.Repo(repo_path)
                    logger.info("Updating existing repo", repo=repo_name)
                    repo.remotes.origin.fetch()
                    repo.git.checkout(branch)
                    repo.remotes.origin.pull()
                    return repo_path
                except Exception as e:
                    logger.warning("Failed to update, will reclone", error=str(e))
                    shutil.rmtree(repo_path)
        
        # Clone repository
        logger.info("Cloning repository", url=repo_url, branch=branch)
        git.Repo.clone_from(
            repo_url,
            repo_path,
            branch=branch,
            depth=1  # Shallow clone for speed
        )
        
        return repo_path
    
    def _parse_repo(
        self,
        repo_path: Path,
        repo_name: str,
        show_progress: bool
    ) -> tuple[List[CodeEntity], int, Dict[str, int]]:
        """Parse all supported files in a repository."""
        entities = []
        files_processed = 0
        languages: Dict[str, int] = {}
        
        # Skip directories
        skip_dirs = {
            'node_modules', 'venv', '.venv', '__pycache__', '.git',
            'dist', 'build', 'target', '.tox', '.pytest_cache',
            'vendor', 'third_party', 'external'
        }
        
        # Find all supported files
        files_to_parse = []
        for ext in ParserFactory.supported_extensions():
            for file_path in repo_path.rglob(f"*{ext}"):
                if not any(d in file_path.parts for d in skip_dirs):
                    files_to_parse.append(file_path)
        
        # Parse files
        iterator = files_to_parse
        if show_progress:
            iterator = tqdm(iterator, desc="Parsing files", unit="file")
        
        for file_path in iterator:
            try:
                file_entities = ParserFactory.parse_file(file_path, repo_name)
                entities.extend(file_entities)
                files_processed += 1
                
                # Track language stats
                if file_entities:
                    lang = file_entities[0].language.value
                    languages[lang] = languages.get(lang, 0) + len(file_entities)
                    
            except Exception as e:
                logger.debug("Failed to parse file", file=str(file_path), error=str(e))
        
        logger.info(
            "Parsing complete",
            files=files_processed,
            entities=len(entities),
            languages=languages
        )
        
        return entities, files_processed, languages


class GitHubScraper:
    """
    Scraper for discovering popular repositories to index.
    
    Uses GitHub API to find popular repos by language, topic, etc.
    """
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize the scraper.
        
        Args:
            token: GitHub API token (optional, increases rate limit)
        """
        self.token = token or settings.github_token
        self._session = None
    
    async def _get_session(self):
        """Get or create aiohttp session."""
        import aiohttp
        
        if self._session is None:
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if self.token:
                headers['Authorization'] = f'token {self.token}'
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session
    
    async def search_repos(
        self,
        language: Optional[str] = None,
        topic: Optional[str] = None,
        min_stars: int = 100,
        limit: int = 100
    ) -> List[Repository]:
        """
        Search for repositories on GitHub.
        
        Args:
            language: Filter by programming language
            topic: Filter by topic
            min_stars: Minimum number of stars
            limit: Maximum number of repos to return
            
        Returns:
            List of Repository objects
        """
        session = await self._get_session()
        
        # Build query
        query_parts = [f'stars:>={min_stars}']
        if language:
            query_parts.append(f'language:{language}')
        if topic:
            query_parts.append(f'topic:{topic}')
        
        query = ' '.join(query_parts)
        
        repos = []
        page = 1
        per_page = min(100, limit)
        
        while len(repos) < limit:
            url = (
                f'https://api.github.com/search/repositories'
                f'?q={query}&sort=stars&order=desc&page={page}&per_page={per_page}'
            )
            
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error("GitHub API error", status=response.status)
                    break
                
                data = await response.json()
                items = data.get('items', [])
                
                if not items:
                    break
                
                for item in items:
                    repos.append(Repository(
                        name=item['full_name'].replace('/', '_'),
                        url=item['clone_url'],
                        branch=item.get('default_branch', 'main'),
                        stars=item['stargazers_count'],
                        language=item.get('language')
                    ))
                
                page += 1
                
                if len(items) < per_page:
                    break
        
        return repos[:limit]
    
    async def close(self):
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None

