"""
Configuration management for CodeSearch engine.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Qdrant Vector Database
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_collection: str = Field(default="code_embeddings", alias="QDRANT_COLLECTION")
    
    # RabbitMQ Message Queue
    rabbitmq_host: str = Field(default="localhost", alias="RABBITMQ_HOST")
    rabbitmq_port: int = Field(default=5672, alias="RABBITMQ_PORT")
    rabbitmq_user: str = Field(default="guest", alias="RABBITMQ_USER")
    rabbitmq_password: str = Field(default="guest", alias="RABBITMQ_PASSWORD")
    rabbitmq_queue: str = Field(default="indexing_jobs", alias="RABBITMQ_QUEUE")
    
    # Embedding Model
    embedding_model: str = Field(
        default="microsoft/codebert-base",
        alias="EMBEDDING_MODEL"
    )
    embedding_dimension: int = Field(default=768, alias="EMBEDDING_DIMENSION")
    
    # Storage paths
    repos_path: Path = Field(default=Path("./data/repos"), alias="REPOS_PATH")
    index_path: Path = Field(default=Path("./data/index"), alias="INDEX_PATH")
    
    # Processing
    batch_size: int = Field(default=32, alias="BATCH_SIZE")
    max_workers: int = Field(default=4, alias="MAX_WORKERS")
    
    # GitHub API (optional, for rate limiting)
    github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @property
    def rabbitmq_url(self) -> str:
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/"


settings = Settings()

