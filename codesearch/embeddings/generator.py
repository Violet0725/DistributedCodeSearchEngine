"""
Code embedding generation using transformer models.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Union
import numpy as np
import structlog
from tqdm import tqdm

from ..models import CodeEntity
from ..config import settings

logger = structlog.get_logger()


class EmbeddingGenerator(ABC):
    """Abstract base class for embedding generators."""
    
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        pass
    
    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        pass
    
    def embed_entity(self, entity: CodeEntity) -> List[float]:
        """Generate embedding for a code entity."""
        searchable_text = entity.get_searchable_text()
        return self.embed_text(searchable_text)
    
    def embed_entities(
        self, 
        entities: List[CodeEntity],
        show_progress: bool = True
    ) -> List[List[float]]:
        """Generate embeddings for multiple code entities."""
        texts = [e.get_searchable_text() for e in entities]
        
        # Process in batches
        all_embeddings = []
        batch_size = settings.batch_size
        
        iterator = range(0, len(texts), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Generating embeddings", unit="batch")
        
        for i in iterator:
            batch = texts[i:i + batch_size]
            embeddings = self.embed_batch(batch)
            all_embeddings.extend(embeddings)
        
        return all_embeddings


class CodeBERTEmbedder(EmbeddingGenerator):
    """
    Embedding generator using CodeBERT or similar code-aware models.
    
    Supports models like:
    - microsoft/codebert-base
    - microsoft/graphcodebert-base  
    - huggingface/CodeBERTa-small-v1
    - Salesforce/codet5-base
    """
    
    def __init__(
        self, 
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        normalize: bool = True
    ):
        """
        Initialize the CodeBERT embedder.
        
        Args:
            model_name: HuggingFace model name (default from settings)
            device: 'cuda', 'cpu', or None for auto-detection
            normalize: Whether to L2-normalize embeddings
        """
        self.model_name = model_name or settings.embedding_model
        self.normalize = normalize
        self._model = None
        self._tokenizer = None
        self._device = device
        
        self._load_model()
    
    def _load_model(self) -> None:
        """Load the transformer model and tokenizer."""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info("Loading embedding model", model=self.model_name)
            
            # Try sentence-transformers first (easier API)
            try:
                self._model = SentenceTransformer(self.model_name, device=self._device)
                self._use_sentence_transformer = True
                logger.info("Loaded model via sentence-transformers")
                return
            except Exception:
                pass
            
            # Fall back to transformers directly
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            self._use_sentence_transformer = False
            
            # Device selection
            if self._device is None:
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self._model = self._model.to(self._device)
            self._model.eval()
            
            logger.info("Loaded model via transformers", device=self._device)
            
        except ImportError as e:
            logger.error("Required ML libraries not installed", error=str(e))
            raise RuntimeError(
                "Please install: pip install sentence-transformers transformers torch"
            )
        except Exception as e:
            logger.error("Failed to load model", model=self.model_name, error=str(e))
            raise
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        return self.embed_batch([text])[0]
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []
        
        try:
            if self._use_sentence_transformer:
                embeddings = self._model.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=self.normalize,
                    show_progress_bar=False
                )
                return embeddings.tolist()
            else:
                return self._embed_with_transformers(texts)
                
        except Exception as e:
            logger.error("Embedding generation failed", error=str(e))
            # Return zero vectors as fallback
            dim = settings.embedding_dimension
            return [[0.0] * dim for _ in texts]
    
    def _embed_with_transformers(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using raw transformers library."""
        import torch
        
        # Tokenize
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(self._device)
        
        # Get embeddings
        with torch.no_grad():
            outputs = self._model(**encoded)
            
            # Use mean pooling over token embeddings
            attention_mask = encoded['attention_mask']
            token_embeddings = outputs.last_hidden_state
            
            # Expand attention mask for broadcasting
            input_mask_expanded = (
                attention_mask
                .unsqueeze(-1)
                .expand(token_embeddings.size())
                .float()
            )
            
            # Sum and divide by mask sum
            sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            embeddings = sum_embeddings / sum_mask
        
        # Normalize if requested
        if self.normalize:
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        
        return embeddings.cpu().numpy().tolist()
    
    @property
    def embedding_dimension(self) -> int:
        """Get the dimension of generated embeddings."""
        if self._use_sentence_transformer:
            return self._model.get_sentence_embedding_dimension()
        else:
            return self._model.config.hidden_size


class MockEmbedder(EmbeddingGenerator):
    """Mock embedder for testing without ML dependencies."""
    
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
    
    def embed_text(self, text: str) -> List[float]:
        """Generate deterministic mock embedding based on text hash."""
        import hashlib
        
        # Create deterministic embedding from text
        hash_bytes = hashlib.sha256(text.encode()).digest()
        
        # Convert to floats
        embedding = []
        for i in range(0, min(len(hash_bytes), self.dimension), 4):
            val = int.from_bytes(hash_bytes[i:i+4], 'big') / (2**32)
            embedding.append(val * 2 - 1)  # Scale to [-1, 1]
        
        # Pad or truncate to dimension
        while len(embedding) < self.dimension:
            embedding.append(0.0)
        embedding = embedding[:self.dimension]
        
        # Normalize
        norm = np.sqrt(sum(x*x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings for batch."""
        return [self.embed_text(t) for t in texts]

